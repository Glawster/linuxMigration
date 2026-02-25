#!/usr/bin/env python3
"""
mediaAudit.py

Audit (and optionally apply *only safe* moves/renames) in a media tree.

Phase 1: collect data and identify what is NOT in the expected place/pattern.
Phase 2A: plan (and optionally apply) author-folder canonicalisation for Audiobooks.

Safety model:
- planning is always safe
- any filesystem changes require --confirm
- without --confirm, the script runs in dry-run mode (logs what it would do)

Conventions:
- camelCase identifiers
- logging messages mostly lowercase (ERROR in Sentence Case)

Examples:
  python3 mediaAudit.py --root /mnt/home --report /mnt/home/mediaAudit.json
  python3 mediaAudit.py --root /mnt/home --move-loose-audiobooks --report /mnt/home/mediaAudit.json
  python3 mediaAudit.py --root /mnt/home --plan-author-renames --report /mnt/home/mediaAudit.json
  python3 mediaAudit.py --root /mnt/home --apply-author-renames --confirm
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass, asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from organiseMyProjects.logUtils import getLogger  # type: ignore


# -----------------------------
# models
# -----------------------------

AUDIO_EXTS = {".mp3", ".m4b", ".m4a", ".aax", ".aac", ".flac", ".ogg", ".wav"}
EBOOK_EXTS = {".epub", ".mobi", ".azw", ".azw3", ".pdf", ".cbz", ".cbr", ".djvu"}

AUTHOR_DIR_PATTERN = re.compile(r"^.+,\s+.+$")  # "Surname, Firstname"

# simple suffix heuristic: keep common suffixes attached to surname
SURNAME_SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "v"}


@dataclass
class PatternIssue:
    issueType: str
    path: str
    detail: str


@dataclass
class MovePlanItem:
    action: str
    src: str
    dst: str
    reason: str
    executed: bool = False
    error: Optional[str] = None


@dataclass
class RenamePlanItem:
    action: str  # "rename"
    src: str
    dst: str
    reason: str
    collision: bool = False
    executed: bool = False
    error: Optional[str] = None


@dataclass
class MergeGroup:
    canonical: str
    sources: List[str]
    reason: str

@dataclass
class NonAuthorFolder:
    path: str
    reason: str
@dataclass
class AuditReport:
    tool: str
    timestampUtc: str
    root: str
    dryRun: bool
    stats: Dict[str, int]
    issues: List[PatternIssue]
    plannedMoves: List[MovePlanItem]
    plannedRenames: List[RenamePlanItem]
    mergeGroups: List[MergeGroup]
    nonAuthorFolders: List[NonAuthorFolder] 


# -----------------------------
# helpers
# -----------------------------

NON_AUTHOR_KEYWORDS = {
    "collection", "collections", "complete", "mega", "pack", "box set", "boxset",
    "series", "anthology", "various", "various authors",
    "horus heresy", "warhammer", "40k", "mba", "pocket", "times",
    "the bible", "bible", "new york times",
}

def looksLikeNonAuthorFolder(folderName: str) -> Optional[str]:
    """
    Return a reason string if this folder is likely NOT an author folder.
    Strict mode: we only rename things we are confident are authors.
    """
    n = normaliseSpaces(folderName)
    low = n.lower()

    # ignore buckets
    if n.startswith("_"):
        return "bucket folder"

    # obvious non-author patterns
    if any(ch.isdigit() for ch in n):
        return "contains digits"
    if " - " in n or " — " in n:
        return "contains dash-separated title"
    if ":" in n:
        return "contains ':'"
    if "/" in n or "\\" in n:
        return "contains path separator"

    for kw in NON_AUTHOR_KEYWORDS:
        if kw in low:
            return f"keyword match: {kw}"

    # Too many words is often a title/collection, not a person name
    # (e.g. 'New York Times Pocket MBA', 'Kurt Vonnegut Mega Pack')
    if "," not in n and len(n.split()) >= 5:
        return "too many words for author (>=5) without comma"

    return None

def nowUtcIso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def isAudioFile(p: Path) -> bool:
    return p.is_file() and p.suffix.lower() in AUDIO_EXTS


def isEbookFile(p: Path) -> bool:
    return p.is_file() and p.suffix.lower() in EBOOK_EXTS


def ensureDir(path: Path, logger, dryRun: bool) -> None:
    if path.exists():
        return
    if dryRun:
        logger.info("...would create directory: %s", str(path))
        return
    logger.info("...creating directory: %s", str(path))
    path.mkdir(parents=True, exist_ok=True)


def movePath(src: Path, dst: Path, logger, dryRun: bool) -> Tuple[bool, Optional[str]]:
    try:
        if dryRun:
            logger.info("...dry-run move: %s -> %s", str(src), str(dst))
            return True, None
        ensureDir(dst.parent, logger, dryRun=False)
        logger.info("...moving: %s -> %s", str(src), str(dst))
        shutil.move(str(src), str(dst))
        return True, None
    except Exception as e:
        logger.error("Move failed: %s", str(e))
        return False, str(e)


def renamePath(src: Path, dst: Path, logger, dryRun: bool) -> Tuple[bool, Optional[str]]:
    try:
        if dryRun:
            logger.info("...dry-run rename: %s -> %s", str(src), str(dst))
            return True, None
        ensureDir(dst.parent, logger, dryRun=False)
        logger.info("...renaming: %s -> %s", str(src), str(dst))
        src.rename(dst)
        return True, None
    except Exception as e:
        logger.error("Rename failed: %s", str(e))
        return False, str(e)

def mergeAuthorFolders(srcDir: Path, dstDir: Path, logger, dryRun: bool) -> Tuple[int, int, int]:
    """
    Move contents of srcDir into dstDir.
    Returns: (movedCount, skippedCount, failedCount)
    - skips if destination child already exists
    - removes srcDir if empty after merge (and not dryRun)
    """
    movedCount = 0
    skippedCount = 0
    failedCount = 0

    if not srcDir.exists() or not srcDir.is_dir():
        return movedCount, skippedCount, failedCount

    ensureDir(dstDir, logger, dryRun)

    for child in sorted(srcDir.iterdir(), key=lambda p: p.name.lower()):
        dstChild = dstDir / child.name

        if dstChild.exists():
            logger.info("...merge skip (exists)...: %s", str(dstChild))
            skippedCount += 1
            continue

        ok, err = movePath(child, dstChild, logger, dryRun)
        if ok:
            if not dryRun:
                movedCount += 1
            else:
                # in dry-run we still count as "would move"
                movedCount += 1
        else:
            failedCount += 1
            logger.error("Merge failed: %s", err or "unknown error")

    # remove src if empty
    try:
        remaining = list(srcDir.iterdir())
        if len(remaining) == 0:
            if dryRun:
                logger.info("...dry-run remove empty dir...: %s", str(srcDir))
            else:
                logger.info("...removing empty dir...: %s", str(srcDir))
                srcDir.rmdir()
    except Exception as e:
        logger.error("Merge cleanup failed: %s", str(e))
        failedCount += 1

    return movedCount, skippedCount, failedCount

def normaliseSpaces(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def normaliseInitials(given: str) -> str:
    """
    Convert spaced initials in the given-name part:
      "George R. R." -> "George R.R."
      "Iain M"       -> "Iain M."
      "H. G."        -> "H.G."
    Leaves normal words alone.
    """
    tokens = [t for t in normaliseSpaces(given).split(" ") if t]
    out: List[str] = []

    i = 0
    while i < len(tokens):
        t = tokens[i]

        # recognise "R" or "R." as an initial token
        def isInitialTok(x: str) -> bool:
            x2 = x.strip()
            if len(x2) == 1 and x2.isalpha():
                return True
            if len(x2) == 2 and x2[0].isalpha() and x2[1] == ".":
                return True
            return False

        if isInitialTok(t):
            # consume a run of consecutive initials and collapse them
            initials = []
            while i < len(tokens) and isInitialTok(tokens[i]):
                x = tokens[i].strip()
                letter = x[0].upper()
                initials.append(letter)
                i += 1

            # "R","R" -> "R.R."
            out.append(".".join(initials) + ".")
            continue

        # normal token
        out.append(t)
        i += 1

    return " ".join(out)

def splitAuthorNameNoComma(name: str) -> Tuple[str, str]:
    """
    Convert 'George R. R. Martin' -> ('Martin', 'George R. R.')
    Option A: preserve punctuation/initials as-is; only rearrange.

    Heuristics:
    - last token is surname
    - if last token is a suffix (jr/sr/ii/iii/iv/v), surname becomes 'PrevToken Suffix'
    """
    tokens = [t for t in normaliseSpaces(name).split(" ") if t]
    if not tokens:
        return "", ""

    if len(tokens) == 1:
        return tokens[0], ""

    last = tokens[-1]
    lastLower = last.lower()
    if lastLower in SURNAME_SUFFIXES and len(tokens) >= 3:
        surname = f"{tokens[-2]} {tokens[-1]}"
        given = " ".join(tokens[:-2])
        return surname, given

    surname = last
    given = " ".join(tokens[:-1])
    return surname, given

def canonicalAuthorFolderName(name: str) -> str:
    """
    Canonical author folder:
      - Ensure format "Surname, Given Names"
      - Normalise initials in Given Names:
          "George R. R." -> "George R.R."
          "Iain M" -> "Iain M."
    """
    n = normaliseSpaces(name)
    if not n:
        return n

    # If already has comma, still normalise initials in the given part
    if "," in n:
        parts = [p.strip() for p in n.split(",", 1)]
        surname = parts[0]
        given = parts[1] if len(parts) > 1 else ""
        given = normaliseInitials(given)
        if given:
            return f"{surname}, {given}"
        return surname

    # No comma: split into surname + given, then normalise initials
    surname, given = splitAuthorNameNoComma(n)
    surname = normaliseSpaces(surname)
    given = normaliseInitials(given)

    if surname and given:
        return f"{surname}, {given}"
    if surname:
        return surname
    return n


# -----------------------------
# auditors
# -----------------------------

def auditAudiobooks(audiobooksDir: Path, logger) -> Tuple[List[PatternIssue], Dict[str, int], List[Path], List[Path]]:
    issues: List[PatternIssue] = []
    stats: Dict[str, int] = {
        "audiobooksTopDirs": 0,
        "audiobooksAuthorDirsGood": 0,
        "audiobooksAuthorDirsBad": 0,
        "audiobooksLooseAudioFiles": 0,
        "audiobooksDesktopIni": 0,
        "audiobooksNestedAudiobookFolder": 0,
    }
    looseAudioFiles: List[Path] = []
    authorDirs: List[Path] = []

    if not audiobooksDir.exists():
        issues.append(PatternIssue("missing_dir", str(audiobooksDir), "Audiobooks directory does not exist"))
        return issues, stats, looseAudioFiles, authorDirs

    for child in sorted(audiobooksDir.iterdir(), key=lambda p: p.name.lower()):
        if child.is_dir():
            stats["audiobooksTopDirs"] += 1
            authorDirs.append(child)

            if child.name.lower() == "audiobook":
                stats["audiobooksNestedAudiobookFolder"] += 1
                issues.append(PatternIssue(
                    issueType="misnamed_folder",
                    path=str(child),
                    detail="folder named 'Audiobook' found inside Audiobooks; likely legacy/mistake"
                ))

            # ignore underscore buckets for author pattern counts
            if not child.name.startswith("_"):
                if AUTHOR_DIR_PATTERN.match(child.name):
                    stats["audiobooksAuthorDirsGood"] += 1
                else:
                    stats["audiobooksAuthorDirsBad"] += 1
                    issues.append(PatternIssue(
                        issueType="author_dir_not_in_pattern",
                        path=str(child),
                        detail="expected author folder 'Surname, Firstname' (contains comma)"
                    ))

            desktopIni = child / "desktop.ini"
            if desktopIni.exists():
                stats["audiobooksDesktopIni"] += 1
                issues.append(PatternIssue(
                    issueType="windows_artifact",
                    path=str(desktopIni),
                    detail="desktop.ini detected (safe to delete later)"
                ))

        elif isAudioFile(child):
            stats["audiobooksLooseAudioFiles"] += 1
            looseAudioFiles.append(child)
            issues.append(PatternIssue(
                issueType="loose_audio_file",
                path=str(child),
                detail="audio file is directly under Audiobooks; expected inside author/book folder"
            ))

    logger.info("...audiobooks scanned: %s", str(audiobooksDir))
    return issues, stats, looseAudioFiles, authorDirs


def auditEbooks(ebooksDir: Path, logger) -> Tuple[List[PatternIssue], Dict[str, int]]:
    issues: List[PatternIssue] = []
    stats: Dict[str, int] = {
        "ebooksTopEbookFiles": 0,
        "ebooksWindowsArtifacts": 0,
    }

    if not ebooksDir.exists():
        issues.append(PatternIssue("missing_dir", str(ebooksDir), "eBooks directory does not exist"))
        return issues, stats

    for child in sorted(ebooksDir.iterdir(), key=lambda p: p.name.lower()):
        if child.is_file() and isEbookFile(child):
            stats["ebooksTopEbookFiles"] += 1
            issues.append(PatternIssue(
                issueType="loose_ebook_file",
                path=str(child),
                detail="ebook file is directly under eBooks; consider placing into author/series folders later"
            ))
        if child.name.lower() == "desktop.ini":
            stats["ebooksWindowsArtifacts"] += 1
            issues.append(PatternIssue(
                issueType="windows_artifact",
                path=str(child),
                detail="desktop.ini detected"
            ))

    logger.info("...ebooks scanned: %s", str(ebooksDir))
    return issues, stats


# -----------------------------
# planning
# -----------------------------

def planAuthorRenames(audiobooksDir: Path, authorDirs: List[Path], logger) -> Tuple[List[RenamePlanItem], List[MergeGroup], List[NonAuthorFolder], Dict[str, int]]:
    """
    Phase 2A:
      - build canonical folder name for every author dir
      - propose renames for dirs not already canonical
      - detect collisions (multiple sources map to same canonical)
    """
    plannedRenames: List[RenamePlanItem] = []
    mergeGroups: List[MergeGroup] = []
    stats: Dict[str, int] = {
        "authorRenameCandidates": 0,
        "authorRenamesPlanned": 0,
        "authorRenameCollisions": 0,
        "authorCanonicalUnique": 0,
    }

    canonicalMap: Dict[str, List[Path]] = {}
    for d in authorDirs:
        if not d.is_dir():
            continue
        if d.name.startswith("_"):
            continue
        if d.name.lower() == "audiobook":
            continue

        canonical = canonicalAuthorFolderName(d.name)
        canonicalMap.setdefault(canonical, []).append(d)

    stats["authorCanonicalUnique"] = len(canonicalMap)

    for canonical, sources in sorted(canonicalMap.items(), key=lambda kv: kv[0].lower()):
        if len(sources) > 1:
            stats["authorRenameCollisions"] += 1
            mergeGroups.append(MergeGroup(
                canonical=canonical,
                sources=[str(s) for s in sorted(sources, key=lambda p: p.name.lower())],
                reason="multiple author folders map to the same canonical name"
            ))

    collisionSources = {Path(p).resolve() for g in mergeGroups for p in g.sources}
    for d in sorted(authorDirs, key=lambda p: p.name.lower()):
        if d.name.startswith("_") or d.name.lower() == "audiobook":
            continue

        canonical = canonicalAuthorFolderName(d.name)
        if canonical == d.name:
            continue

        stats["authorRenameCandidates"] += 1
        dst = audiobooksDir / canonical
        collision = (
            (dst.exists() and dst != d.resolve()) 
            or (d.resolve() in collisionSources)
            )
        plannedRenames.append(RenamePlanItem(
            action="rename",
            src=str(d),
            dst=str(dst),
            reason="canonicalise author folder name to 'Surname, Firstname' (option A: preserve punctuation)",
            collision=collision
        ))

    nonAuthorFolders: List[NonAuthorFolder] = []
    filteredAuthorDirs: List[Path] = []

    for d in authorDirs:
        if not d.is_dir():
            continue
        if d.name.startswith("_") or d.name.lower() == "audiobook":
            continue

        reason = looksLikeNonAuthorFolder(d.name)
        if reason:
            nonAuthorFolders.append(NonAuthorFolder(path=str(d), reason=reason))
            continue

        filteredAuthorDirs.append(d)

    logger.info("...author rename candidates...: %d", stats["authorRenameCandidates"])
    logger.info("...author renames planned...: %d", stats["authorRenamesPlanned"])
    logger.info("...author rename collisions...: %d", stats["authorRenameCollisions"])
    logger.info("...non-author folders excluded...: %d", stats["nonAuthorExcluded"])
    return plannedRenames, mergeGroups, nonAuthorFolders, stats


# -----------------------------
# main workflow
# -----------------------------

def buildReport(
    root: Path,
    dryRun: bool,
    logger,
    moveLooseAudiobooks: bool,
    planAuthorRenamesFlag: bool,
    applyAuthorRenamesFlag: bool,
    applyAuthorMergesFlag: bool
) -> AuditReport:
    issues: List[PatternIssue] = []
    plannedMoves: List[MovePlanItem] = []
    plannedRenames: List[RenamePlanItem] = []
    mergeGroups: List[MergeGroup] = []
    nonAuthorFolders: List[NonAuthorFolder] = []
    stats: Dict[str, int] = {
        "issues": 0,
        "plannedMoves": 0,
        "movesExecuted": 0,
        "movesFailed": 0,
        "plannedRenames": 0,
        "nonAuthorExcluded": 0,
        "renamesExecuted": 0,
        "renamesFailed": 0,
        "mergeGroups": 0,
        "mergeMoves": 0,
        "mergeSkips": 0,
        "mergeFails": 0,
    }

    audiobooksDir = root / "Audiobooks"
    ebooksDir = root / "eBooks"

    abIssues, abStats, looseAudioFiles, authorDirs = auditAudiobooks(audiobooksDir, logger)
    ebIssues, ebStats = auditEbooks(ebooksDir, logger)
    issues.extend(abIssues)
    issues.extend(ebIssues)

    if moveLooseAudiobooks and looseAudioFiles:
        unsortedDir = audiobooksDir / "_Unsorted"
        ensureDir(unsortedDir, logger, dryRun)
        for f in looseAudioFiles:
            dst = unsortedDir / f.name
            plannedMoves.append(MovePlanItem(
                action="move",
                src=str(f),
                dst=str(dst),
                reason="loose audiobook file at top level"
            ))

    if planAuthorRenamesFlag or applyAuthorRenamesFlag:
        authorRenames, mergeGroups, nonAuthorFolders, renameStats = planAuthorRenames(audiobooksDir, authorDirs, logger)
        plannedRenames.extend(authorRenames)
        for k, v in renameStats.items():
            stats[k] = v

    for item in plannedMoves:
        ok, err = movePath(Path(item.src), Path(item.dst), logger, dryRun)
        item.executed = ok and (not dryRun)
        item.error = err
        if not dryRun:
            if ok:
                stats["movesExecuted"] += 1
            else:
                stats["movesFailed"] += 1

    if applyAuthorRenamesFlag and plannedRenames:
        for r in plannedRenames:
            if r.collision:
                logger.info("...skipping rename due to collision...: %s -> %s", r.src, r.dst)
                continue
            ok, err = renamePath(Path(r.src), Path(r.dst), logger, dryRun)
            r.executed = ok and (not dryRun)
            r.error = err
            if not dryRun:
                if ok:
                    stats["renamesExecuted"] += 1
                else:
                    stats["renamesFailed"] += 1

    if applyAuthorMergesFlag and mergeGroups:
        for g in mergeGroups:
            canonicalDir = audiobooksDir / g.canonical
            ensureDir(canonicalDir, logger, dryRun)

            for srcStr in g.sources:
                srcDir = Path(srcStr)
                if srcDir.resolve() == canonicalDir.resolve():
                    continue

                logger.info("...merging author...: %s -> %s", str(srcDir), str(canonicalDir))
                moved, skipped, failed = mergeAuthorFolders(srcDir, canonicalDir, logger, dryRun)
                stats["mergeMoves"] += moved
                stats["mergeSkips"] += skipped
                stats["mergeFails"] += failed


    for k, v in abStats.items():
        stats[k] = v
    for k, v in ebStats.items():
        stats[k] = v

    stats["issues"] = len(issues)
    stats["plannedMoves"] = len(plannedMoves)
    stats["plannedRenames"] = len(plannedRenames)
    stats["nonAuthorExcluded"] = len(nonAuthorFolders)
    stats["mergeGroups"] = len(mergeGroups)

    return AuditReport(
        tool="mediaAudit.py",
        timestampUtc=nowUtcIso(),
        root=str(root),
        dryRun=dryRun,
        stats=stats,
        issues=issues,
        plannedMoves=plannedMoves,
        plannedRenames=plannedRenames,
        mergeGroups=mergeGroups,
        nonAuthorFolders=nonAuthorFolders,
    )


def parseArgs() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit media folders and identify items not matching naming/location patterns.")
    parser.add_argument("--root", default="/mnt/home", help="root directory containing Media folders (default: /mnt/home)")
    parser.add_argument("--report", default="", help="write JSON report to this path (optional)")
    parser.add_argument("--confirm", action="store_true", help="allow filesystem changes (without this, actions are simulated)")

    parser.add_argument("--move-loose-audiobooks", action="store_true",
                        help="move audio files directly under Audiobooks/ into Audiobooks/_Unsorted (no renames)")

    parser.add_argument("--plan-author-renames", action="store_true",
                        help="plan canonical author-folder renames under Audiobooks (option A: preserve punctuation)")
    parser.add_argument("--apply-author-renames", action="store_true",
                        help="apply canonical author-folder renames (requires --confirm; collisions are skipped)")
    parser.add_argument("--apply-author-merges", action="store_true",
                        help="merge duplicate author folders (requires --confirm)")

    modeGroup = parser.add_mutually_exclusive_group()
    modeGroup.add_argument("--rename-only", action="store_true", help="apply only renames (skip merges)")
    modeGroup.add_argument("--merge-only", action="store_true", help="apply only merges (skip renames)")

    return parser.parse_args()


def writeReport(report: AuditReport, reportPath: str, logger) -> None:
    if not reportPath:
        return

    outPath = Path(reportPath).expanduser()
    outPath.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        **asdict(report),
        "issues": [asdict(i) for i in report.issues],
        "plannedMoves": [asdict(m) for m in report.plannedMoves],
        "plannedRenames": [asdict(r) for r in report.plannedRenames],
        "mergeGroups": [asdict(g) for g in report.mergeGroups],
        "nonAuthorFolders": [asdict(n) for n in report.nonAuthorFolders],
    }

    tmpPath = outPath.with_suffix(outPath.suffix + ".tmp")
    with tmpPath.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    tmpPath.replace(outPath)
    logger.info("report written...: %s", str(outPath))


def main() -> int:
    args = parseArgs()
    dryRun = not args.confirm

    logger = getLogger(
        name="mediaAudit",
        includeConsole=True
    )

    root = Path(args.root).expanduser().resolve()
    if not root.exists():
        logger.error("Root does not exist: %s", str(root))
        return 2

    logger.info("...starting audit")
    logger.info("...root: %s", str(root))
    logger.info("...dry-run: %s", str(dryRun))
    logger.info("...confirm: %s", str(args.confirm))
    logger.info("...move loose audiobooks: %s", str(args.move_loose_audiobooks))
    logger.info("...plan author renames: %s", str(args.plan_author_renames))
    logger.info("...apply author renames: %s", str(args.apply_author_renames))
    logger.info("...apply author merges: %s", str(args.apply_author_merges))
    if args.apply_author_renames and not args.confirm:
        logger.info("...apply requested but confirm not set; forcing dry-run")
        dryRun = True

    renameOnly = bool(args.rename_only)
    mergeOnly = bool(args.merge_only)

    planAuthorRenamesFlag = args.plan_author_renames or args.apply_author_renames or args.apply_author_merges
    applyAuthorRenamesFlag = args.apply_author_renames
    applyAuthorMergesFlag = args.apply_author_merges

    # mode overrides
    if renameOnly:
        applyAuthorMergesFlag = False
    if mergeOnly:
        applyAuthorRenamesFlag = False
        # for merges, we still need planning to discover mergeGroups
        planAuthorRenamesFlag = True
    
    report = buildReport(
        root=root,
        dryRun=dryRun,
        logger=logger,
        moveLooseAudiobooks=args.move_loose_audiobooks,
        planAuthorRenamesFlag=planAuthorRenamesFlag,
        applyAuthorRenamesFlag=applyAuthorRenamesFlag,
        applyAuthorMergesFlag=applyAuthorMergesFlag
    )

    logger.info("issues...: %d", report.stats.get("issues", 0))
    logger.info("planned moves...: %d", report.stats.get("plannedMoves", 0))
    logger.info("planned renames...: %d", report.stats.get("plannedRenames", 0))
    logger.info("would merge groups...: %d", report.stats.get("mergeGroups", 0))
    logger.info("non-author folders excluded...: %d", report.stats.get("nonAuthorExcluded", 0))
    logger.info("would move...: %d", report.stats.get("mergeMoves", 0))
    logger.info("would skip...: %d", report.stats.get("mergeSkips", 0))
    logger.info("would fail...: %d", report.stats.get("mergeFails", 0))

    if not dryRun:
        logger.info("moves executed...: %d", report.stats.get("movesExecuted", 0))
        logger.info("moves failed...: %d", report.stats.get("movesFailed", 0))
        logger.info("renames executed...: %d", report.stats.get("renamesExecuted", 0))
        logger.info("renames failed...: %d", report.stats.get("renamesFailed", 0))
        logger.info("author rename collisions...: %d", report.stats.get("authorRenameCollisions", 0))
        logger.info("merge moves...: %d", report.stats.get("mergeMoves", 0))
        logger.info("merge skips...: %d", report.stats.get("mergeSkips", 0))
        logger.info("merge fails...: %d", report.stats.get("mergeFails", 0))

    previewMax = 40
    if report.issues:
        logger.info("...issue preview (up to %d):", previewMax)
        for i, issue in enumerate(report.issues[:previewMax], start=1):
            logger.info("...%02d %s: %s (%s)", i, issue.issueType, issue.path, issue.detail)
        if len(report.issues) > previewMax:
            logger.info("...more issues: %d", len(report.issues) - previewMax)

    if report.mergeGroups:
        logger.info("...merge group preview (up to %d):", previewMax)
        for i, g in enumerate(report.mergeGroups[:previewMax], start=1):
            logger.info("...%02d canonical...: %s", i, g.canonical)
            for s in g.sources[:6]:
                logger.info("......source...: %s", s)
            if len(g.sources) > 6:
                logger.info("......more sources...: %d", len(g.sources) - 6)

    if report.nonAuthorFolders:
        logger.info("...non-author folder preview (up to %d):", previewMax)
        for i, n in enumerate(report.nonAuthorFolders[:previewMax], start=1):
            logger.info("...%02d %s: %s", i, n.path, n.reason)
        if len(report.nonAuthorFolders) > previewMax:
            logger.info("...more non-author folders: %d", len(report.nonAuthorFolders) - previewMax)

    writeReport(report, args.report, logger)
    logger.info("...audit complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())