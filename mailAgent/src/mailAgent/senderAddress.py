"""Normalize sender addresses, including Apple Hide My Email relay senders."""

import re
from email.utils import getaddresses


_RELAY_SUFFIX = re.compile(
    r"_(?=[a-z0-9]*\d)[a-z0-9]{6,}_(?=[a-z0-9]*\d)[a-z0-9]{6,}$",
    re.IGNORECASE,
)


def senderNormalize(value: str | None) -> str | None:
    """Return one normalized sender address, decoding known iCloud relay form."""
    if not isinstance(value, str):
        return None
    addresses = [address.lower() for _, address in getaddresses([value]) if address]
    if len(addresses) != 1:
        return None
    return senderRelayDecode(addresses[0])


def senderRelayDecode(address: str) -> str:
    """Decode Apple's observable Hide My Email relay sender convention.

    Example:
      bmwuk_at_service_bmw_com_x...@icloud.com
      -> bmwuk@service.bmw.com

    Only the constrained @icloud.com relay form is rewritten.
    """
    address = address.strip().lower()
    local, separator, domain = address.rpartition("@")
    if separator != "@" or domain != "icloud.com" or "_at_" not in local:
        return address

    originalLocal, originalDomain = local.split("_at_", 1)
    originalDomain = _RELAY_SUFFIX.sub("", originalDomain)
    if not originalLocal or not originalDomain or "_" not in originalDomain:
        return address

    decodedDomain = originalDomain.replace("_", ".")
    if not _domainValid(decodedDomain):
        return address
    return f"{originalLocal}@{decodedDomain}"


def _domainValid(domain: str) -> bool:
    labels = domain.split(".")
    return (
        len(labels) >= 2
        and all(
            label
            and label[0].isalnum()
            and label[-1].isalnum()
            and all(char.isalnum() or char == "-" for char in label)
            for label in labels
        )
    )
