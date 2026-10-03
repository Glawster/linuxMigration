"""Learn conservative sender-to-folder evidence from the local mail archive."""

from collections import Counter, defaultdict
from email.parser import BytesHeaderParser
from email.utils import getaddresses
from pathlib import Path
import re


def archiveSenderIndex(archive: dict) -> dict:
    """Return sender -> canonical-folder counts without reading message bodies."""
    index = defaultdict(Counter)
    if not archive.get("available") or not archive.get("complete", True):
        return {}
    for folder in archive.get("folders", []):
        if not folder.get("selectable"):
            continue
        storage = Path(folder["storage"])
        try:
            if archive["format"] == "thunderbird":
                senders = _mboxSenders(storage)
            else:
                senders = _maildirSenders(storage)
            for sender in senders:
                index[sender][folder["path"]] += 1
        except OSError:
            continue
    return {sender: dict(counts) for sender, counts in index.items()}


def senderClassify(sender: str | None, mappings: list[dict], index: dict) -> dict | None:
    """Classify a sender using archive history, then a unique folder-name match."""
    sender = _addressNormalize(sender)
    if not sender:
        return None

    history = index.get(sender, {})
    if history:
        ordered = sorted(history.items(), key=lambda item: (-item[1], item[0]))
        if len(ordered) == 1:
            folder, count = ordered[0]
            mapping = _mappingFor(folder, mappings)
            if mapping:
                return dict(
                    mapping=mapping,
                    method="archiveSenderExact",
                    confidence="high",
                    reason=(
                        f"{count} archived message"
                        f'{"s" if count != 1 else ""} from {sender} are filed in {folder}'
                    ),
                    evidenceCount=count,
                )
        elif ordered[0][1] >= 3 and ordered[0][1] >= ordered[1][1] * 3:
            folder, count = ordered[0]
            mapping = _mappingFor(folder, mappings)
            if mapping:
                return dict(
                    mapping=mapping,
                    method="archiveSenderMajority",
                    confidence="high",
                    reason=(
                        f"{count} archived messages from {sender} are filed in {folder}; "
                        f"next-best folder has {ordered[1][1]}"
                    ),
                    evidenceCount=count,
                )

    senderToken = re.sub(r"[^a-z0-9]", "", sender.lower())
    candidates = []
    for mapping in mappings:
        leaf = mapping["canonical"].rsplit("/", 1)[-1]
        token = re.sub(r"[^a-z0-9]", "", leaf.lower())
        if len(token) >= 4 and token in senderToken:
            candidates.append((mapping, leaf))
    if len(candidates) == 1:
        mapping, leaf = candidates[0]
        return dict(
            mapping=mapping,
            method="senderContainsFolderName",
            confidence="medium",
            reason=f"Sender address contains archive folder name '{leaf}'",
            evidenceCount=0,
        )
    return None


def _mappingFor(canonical: str, mappings: list[dict]) -> dict | None:
    matches = [mapping for mapping in mappings if mapping["canonical"] == canonical]
    return matches[0] if len(matches) == 1 else None


def _addressNormalize(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    addresses = [address.lower() for _, address in getaddresses([value]) if address]
    return addresses[0] if len(addresses) == 1 else None


def _mboxSenders(path: Path):
    """Yield From addresses from an mbox while stopping at each header/body boundary."""
    if not path.is_file():
        return
    with path.open("rb") as stream:
        header = []
        collecting = False
        for line in stream:
            if line.startswith(b"From "):
                if header:
                    sender = _headerSender(b"".join(header))
                    if sender:
                        yield sender
                header = []
                collecting = True
                continue
            if not collecting:
                continue
            if line in (b"\n", b"\r\n"):
                sender = _headerSender(b"".join(header))
                if sender:
                    yield sender
                header = []
                collecting = False
            else:
                header.append(line)
        if header:
            sender = _headerSender(b"".join(header))
            if sender:
                yield sender


def _maildirSenders(path: Path):
    for leaf in ("cur", "new"):
        directory = path / leaf
        if not directory.is_dir():
            continue
        for message in directory.iterdir():
            if not message.is_file() or message.is_symlink():
                continue
            header = []
            with message.open("rb") as stream:
                for line in stream:
                    if line in (b"\n", b"\r\n"):
                        break
                    header.append(line)
            sender = _headerSender(b"".join(header))
            if sender:
                yield sender


def _headerSender(header: bytes) -> str | None:
    message = BytesHeaderParser().parsebytes(header)
    values = message.get_all("From", [])
    if len(values) != 1:
        return None
    return _addressNormalize(values[0])
