#!/usr/bin/env python3
"""
scansnapToVM.py

Attach or detach a Fujitsu ScanSnap S1300i USB device to/from a running
libvirt / virt-manager virtual machine.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


CONFIG_DIR = Path.home() / ".config" / "scansnapToVM"
CONFIG_PATH = CONFIG_DIR / "config.json"


def getLogger():
    try:
        from organiseMyProjects.logUtils import getLogger as projectGetLogger  # type: ignore
        return projectGetLogger("scansnapToVM")
    except Exception:
        import logging

        logger = logging.getLogger("scansnapToVM")
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger


logger = getLogger()


@dataclass(frozen=True)
class UsbAddress:
    bus: int
    device: int


@dataclass(frozen=True)
class HostScanner:
    bus: int
    device: int
    rawLine: str


class ScanSnapError(RuntimeError):
    pass


def logStep(message: str) -> None:
    logger.info(f"...{message}")


def logValue(message: str, value: str) -> None:
    logger.info(f"...{message}: {value}")


def runCommand(command: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        details = stderr or stdout or f"command failed with exit code {result.returncode}"
        raise ScanSnapError(details)
    return result


def requireCommand(commandName: str) -> None:
    if shutil.which(commandName) is None:
        raise ScanSnapError(f"missing command: {commandName}")


def parseArguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Attach or detach a ScanSnap S1300i to/from a running libvirt VM."
    )
    parser.add_argument(
        "vmName",
        nargs="?",
        help=(
            "libvirt domain name. If omitted, the saved config entry is used. "
            "If no saved config exists, SCANSNAP_VM is used. "
            "If exactly one VM is running, that VM is used."
        ),
    )
    parser.add_argument(
        "--drop",
        action="store_true",
        help="detach the scanner from the running VM and hand it back to linux",
    )
    parser.add_argument(
        "--persist",
        action="store_true",
        help="also update the persistent VM config",
    )
    parser.add_argument(
        "--show-config",
        action="store_true",
        help="show the saved config and exit",
    )
    parser.add_argument(
        "--clear-config",
        action="store_true",
        help="clear the saved config and exit",
    )
    return parser.parse_args()


def loadConfig() -> dict:
    if not CONFIG_PATH.exists():
        return {}

    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ScanSnapError(f"unable to read config: {exc}") from exc


def saveConfig(config: dict) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except Exception as exc:
        raise ScanSnapError(f"unable to write config: {exc}") from exc


def clearConfig() -> None:
    if CONFIG_PATH.exists():
        CONFIG_PATH.unlink()
    logValue("config cleared", str(CONFIG_PATH))


def getConfiguredVmName() -> str:
    config = loadConfig()
    vmName = config.get("vmName", "").strip()
    return vmName


def saveConfiguredVmName(vmName: str) -> None:
    config = loadConfig()
    config["vmName"] = vmName
    saveConfig(config)
    logValue("config vmName", vmName)
    logValue("config path", str(CONFIG_PATH))


def resolveVmName(argVmName: Optional[str]) -> str:
    if argVmName:
        saveConfiguredVmName(argVmName)
        return argVmName

    configuredVmName = getConfiguredVmName()
    if configuredVmName:
        return configuredVmName

    envVmName = os.environ.get("SCANSNAP_VM", "").strip()
    if envVmName:
        return envVmName

    result = runCommand(["virsh", "list", "--name"])
    runningVms = [line.strip() for line in result.stdout.splitlines() if line.strip()]

    if len(runningVms) == 1:
        return runningVms[0]

    raise ScanSnapError(
        "no vm name supplied and unable to infer one. pass a domain name, save one in config, or set SCANSNAP_VM."
    )


def assertVmRunning(vmName: str) -> None:
    result = runCommand(["virsh", "list", "--name"])
    runningVms = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if vmName not in runningVms:
        raise ScanSnapError(f"vm is not running: {vmName}")


def getHostScanner() -> HostScanner:
    result = runCommand(["lsusb"])
    pattern = re.compile(
        r"^Bus\s+(?P<bus>\d+)\s+Device\s+(?P<device>\d+):\s+ID\s+04c5:128d\b.*$",
        re.IGNORECASE,
    )

    for line in result.stdout.splitlines():
        match = pattern.match(line.strip())
        if match:
            return HostScanner(
                bus=int(match.group("bus")),
                device=int(match.group("device")),
                rawLine=line.strip(),
            )

    raise ScanSnapError("scanner not visible on host usb bus")


def getDomainXml(vmName: str, inactive: bool = False) -> ET.Element:
    command = ["virsh", "dumpxml", vmName]
    if inactive:
        command.append("--inactive")

    result = runCommand(command)
    try:
        return ET.fromstring(result.stdout)
    except ET.ParseError as exc:
        raise ScanSnapError(f"unable to parse domain xml: {exc}") from exc


def extractScanSnapHostdev(domainRoot: ET.Element) -> Optional[ET.Element]:
    for hostdev in domainRoot.findall(".//hostdev[@type='usb']"):
        source = hostdev.find("source")
        if source is None:
            continue

        vendor = source.find("vendor")
        product = source.find("product")
        if vendor is None or product is None:
            continue

        if vendor.attrib.get("id", "").lower() == "0x04c5" and product.attrib.get("id", "").lower() == "0x128d":
            return hostdev

    return None


def extractUsbAddress(hostdev: Optional[ET.Element]) -> Optional[UsbAddress]:
    if hostdev is None:
        return None

    source = hostdev.find("source")
    if source is None:
        return None

    address = source.find("address")
    if address is None:
        return None

    busValue = address.attrib.get("bus")
    deviceValue = address.attrib.get("device")
    if not busValue or not deviceValue:
        return None

    try:
        return UsbAddress(bus=int(busValue), device=int(deviceValue))
    except ValueError:
        return None


def buildAttachXml(bus: Optional[int] = None, device: Optional[int] = None) -> str:
    hostdev = ET.Element(
        "hostdev",
        {"mode": "subsystem", "type": "usb", "managed": "yes"},
    )
    source = ET.SubElement(hostdev, "source")
    ET.SubElement(source, "vendor", {"id": "0x04c5"})
    ET.SubElement(source, "product", {"id": "0x128d"})

    if bus is not None and device is not None:
        ET.SubElement(source, "address", {"bus": str(bus), "device": str(device)})

    return ET.tostring(hostdev, encoding="unicode")


def buildDetachXmlFromHostdev(hostdev: ET.Element) -> str:
    return ET.tostring(hostdev, encoding="unicode")


def writeTempXml(xmlText: str) -> Path:
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-8") as tempFile:
        tempFile.write(xmlText)
        tempFile.flush()
        return Path(tempFile.name)


def attachDevice(vmName: str, xmlText: str, live: bool = False, config: bool = False) -> None:
    xmlPath = writeTempXml(xmlText)
    try:
        command = ["virsh", "attach-device", vmName, str(xmlPath)]
        if live:
            command.append("--live")
        if config:
            command.append("--config")
        runCommand(command)
    finally:
        xmlPath.unlink(missing_ok=True)


def detachDevice(vmName: str, xmlText: str, live: bool = False, config: bool = False) -> None:
    xmlPath = writeTempXml(xmlText)
    try:
        command = ["virsh", "detach-device", vmName, str(xmlPath)]
        if live:
            command.append("--live")
        if config:
            command.append("--config")
        runCommand(command, check=False)
    finally:
        xmlPath.unlink(missing_ok=True)


def attachScannerToVm(vmName: str, persist: bool) -> None:
    logStep("checking host for scansnap s1300i...")
    hostScanner = getHostScanner()
    logValue("host scanner", hostScanner.rawLine)
    logValue("current host usb address", f"bus={hostScanner.bus} device={hostScanner.device}")

    liveRoot = getDomainXml(vmName)
    liveHostdev = extractScanSnapHostdev(liveRoot)
    liveAddress = extractUsbAddress(liveHostdev)

    if liveAddress is not None:
        logValue("live vm usb address", f"bus={liveAddress.bus} device={liveAddress.device}")
        if liveAddress.bus == hostScanner.bus and liveAddress.device == hostScanner.device:
            logStep("scanner is already attached live with the current bus/device")
        else:
            logStep("detaching stale live scansnap attachment...")
            detachDevice(vmName, buildDetachXmlFromHostdev(liveHostdev), live=True)  # type: ignore[arg-type]

            logStep("attaching current scanner to live vm...")
            attachDevice(
                vmName,
                buildAttachXml(bus=hostScanner.bus, device=hostScanner.device),
                live=True,
            )
    else:
        logStep("no live scansnap attachment found; attaching current scanner...")
        attachDevice(
            vmName,
            buildAttachXml(bus=hostScanner.bus, device=hostScanner.device),
            live=True,
        )

    if persist:
        logStep("updating persistent vm config...")
        persistentXml = buildAttachXml()
        detachDevice(vmName, persistentXml, config=True)
        attachDevice(vmName, persistentXml, config=True)
        logStep("persistent config updated")


def dropScannerFromVm(vmName: str, persist: bool) -> None:
    logStep("drop mode: detaching scanner from vm...")

    liveRoot = getDomainXml(vmName)
    liveHostdev = extractScanSnapHostdev(liveRoot)
    if liveHostdev is None:
        raise ScanSnapError("no live scansnap device found in vm")

    detachDevice(vmName, buildDetachXmlFromHostdev(liveHostdev), live=True)
    logStep("scanner detached from vm (returned to linux)")

    if persist:
        logStep("removing persistent vm config...")
        detachDevice(vmName, buildAttachXml(), config=True)
        logStep("persistent config updated")


def main() -> int:
    requireCommand("virsh")
    requireCommand("lsusb")

    args = parseArguments()

    if args.show_config:
        configuredVmName = getConfiguredVmName()
        if configuredVmName:
            logValue("config vmName", configuredVmName)
            logValue("config path", str(CONFIG_PATH))
        else:
            logValue("config vmName", "<not set>")
            logValue("config path", str(CONFIG_PATH))
        return 0

    if args.clear_config:
        clearConfig()
        return 0

    vmName = resolveVmName(args.vmName)

    logValue("target vm", vmName)
    assertVmRunning(vmName)

    if args.drop:
        dropScannerFromVm(vmName, args.persist)
    else:
        attachScannerToVm(vmName, args.persist)

    logStep("done")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ScanSnapError as exc:
        logger.error(f"ERROR: {exc}")
        sys.exit(1)
