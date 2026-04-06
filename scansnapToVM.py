#!/usr/bin/env python3
"""
scansnapToVM.py

Attach or detach a Fujitsu ScanSnap S1300i USB device to/from a running
libvirt / virt-manager virtual machine.

By default this runs as a dry-run and only shows what would be done.
Pass --confirm to actually attach or detach the device.

Usage:
    python3 scansnapToVM.py [vmName] [--confirm] [--drop] [--persist]
    python3 scansnapToVM.py --show-config
    python3 scansnapToVM.py --clear-config

Examples:
    python3 scansnapToVM.py win11                    # dry-run attach to win11
    python3 scansnapToVM.py win11 --confirm          # attach to win11
    python3 scansnapToVM.py --drop --confirm         # detach from running VM
    python3 scansnapToVM.py win11 --persist --confirm
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

try:
    from organiseMyProjects.logUtils import getLogger  # type: ignore
except ImportError:
    import logging as _logging

    def getLogger(name: str, **kwargs) -> _logging.Logger:  # type: ignore[misc]
        """Minimal fallback logger when organiseMyProjects is unavailable."""
        _logger = _logging.getLogger(name)
        if not _logger.handlers:
            _h = _logging.StreamHandler()
            _h.setFormatter(_logging.Formatter("%(message)s"))
            _logger.addHandler(_h)
            _logger.setLevel(_logging.INFO)
        return _logger


CONFIG_DIR = Path.home() / ".config" / "scansnapToVM"
CONFIG_PATH = CONFIG_DIR / "config.json"

logger = getLogger("scansnapToVM")


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
        description=(
            "Attach or detach a ScanSnap S1300i to/from a running libvirt VM. "
            "Runs as a dry-run by default; pass --confirm to execute changes."
        )
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
        "--confirm",
        dest="confirm",
        action="store_true",
        help="execute changes (default is dry-run)",
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
    logger.info("...config cleared: %s", str(CONFIG_PATH))


def getConfiguredVmName() -> str:
    config = loadConfig()
    vmName = config.get("vmName", "").strip()
    return vmName


def saveConfiguredVmName(vmName: str) -> None:
    config = loadConfig()
    config["vmName"] = vmName
    saveConfig(config)
    logger.info("...config vmName: %s", vmName)
    logger.info("...config path: %s", str(CONFIG_PATH))


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


def attachScannerToVm(vmName: str, persist: bool, dryRun: bool) -> None:
    prefix = "...[]" if dryRun else "..."
    logger.info("%s checking host for scansnap s1300i...", prefix)
    hostScanner = getHostScanner()
    logger.info("...host scanner: %s", hostScanner.rawLine)
    logger.info("...current host usb address: bus=%d device=%d", hostScanner.bus, hostScanner.device)

    liveRoot = getDomainXml(vmName)
    liveHostdev = extractScanSnapHostdev(liveRoot)
    liveAddress = extractUsbAddress(liveHostdev)

    if liveAddress is not None:
        logger.info("...live vm usb address: bus=%d device=%d", liveAddress.bus, liveAddress.device)
        if liveAddress.bus == hostScanner.bus and liveAddress.device == hostScanner.device:
            logger.info("...scanner is already attached live with the current bus/device")
        else:
            logger.info("%s detaching stale live scansnap attachment...", prefix)
            if not dryRun:
                detachDevice(vmName, buildDetachXmlFromHostdev(liveHostdev), live=True)  # type: ignore[arg-type]

            logger.info("%s attaching current scanner to live vm...", prefix)
            if not dryRun:
                attachDevice(
                    vmName,
                    buildAttachXml(bus=hostScanner.bus, device=hostScanner.device),
                    live=True,
                )
    else:
        logger.info("%s no live scansnap attachment found; attaching current scanner...", prefix)
        if not dryRun:
            attachDevice(
                vmName,
                buildAttachXml(bus=hostScanner.bus, device=hostScanner.device),
                live=True,
            )

    if persist:
        logger.info("%s updating persistent vm config...", prefix)
        if not dryRun:
            persistentXml = buildAttachXml()
            detachDevice(vmName, persistentXml, config=True)
            attachDevice(vmName, persistentXml, config=True)
        logger.info("%s persistent config updated", prefix)


def dropScannerFromVm(vmName: str, persist: bool, dryRun: bool) -> None:
    prefix = "...[]" if dryRun else "..."
    logger.info("%s drop mode: detaching scanner from vm...", prefix)

    liveRoot = getDomainXml(vmName)
    liveHostdev = extractScanSnapHostdev(liveRoot)
    if liveHostdev is None:
        raise ScanSnapError("no live scansnap device found in vm")

    if not dryRun:
        detachDevice(vmName, buildDetachXmlFromHostdev(liveHostdev), live=True)
    logger.info("%s scanner detached from vm (returned to linux)", prefix)

    if persist:
        logger.info("%s removing persistent vm config...", prefix)
        if not dryRun:
            detachDevice(vmName, buildAttachXml(), config=True)
        logger.info("%s persistent config updated", prefix)


def main() -> int:
    requireCommand("virsh")
    requireCommand("lsusb")

    args = parseArguments()
    dryRun = not args.confirm

    global logger
    logger = getLogger("scansnapToVM", includeConsole=True, dryRun=dryRun)

    if args.show_config:
        configuredVmName = getConfiguredVmName()
        if configuredVmName:
            logger.info("...config vmName: %s", configuredVmName)
            logger.info("...config path: %s", str(CONFIG_PATH))
        else:
            logger.info("...config vmName: <not set>")
            logger.info("...config path: %s", str(CONFIG_PATH))
        return 0

    if args.clear_config:
        clearConfig()
        return 0

    vmName = resolveVmName(args.vmName)

    logger.info("...target vm: %s", vmName)
    assertVmRunning(vmName)

    if args.drop:
        dropScannerFromVm(vmName, args.persist, dryRun)
    else:
        attachScannerToVm(vmName, args.persist, dryRun)

    logger.info("...done")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ScanSnapError as exc:
        logger.error(f"ERROR: {exc}")
        sys.exit(1)
