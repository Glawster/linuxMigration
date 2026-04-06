"""
tests/test_scansnapToVM.py

Unit tests for scansnapToVM.py pure-logic functions.
These tests do not require virsh or lsusb to be installed.
"""

import json
import xml.etree.ElementTree as ET

import pytest

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scansnapToVM import (
    CONFIG_PATH,
    CONFIG_DIR,
    ScanSnapError,
    UsbAddress,
    HostScanner,
    buildAttachXml,
    buildDetachXmlFromHostdev,
    extractScanSnapHostdev,
    extractUsbAddress,
    loadConfig,
    saveConfig,
    clearConfig,
    getConfiguredVmName,
    saveConfiguredVmName,
)


# ---------------------------------------------------------------------------
# buildAttachXml
# ---------------------------------------------------------------------------


class TestBuildAttachXml:
    def test_without_address(self):
        """XML must contain vendor and product IDs but no address element."""
        xml = buildAttachXml()
        root = ET.fromstring(xml)
        assert root.tag == "hostdev"
        assert root.attrib["type"] == "usb"
        assert root.attrib["managed"] == "yes"
        source = root.find("source")
        assert source is not None
        assert source.find("vendor").attrib["id"] == "0x04c5"
        assert source.find("product").attrib["id"] == "0x128d"
        assert source.find("address") is None

    def test_with_address(self):
        """XML must include address element when bus and device are provided."""
        xml = buildAttachXml(bus=3, device=7)
        root = ET.fromstring(xml)
        source = root.find("source")
        address = source.find("address")
        assert address is not None
        assert address.attrib["bus"] == "3"
        assert address.attrib["device"] == "7"

    def test_without_only_bus(self):
        """Address element must be absent when only bus is provided."""
        xml = buildAttachXml(bus=1)
        root = ET.fromstring(xml)
        assert root.find("source/address") is None

    def test_without_only_device(self):
        """Address element must be absent when only device is provided."""
        xml = buildAttachXml(device=5)
        root = ET.fromstring(xml)
        assert root.find("source/address") is None


# ---------------------------------------------------------------------------
# extractScanSnapHostdev
# ---------------------------------------------------------------------------


def _makeDomainXml(vendor_id: str = "0x04c5", product_id: str = "0x128d") -> ET.Element:
    """Build a minimal domain XML element with one USB hostdev entry."""
    xml = f"""
    <domain>
      <devices>
        <hostdev mode="subsystem" type="usb" managed="yes">
          <source>
            <vendor id="{vendor_id}"/>
            <product id="{product_id}"/>
          </source>
        </hostdev>
      </devices>
    </domain>
    """
    return ET.fromstring(xml)


class TestExtractScanSnapHostdev:
    def test_found(self):
        """Returns the hostdev element when the correct scanner is present."""
        root = _makeDomainXml()
        hostdev = extractScanSnapHostdev(root)
        assert hostdev is not None
        assert hostdev.tag == "hostdev"

    def test_not_found_wrong_vendor(self):
        """Returns None when vendor ID does not match."""
        root = _makeDomainXml(vendor_id="0x1234")
        assert extractScanSnapHostdev(root) is None

    def test_not_found_wrong_product(self):
        """Returns None when product ID does not match."""
        root = _makeDomainXml(product_id="0x9999")
        assert extractScanSnapHostdev(root) is None

    def test_case_insensitive(self):
        """Vendor / product comparison is case-insensitive."""
        root = _makeDomainXml(vendor_id="0X04C5", product_id="0X128D")
        assert extractScanSnapHostdev(root) is not None

    def test_empty_domain(self):
        """Returns None when domain has no hostdev elements."""
        root = ET.fromstring("<domain><devices/></domain>")
        assert extractScanSnapHostdev(root) is None

    def test_non_usb_hostdev_ignored(self):
        """Returns None for non-USB hostdev entries."""
        xml = """
        <domain>
          <devices>
            <hostdev mode="subsystem" type="pci" managed="yes">
              <source>
                <vendor id="0x04c5"/>
                <product id="0x128d"/>
              </source>
            </hostdev>
          </devices>
        </domain>
        """
        root = ET.fromstring(xml)
        assert extractScanSnapHostdev(root) is None


# ---------------------------------------------------------------------------
# extractUsbAddress
# ---------------------------------------------------------------------------


def _makeHostdevWithAddress(bus: str = "3", device: str = "7") -> ET.Element:
    xml = f"""
    <hostdev mode="subsystem" type="usb" managed="yes">
      <source>
        <vendor id="0x04c5"/>
        <product id="0x128d"/>
        <address bus="{bus}" device="{device}"/>
      </source>
    </hostdev>
    """
    return ET.fromstring(xml)


class TestExtractUsbAddress:
    def test_returns_address(self):
        """Parses bus and device numbers correctly."""
        hostdev = _makeHostdevWithAddress(bus="3", device="7")
        addr = extractUsbAddress(hostdev)
        assert addr == UsbAddress(bus=3, device=7)

    def test_none_input(self):
        """Returns None when hostdev is None."""
        assert extractUsbAddress(None) is None

    def test_no_address_element(self):
        """Returns None when there is no <address> element in <source>."""
        xml = """
        <hostdev mode="subsystem" type="usb" managed="yes">
          <source>
            <vendor id="0x04c5"/>
            <product id="0x128d"/>
          </source>
        </hostdev>
        """
        hostdev = ET.fromstring(xml)
        assert extractUsbAddress(hostdev) is None

    def test_non_numeric_bus(self):
        """Returns None when bus attribute is not a valid integer."""
        hostdev = _makeHostdevWithAddress(bus="bogus", device="7")
        assert extractUsbAddress(hostdev) is None

    def test_missing_bus_attribute(self):
        """Returns None when bus attribute is missing from <address>."""
        xml = """
        <hostdev mode="subsystem" type="usb" managed="yes">
          <source>
            <vendor id="0x04c5"/>
            <product id="0x128d"/>
            <address device="7"/>
          </source>
        </hostdev>
        """
        assert extractUsbAddress(ET.fromstring(xml)) is None


# ---------------------------------------------------------------------------
# buildDetachXmlFromHostdev
# ---------------------------------------------------------------------------


class TestBuildDetachXmlFromHostdev:
    def test_round_trips_element(self):
        """Serialises the element to XML string that can be parsed back."""
        hostdev = _makeHostdevWithAddress()
        xml = buildDetachXmlFromHostdev(hostdev)
        root = ET.fromstring(xml)
        assert root.tag == "hostdev"
        assert root.find("source/vendor").attrib["id"] == "0x04c5"


# ---------------------------------------------------------------------------
# config helpers
# ---------------------------------------------------------------------------


class TestConfigHelpers:
    def test_load_config_missing_file(self, tmp_path, monkeypatch):
        """loadConfig returns empty dict when config file does not exist."""
        monkeypatch.setattr("scansnapToVM.CONFIG_PATH", tmp_path / "missing.json")
        assert loadConfig() == {}

    def test_save_and_load_config(self, tmp_path, monkeypatch):
        """saveConfig writes JSON; loadConfig reads it back."""
        monkeypatch.setattr("scansnapToVM.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("scansnapToVM.CONFIG_PATH", tmp_path / "config.json")
        saveConfig({"vmName": "win11"})
        assert loadConfig() == {"vmName": "win11"}

    def test_load_config_invalid_json(self, tmp_path, monkeypatch):
        """loadConfig raises ScanSnapError for corrupt JSON."""
        cfg = tmp_path / "config.json"
        cfg.write_text("NOT JSON", encoding="utf-8")
        monkeypatch.setattr("scansnapToVM.CONFIG_PATH", cfg)
        with pytest.raises(ScanSnapError, match="unable to read config"):
            loadConfig()

    def test_clear_config(self, tmp_path, monkeypatch):
        """clearConfig removes the config file."""
        cfg = tmp_path / "config.json"
        cfg.write_text("{}", encoding="utf-8")
        monkeypatch.setattr("scansnapToVM.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("scansnapToVM.CONFIG_PATH", cfg)
        clearConfig()
        assert not cfg.exists()

    def test_clear_config_no_file(self, tmp_path, monkeypatch):
        """clearConfig is a no-op when config file does not exist."""
        cfg = tmp_path / "config.json"
        monkeypatch.setattr("scansnapToVM.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("scansnapToVM.CONFIG_PATH", cfg)
        clearConfig()  # should not raise

    def test_save_and_get_configured_vm_name(self, tmp_path, monkeypatch):
        """saveConfiguredVmName persists; getConfiguredVmName retrieves."""
        monkeypatch.setattr("scansnapToVM.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("scansnapToVM.CONFIG_PATH", tmp_path / "config.json")
        saveConfiguredVmName("myVM")
        assert getConfiguredVmName() == "myVM"

    def test_get_configured_vm_name_empty(self, tmp_path, monkeypatch):
        """getConfiguredVmName returns empty string when not set."""
        monkeypatch.setattr("scansnapToVM.CONFIG_PATH", tmp_path / "missing.json")
        assert getConfiguredVmName() == ""
