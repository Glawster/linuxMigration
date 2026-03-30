#!/usr/bin/env python3
"""
myTools.py

Qt-based visual launcher and catalogue for all the tools in this repository
and related ~/Source projects.

Browse tools organised by category (subfolder or source repo), read what each
one does, and launch it — all from a single window.

Usage:
    python3 myTools.py
    ./myTools.sh

Requires PyQt6 (preferred) or PySide6.
PyQt6 is chosen here because it is the most widely packaged Qt6 binding for
Python on Ubuntu/Debian and matches the PyQt5 → PyQt6 upgrade path already
common in this ecosystem.  If PyQt6 is not installed the code falls back to
PySide6 automatically.
"""

# ---------------------------------------------------------------------------
# Qt import — prefer PyQt6, fall back to PySide6
# ---------------------------------------------------------------------------
try:
    from PyQt6.QtWidgets import (
        QApplication,
        QMainWindow,
        QWidget,
        QSplitter,
        QTreeWidget,
        QTreeWidgetItem,
        QVBoxLayout,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QLineEdit,
        QScrollArea,
        QDialog,
        QPlainTextEdit,
        QCheckBox,
        QSizePolicy,
        QFrame,
    )
    from PyQt6.QtCore import (
        Qt,
        QProcess,
        QSettings,
        QSize,
        QTimer,
    )
    from PyQt6.QtGui import QFont, QColor, QBrush, QCloseEvent

    _QT_BACKEND = "PyQt6"
    _ItemDataRole = Qt.ItemDataRole
    _Orientation = Qt.Orientation
    _AlignmentFlag = Qt.AlignmentFlag
    _WindowModality = Qt.WindowModality
    _CheckState = Qt.CheckState
    _SizePolicy = QSizePolicy.Policy

except ImportError:
    from PySide6.QtWidgets import (  # type: ignore[no-redef]
        QApplication,
        QMainWindow,
        QWidget,
        QSplitter,
        QTreeWidget,
        QTreeWidgetItem,
        QVBoxLayout,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QLineEdit,
        QScrollArea,
        QDialog,
        QPlainTextEdit,
        QCheckBox,
        QSizePolicy,
        QFrame,
    )
    from PySide6.QtCore import (  # type: ignore[no-redef]
        Qt,
        QProcess,
        QSettings,
        QSize,
        QTimer,
    )
    from PySide6.QtGui import QFont, QColor, QBrush, QCloseEvent  # type: ignore[no-redef]

    _QT_BACKEND = "PySide6"
    _ItemDataRole = Qt.ItemDataRole
    _Orientation = Qt.Orientation
    _AlignmentFlag = Qt.AlignmentFlag
    _WindowModality = Qt.WindowModality
    _CheckState = Qt.CheckState
    _SizePolicy = QSizePolicy.Policy

# ---------------------------------------------------------------------------
import ast
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent

# Subfolders that become named categories in the tree
CATEGORY_DIRS = {
    "kohyaTools": "Kohya Tools",
    "recoveryTools": "Recovery Tools",
    "runpodTools": "Runpod Tools",
}

# Python files matching these patterns are library/helper files, not tools
_PY_EXCLUDE_PATTERNS = re.compile(
    r"(__init__|Config|Utils|Common)\.py$|^myTools\.py$", re.IGNORECASE
)

# Shebang / boilerplate lines to strip when extracting Bash descriptions
_BASH_STRIP_PATTERNS = re.compile(
    r"^(#!.*|set\s+-[a-z]+|#\s*-\*-.*-\*-)\s*$", re.IGNORECASE
)

# ---------------------------------------------------------------------------
# ~/Source repo catalogue
# ---------------------------------------------------------------------------
# Each entry declares a repo that may exist under ~/Source.  If the directory
# is absent on the current machine it is silently skipped.
#
# Fields:
#   dir    – directory name under ~/Source
#   label  – category label shown in the tree
#   scan   – list of sub-paths to scan (relative to the repo root).
#            Use ["."] to scan the repo root itself.
#            Each path is scanned one level deep (non-recursive).
SOURCE_BASE = Path.home() / "Source"

SOURCE_REPOS: List[dict] = [
    {
        "dir": "b2-backup-scripts",
        "label": "B2 Backup",
        "scan": ["."],
    },
    {
        "dir": "organiseMyProjects",
        "label": "Organise My Projects",
        "scan": ["."],
    },
    {
        "dir": "organiseMyPhotos",
        "label": "Organise My Photos",
        "scan": ["."],
    },
    {
        "dir": "organiseMyVideo",
        "label": "Organise My Video",
        "scan": ["."],
    },
    {
        "dir": "imageRecognition",
        "label": "Image Recognition",
        "scan": ["."],
    },
    {
        "dir": "sidecarEditor",
        "label": "Sidecar Editor",
        "scan": ["."],
    },
]


# ---------------------------------------------------------------------------
# Tool discovery helpers
# ---------------------------------------------------------------------------
def _isRunnable(path: Path) -> bool:
    """Return True if this file should appear in the catalogue."""
    if path.suffix == ".py":
        return not _PY_EXCLUDE_PATTERNS.search(path.name)
    if path.suffix == ".sh":
        return True
    return False


def _extractPyDescription(text: str, path: Path) -> str:
    """Extract description from a Python source file's first usable docstring."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return _fallbackDocstring(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            val = node.value.value
            if isinstance(val, str) and val.strip():
                paragraphs = [p.strip() for p in val.strip().split("\n\n") if p.strip()]
                for para in paragraphs:
                    firstLine = para.splitlines()[0].strip()
                    if re.match(r"^\w[\w.-]+\.(py|sh)$", firstLine) and len(para.splitlines()) <= 1:
                        continue
                    if firstLine.lower() == path.stem.lower():
                        continue
                    return para
                return paragraphs[0] if paragraphs else ""
    return _fallbackDocstring(text)


def _extractBashDescription(text: str) -> str:
    """Extract description from the leading comment block of a Bash file."""
    descLines: List[str] = []
    started = False
    for line in text.splitlines():
        stripped = line.strip()
        if _BASH_STRIP_PATTERNS.match(stripped):
            continue
        if stripped.startswith("#"):
            comment = stripped.lstrip("#").strip()
            if comment:
                descLines.append(comment)
                started = True
        elif started:
            break
    return " ".join(descLines).strip()


def _extractDescription(path: Path) -> str:
    """Extract a human-readable description from a tool file."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if path.suffix == ".py":
        return _extractPyDescription(text, path)
    return _extractBashDescription(text)


def _fallbackDocstring(text: str) -> str:
    """Simple regex fallback for extracting triple-quoted docstrings."""
    m = re.search(r'"""(.*?)"""', text, re.DOTALL)
    if m:
        return m.group(1).strip().split("\n\n")[0].strip()
    m = re.search(r"'''(.*?)'''", text, re.DOTALL)
    if m:
        return m.group(1).strip().split("\n\n")[0].strip()
    return ""


def _extractUsage(path: Path, timeoutSecs: int = 5) -> str:
    """Run the tool with --help and return its output (stdout+stderr).

    Only attempted for Python files; Bash scripts often have no --help flag.
    Returns empty string on failure or timeout.
    """
    if path.suffix != ".py":
        return ""
    try:
        result = subprocess.run(
            [sys.executable, str(path), "--help"],
            capture_output=True,
            text=True,
            timeout=timeoutSecs,
        )
        output = (result.stdout or "") + (result.stderr or "")
        return output.strip()
    except (subprocess.TimeoutExpired, OSError, subprocess.SubprocessError):
        return ""


def _collectArgKwargs(node: ast.Call) -> dict:
    """Collect keyword arguments from an add_argument() Call into a plain dict."""
    kw: dict = {}
    for kwNode in node.keywords:
        if kwNode.arg is None:
            continue
        if isinstance(kwNode.value, ast.Constant):
            kw[kwNode.arg] = kwNode.value.value
        elif isinstance(kwNode.value, ast.Name):
            kw[kwNode.arg] = kwNode.value.id
    return kw


def _resolveArgDest(flags: List[str], kw: dict, isPositional: bool) -> str:
    """Derive the argparse dest name from flags and keyword args."""
    dest: str = str(kw.get("dest", ""))
    if dest:
        return dest
    if isPositional:
        return flags[0]
    longFlags = [f for f in flags if f.startswith("--")]
    chosen = longFlags[0] if longFlags else flags[0]
    return chosen.lstrip("-").replace("-", "_")


def _parseOneArgDef(node: ast.Call) -> Optional[dict]:
    """Parse a single add_argument() AST Call node into an argument descriptor.

    Returns None if the call cannot be interpreted as a usable argument.
    """
    flags: List[str] = [
        a.value
        for a in node.args
        if isinstance(a, ast.Constant) and isinstance(a.value, str)
    ]
    if not flags:
        return None
    kw = _collectArgKwargs(node)
    action: str = str(kw.get("action", "store"))
    isBoolean = action in ("store_true", "store_false")
    isPositional = not any(f.startswith("-") for f in flags)
    dest = _resolveArgDest(flags, kw, isPositional)
    defaultVal = kw.get("default", None)
    if isBoolean and defaultVal is None:
        defaultVal = action == "store_false"
    return {
        "flags": flags,
        "dest": dest,
        "help": str(kw.get("help", "")),
        "default": defaultVal,
        "action": action,
        "required": bool(kw.get("required", False)),
        "metavar": kw.get("metavar", None),
        "isBoolean": isBoolean,
        "isPositional": isPositional,
    }


def _parseArguments(path: Path) -> List[dict]:
    """Parse add_argument() calls from a Python source file.

    Returns a list of argument descriptor dicts.  Only called lazily when the
    user first presses Run.  Returns an empty list for Bash files or files
    that cannot be parsed.
    """
    if path.suffix != ".py":
        return []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError):
        return []

    argDefs: List[dict] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_argument"
        ):
            argDef = _parseOneArgDef(node)
            if argDef:
                argDefs.append(argDef)
    return argDefs


def _evalPathExpr(node: ast.expr) -> Optional[Path]:
    """Evaluate a simple Path-construction AST expression to a concrete Path.

    Handles Path.home(), Path("str"), and chained / binary operations.
    Returns None for expressions that cannot be statically evaluated.
    """
    if isinstance(node, ast.Call):
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "home"
            and isinstance(func.value, ast.Name)
            and func.value.id == "Path"
        ):
            return Path.home()
        if (
            isinstance(func, ast.Name)
            and func.id == "Path"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            return Path(str(node.args[0].value))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = _evalPathExpr(node.left)
        if left is not None and isinstance(node.right, ast.Constant):
            return left / str(node.right.value)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return Path(node.value)
    return None


def _extractConfigPathFromModule(modulePath: Path) -> Optional[Path]:
    """Find and evaluate the DEFAULT_CONFIG_PATH assignment in a module."""
    try:
        tree = ast.parse(modulePath.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError):
        return None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "DEFAULT_CONFIG_PATH":
                return _evalPathExpr(node.value)
    return None


def _findConfigPathByDocstring(text: str) -> Optional[Path]:
    """Strategy 1: scan source text for a ~/... config path literal."""
    for m in re.finditer(r"~[/\\][\w/\\.-]+\.(?:json|cfg|ini|toml|yaml|yml)", text):
        candidate = Path(m.group(0)).expanduser()
        if candidate.exists():
            return candidate
    return None


def _findConfigPathByImport(tree: ast.AST, toolDir: Path) -> Optional[Path]:
    """Strategy 2: DEFAULT_CONFIG_PATH imported from a local sibling module."""
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ImportFrom) and node.module):
            continue
        if "DEFAULT_CONFIG_PATH" not in [a.name for a in node.names]:
            continue
        candidate = toolDir / f"{node.module.split('.')[-1]}.py"
        if candidate.exists():
            cfgPath = _extractConfigPathFromModule(candidate)
            if cfgPath and cfgPath.exists():
                return cfgPath
    return None


def _findConfigPathByArgparse(tree: ast.AST, toolDir: Path) -> Optional[Path]:
    """Strategy 3: add_argument("--config*", default="<path>") with a file default."""
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_argument"
        ):
            continue
        flags = [
            a.value
            for a in node.args
            if isinstance(a, ast.Constant) and isinstance(a.value, str)
        ]
        if not any("config" in f.lower() for f in flags):
            continue
        for kw in node.keywords:
            if kw.arg == "default" and isinstance(kw.value, ast.Constant):
                val = kw.value.value
                if isinstance(val, str) and val:
                    candidate = Path(val).expanduser()
                    if not candidate.is_absolute():
                        candidate = toolDir / candidate
                    if candidate.exists():
                        return candidate
    return None


def _findConfigPath(toolPath: Path) -> Optional[Path]:
    """Detect the config file path used by a Python tool.

    Tries three strategies in order: docstring path literal,
    DEFAULT_CONFIG_PATH import, and add_argument --config* default.
    """
    if toolPath.suffix != ".py":
        return None
    try:
        text = toolPath.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(text)
    except (OSError, SyntaxError):
        return None
    return (
        _findConfigPathByDocstring(text)
        or _findConfigPathByImport(tree, toolPath.parent)
        or _findConfigPathByArgparse(tree, toolPath.parent)
    )


def _toolType(path: Path) -> str:
    """Return a display label for the file type."""
    return {"py": "Python", "sh": "Bash"}.get(path.suffix.lstrip("."), "Script")


def _categoryName(path: Path) -> str:
    """Return the category label for a tool path."""
    rel = path.relative_to(REPO_ROOT)
    parts = rel.parts
    if len(parts) > 1:
        return CATEGORY_DIRS.get(parts[0], parts[0].capitalize())
    return "General"


def _scanDir(directory: Path, label: str, tools: List[dict]) -> None:
    """Append all runnable tools found directly inside directory to tools."""
    if not directory.is_dir():
        return
    for entry in sorted(directory.iterdir()):
        if entry.is_file() and _isRunnable(entry):
            tools.append(
                {
                    "path": entry,
                    "name": entry.name,
                    "type": _toolType(entry),
                    "category": label,
                    "description": _extractDescription(entry),
                    "usage": "",
                }
            )


def discoverTools() -> List[dict]:
    """Scan the repo and ~/Source repos; return a list of tool metadata dicts."""
    tools: List[dict] = []
    _scanDir(REPO_ROOT, "General", tools)
    for dirName, label in CATEGORY_DIRS.items():
        _scanDir(REPO_ROOT / dirName, label, tools)
    for repo in SOURCE_REPOS:
        repoRoot = SOURCE_BASE / repo["dir"]
        if not repoRoot.is_dir():
            continue
        for scanPath in repo["scan"]:
            scanDir = repoRoot if scanPath == "." else repoRoot / scanPath
            _scanDir(scanDir, repo["label"], tools)
    return tools


# ---------------------------------------------------------------------------
# Config editor dialog
# ---------------------------------------------------------------------------
class ConfigEditorDialog(QDialog):
    """Editable view of a tool's JSON (or other plain-text) config file."""

    def __init__(self, configPath: Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._configPath = configPath
        self._setupUi()
        self.setWindowModality(_WindowModality.WindowModal)
        self.resize(640, 500)

    def _setupUi(self) -> None:
        self.setWindowTitle(f"Config — {self._configPath.name}")
        layout = QVBoxLayout(self)

        pathLabel = QLabel(str(self._configPath))
        pathLabel.setStyleSheet("color:#666; font-size:9pt;")
        pathLabel.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(pathLabel)

        self._editor = QPlainTextEdit()
        self._editor.setFont(QFont("Monospace", 10))
        layout.addWidget(self._editor)

        self._statusLabel = QLabel("")
        layout.addWidget(self._statusLabel)

        self._addButtons(layout)
        self._loadContent()

    def _addButtons(self, layout: QVBoxLayout) -> None:
        """Add Save / Reload / Close buttons."""
        btnRow = QHBoxLayout()
        saveBtn = QPushButton("💾  Save")
        saveBtn.setDefault(True)
        saveBtn.clicked.connect(self._onSave)
        reloadBtn = QPushButton("↺  Reload")
        reloadBtn.clicked.connect(self._loadContent)
        closeBtn = QPushButton("Close")
        closeBtn.clicked.connect(self.close)
        btnRow.addWidget(saveBtn)
        btnRow.addWidget(reloadBtn)
        btnRow.addStretch()
        btnRow.addWidget(closeBtn)
        layout.addLayout(btnRow)

    def _loadContent(self) -> None:
        """Read the config file and populate the editor."""
        try:
            rawText = self._configPath.read_text(encoding="utf-8", errors="replace")
            if self._configPath.suffix == ".json":
                try:
                    rawText = json.dumps(json.loads(rawText), indent=2)
                except json.JSONDecodeError:
                    pass
            self._editor.setPlainText(rawText)
            self._statusLabel.setText("")
        except OSError as exc:
            self._editor.setPlainText("")
            self._statusLabel.setText(f"Could not read: {exc}")

    def _onSave(self) -> None:
        """Validate (if JSON) and write the editor content back to disk."""
        text = self._editor.toPlainText()
        if self._configPath.suffix == ".json":
            try:
                json.loads(text)
            except json.JSONDecodeError as exc:
                self._statusLabel.setText(f"Invalid JSON — not saved: {exc}")
                return
        try:
            self._configPath.write_text(text, encoding="utf-8")
            self._statusLabel.setText("Saved ✓")
        except OSError as exc:
            self._statusLabel.setText(f"Save failed: {exc}")


# ---------------------------------------------------------------------------
# Arguments form dialog
# ---------------------------------------------------------------------------
class ArgsDialog(QDialog):
    """Pre-run form for configuring arguments and reviewing the config file."""

    def __init__(
        self,
        tool: dict,
        argDefs: List[dict],
        configPath: Optional[Path] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._tool = tool
        self._argDefs = argDefs
        self._configPath = configPath
        self._widgets: List[Tuple[dict, QWidget]] = []
        self._skipped = False
        self._setupUi()
        self.setWindowModality(_WindowModality.WindowModal)
        self.resize(520, min(140 + len(argDefs) * 52, 600))

    def _setupUi(self) -> None:
        self.setWindowTitle(f"Arguments — {self._tool['name']}")
        layout = QVBoxLayout(self)
        self._addConfigRow(layout)
        if self._argDefs:
            self._addArgForm(layout)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep)
        self._addButtonRow(layout)

    def _addConfigRow(self, layout: QVBoxLayout) -> None:
        """Add the config file label + Show Config button (when a config is detected)."""
        if not self._configPath:
            return
        cfgRow = QHBoxLayout()
        cfgLabel = QLabel(f"Config: {self._configPath.name}")
        cfgLabel.setStyleSheet("color:#666; font-size:9pt;")
        cfgBtn = QPushButton("⚙  Show Config")
        cfgBtn.setFlat(True)
        cfgBtn.clicked.connect(self._onShowConfig)
        cfgRow.addWidget(cfgLabel)
        cfgRow.addStretch()
        cfgRow.addWidget(cfgBtn)
        layout.addLayout(cfgRow)
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(divider)

    def _addArgForm(self, layout: QVBoxLayout) -> None:
        """Add the scrollable form with one row per argument."""
        infoLabel = QLabel("Configure arguments, then click <b>Run</b>:")
        infoLabel.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(infoLabel)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        formWidget = QWidget()
        formLayout = QVBoxLayout(formWidget)
        formLayout.setSpacing(6)
        formLayout.setContentsMargins(4, 4, 4, 4)
        for argDef in self._argDefs:
            self._addArgRow(formLayout, argDef)
        formLayout.addStretch()
        scroll.setWidget(formWidget)
        layout.addWidget(scroll)

    def _addArgRow(self, formLayout: QVBoxLayout, argDef: dict) -> None:
        """Add a label + input widget row for one argument definition."""
        row = QHBoxLayout()
        row.setSpacing(8)
        flagStr = ", ".join(argDef["flags"])
        helpText = argDef["help"] or flagStr
        lbl = QLabel(flagStr)
        lbl.setFixedWidth(180)
        lbl.setToolTip(helpText)
        if argDef["required"]:
            font = lbl.font()
            font.setBold(True)
            lbl.setFont(font)
        row.addWidget(lbl)
        if argDef["isBoolean"]:
            widget: QWidget = QCheckBox()
            widget.setChecked(bool(argDef["default"]))
            widget.setToolTip(helpText)
            row.addWidget(widget)
            row.addStretch()
        else:
            widget = QLineEdit()
            if argDef["default"] is not None:
                widget.setText(str(argDef["default"]))
            widget.setPlaceholderText(
                str(argDef["metavar"]) if argDef["metavar"] else argDef["dest"]
            )
            widget.setToolTip(helpText)
            row.addWidget(widget)
        formLayout.addLayout(row)
        self._widgets.append((argDef, widget))

    def _addButtonRow(self, layout: QVBoxLayout) -> None:
        """Add Run / Cancel / Run-without-arguments buttons."""
        btnRow = QHBoxLayout()
        runBtn = QPushButton("▶  Run")
        runBtn.setDefault(True)
        runBtn.clicked.connect(self.accept)
        cancelBtn = QPushButton("Cancel")
        cancelBtn.clicked.connect(self.reject)
        btnRow.addWidget(runBtn)
        btnRow.addWidget(cancelBtn)
        if self._argDefs:
            skipBtn = QPushButton("Run without arguments")
            skipBtn.setFlat(True)
            skipBtn.setStyleSheet("color:#888;")
            skipBtn.clicked.connect(self._onSkip)
            btnRow.addStretch()
            btnRow.addWidget(skipBtn)
        layout.addLayout(btnRow)

    def _onShowConfig(self) -> None:
        if self._configPath:
            ConfigEditorDialog(self._configPath, self).exec()

    def _onSkip(self) -> None:
        self._skipped = True
        self.accept()

    def buildArgs(self) -> List[str]:
        """Convert form widget values to a CLI argument list."""
        if self._skipped:
            return []
        result: List[str] = []
        for argDef, widget in self._widgets:
            if argDef["isBoolean"]:
                checked = isinstance(widget, QCheckBox) and widget.isChecked()
                if argDef["action"] == "store_true" and checked:
                    result.append(argDef["flags"][0])
                elif argDef["action"] == "store_false" and not checked:
                    result.append(argDef["flags"][0])
            elif argDef["isPositional"]:
                val = widget.text().strip() if isinstance(widget, QLineEdit) else ""
                if val:
                    result.append(val)
            else:
                val = widget.text().strip() if isinstance(widget, QLineEdit) else ""
                if val:
                    longFlags = [f for f in argDef["flags"] if f.startswith("--")]
                    flag = longFlags[0] if longFlags else argDef["flags"][0]
                    result.extend([flag, val])
        return result


# ---------------------------------------------------------------------------
# Run dialog
# ---------------------------------------------------------------------------
class RunDialog(QDialog):
    """Terminal-style dialog that runs a tool via QProcess."""

    def __init__(
        self,
        tool: dict,
        extraArgs: Optional[List[str]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._tool = tool
        self._extraArgs = extraArgs  # None → manual mode; list → auto-start mode
        self._process: Optional[QProcess] = None
        self._confirmCheck: Optional[QCheckBox] = None
        self._setupUi()
        self.setWindowModality(_WindowModality.WindowModal)
        self.resize(700, 500)
        if self._extraArgs is not None:
            QTimer.singleShot(0, self._runTool)

    def _setupOptionsRow(self, layout: QVBoxLayout) -> None:
        """Add either an args-preview label or the --confirm checkbox."""
        if self._extraArgs is not None:
            if self._extraArgs:
                previewLabel = QLabel("Args: " + " ".join(self._extraArgs))
                previewLabel.setStyleSheet("color:#666; font-size:9pt;")
                previewLabel.setTextFormat(Qt.TextFormat.PlainText)
                layout.addWidget(previewLabel)
        else:
            optionsRow = QHBoxLayout()
            desc = self._tool.get("description", "")
            usage = self._tool.get("usage", "")
            if "--confirm" in (desc + " " + usage).lower():
                self._confirmCheck = QCheckBox("Execute changes (default is dry-run)")
                self._confirmCheck.setChecked(False)
                optionsRow.addWidget(self._confirmCheck)
            optionsRow.addStretch()
            layout.addLayout(optionsRow)

    def _setupOutputArea(self, layout: QVBoxLayout) -> None:
        """Add the monospace output text area."""
        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)
        self._output.setFont(QFont("Monospace", 10))
        self._output.setStyleSheet(
            "background:#1e1e1e; color:#d4d4d4; border:1px solid #444;"
        )
        layout.addWidget(self._output)

    def _setupButtons(self, layout: QVBoxLayout) -> None:
        """Add Run / Stop / Close buttons."""
        self._statusLabel = QLabel("Ready.")
        layout.addWidget(self._statusLabel)
        btnRow = QHBoxLayout()
        self._runBtn = QPushButton("▶  Run")
        self._runBtn.setDefault(True)
        self._runBtn.clicked.connect(self._runTool)
        self._stopBtn = QPushButton("■  Stop")
        self._stopBtn.setEnabled(False)
        self._stopBtn.clicked.connect(self._stopTool)
        closeBtn = QPushButton("Close")
        closeBtn.clicked.connect(self.close)
        btnRow.addWidget(self._runBtn)
        btnRow.addWidget(self._stopBtn)
        btnRow.addStretch()
        btnRow.addWidget(closeBtn)
        layout.addLayout(btnRow)

    def _setupUi(self) -> None:
        self.setWindowTitle(f"Run — {self._tool['name']}")
        layout = QVBoxLayout(self)
        self._setupOptionsRow(layout)
        self._setupOutputArea(layout)
        self._setupButtons(layout)

    def _buildCommand(self) -> Tuple[str, List[str]]:
        """Return (program, args) for QProcess."""
        path = self._tool["path"]
        if self._extraArgs is not None:
            extraArgs = list(self._extraArgs)
        else:
            extraArgs = []
            if self._confirmCheck and self._confirmCheck.isChecked():
                extraArgs.append("--confirm")
        if path.suffix == ".py":
            return sys.executable, [str(path)] + extraArgs
        return "bash", [str(path)] + extraArgs

    def _runTool(self) -> None:
        self._output.clear()
        self._statusLabel.setText("Running…")
        self._runBtn.setEnabled(False)
        self._stopBtn.setEnabled(True)

        program, args = self._buildCommand()
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._process.readyRead.connect(self._onReadyRead)
        self._process.finished.connect(self._onFinished)
        self._process.start(program, args)

    def _onReadyRead(self) -> None:
        if self._process:
            data = bytes(self._process.readAll()).decode("utf-8", errors="replace")
            self._output.moveCursor(self._output.textCursor().MoveOperation.End)
            self._output.insertPlainText(data)
            self._output.moveCursor(self._output.textCursor().MoveOperation.End)

    def _onFinished(self, exitCode: int, exitStatus: QProcess.ExitStatus) -> None:
        self._runBtn.setEnabled(True)
        self._stopBtn.setEnabled(False)
        statusText = (
            f"Finished — exit code {exitCode}"
            if exitStatus == QProcess.ExitStatus.NormalExit
            else "Crashed or terminated."
        )
        self._statusLabel.setText(statusText)
        self._process = None

    def _stopTool(self) -> None:
        if self._process:
            self._process.terminate()
            QTimer.singleShot(2000, self._forceKill)

    def _forceKill(self) -> None:
        if self._process and self._process.state() != QProcess.ProcessState.NotRunning:
            self._process.kill()

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        self._stopTool()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# Detail pane
# ---------------------------------------------------------------------------
class DetailPane(QScrollArea):
    """Right-hand panel showing tool metadata and action buttons."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._currentTool: Optional[dict] = None
        self.setWidgetResizable(True)
        self._container = QWidget()
        self.setWidget(self._container)
        layout = QVBoxLayout(self._container)
        layout.setAlignment(_AlignmentFlag.AlignTop)
        layout.setSpacing(8)
        self._setupNameSection(layout)
        self._setupDescriptionSection(layout)
        self._setupButtonRow(layout)
        layout.addStretch()
        self._showEmpty()

    def _setupNameSection(self, layout: QVBoxLayout) -> None:
        """Add name label, type badge, and horizontal separator."""
        self._nameLabel = QLabel()
        nameFont = QFont()
        nameFont.setPointSize(16)
        nameFont.setBold(True)
        self._nameLabel.setFont(nameFont)
        self._nameLabel.setWordWrap(True)
        layout.addWidget(self._nameLabel)

        self._typeBadge = QLabel()
        self._typeBadge.setFixedHeight(24)
        self._typeBadge.setAlignment(_AlignmentFlag.AlignLeft | _AlignmentFlag.AlignVCenter)
        layout.addWidget(self._typeBadge)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep)

    def _setupDescriptionSection(self, layout: QVBoxLayout) -> None:
        """Add description label, usage label, and horizontal separator."""
        descHeader = QLabel("Description")
        descHeader.setFont(QFont("", -1, QFont.Weight.Bold))
        layout.addWidget(descHeader)

        self._descLabel = QLabel()
        self._descLabel.setWordWrap(True)
        self._descLabel.setAlignment(_AlignmentFlag.AlignTop)
        self._descLabel.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self._descLabel)

        self._usageHeader = QLabel("Usage / Arguments")
        self._usageHeader.setFont(QFont("", -1, QFont.Weight.Bold))
        layout.addWidget(self._usageHeader)

        self._usageLabel = QLabel()
        self._usageLabel.setWordWrap(True)
        self._usageLabel.setAlignment(_AlignmentFlag.AlignTop)
        self._usageLabel.setTextFormat(Qt.TextFormat.PlainText)
        self._usageLabel.setFont(QFont("Monospace", 9))
        layout.addWidget(self._usageLabel)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep)

    def _setupButtonRow(self, layout: QVBoxLayout) -> None:
        """Add Run and Open-in-Editor buttons."""
        btnRow = QHBoxLayout()
        self._runBtn = QPushButton("▶  Run")
        self._runBtn.setEnabled(False)
        self._runBtn.clicked.connect(self._onRun)
        self._openBtn = QPushButton("✎  Open in Editor")
        self._openBtn.setEnabled(False)
        self._openBtn.clicked.connect(self._onOpenEditor)
        btnRow.addWidget(self._runBtn)
        btnRow.addWidget(self._openBtn)
        btnRow.addStretch()
        layout.addLayout(btnRow)

    def _showEmpty(self) -> None:
        self._nameLabel.setText("Select a tool")
        self._typeBadge.setText("")
        self._descLabel.setText("Choose a tool from the list on the left.")
        self._usageHeader.setVisible(False)
        self._usageLabel.setVisible(False)
        self._runBtn.setEnabled(False)
        self._openBtn.setEnabled(False)

    def showTool(self, tool: dict) -> None:
        self._currentTool = tool
        self._nameLabel.setText(tool["name"])

        # Type badge with colour
        toolType = tool["type"]
        colours = {"Python": "#3572A5", "Bash": "#89e051", "Shell": "#89e051"}
        colour = colours.get(toolType, "#888888")
        self._typeBadge.setText(f"  {toolType}  ")
        self._typeBadge.setStyleSheet(
            f"background:{colour}; color:white; border-radius:4px; padding:2px 6px;"
        )

        self._descLabel.setText(tool["description"] or "(no description available)")

        # Load usage lazily
        if not tool["usage"] and tool["type"] == "Python":
            tool["usage"] = _extractUsage(tool["path"])

        usage = tool.get("usage", "")
        if usage:
            self._usageHeader.setVisible(True)
            self._usageLabel.setVisible(True)
            self._usageLabel.setText(usage)
        else:
            self._usageHeader.setVisible(False)
            self._usageLabel.setVisible(False)

        self._runBtn.setEnabled(True)
        self._openBtn.setEnabled(True)

    def _onRun(self) -> None:
        if not self._currentTool:
            return
        tool = self._currentTool
        if "args" not in tool:
            tool["args"] = _parseArguments(tool["path"])
            tool["configPath"] = _findConfigPath(tool["path"])
        argDefs: List[dict] = tool["args"]
        configPath: Optional[Path] = tool.get("configPath")
        if argDefs or configPath:
            dlg = ArgsDialog(tool, argDefs, configPath=configPath, parent=self)
            if not dlg.exec():
                return
            extraArgs = dlg.buildArgs()
            RunDialog(tool, extraArgs=extraArgs, parent=self).exec()
        else:
            RunDialog(tool, parent=self).exec()

    def _onOpenEditor(self) -> None:
        if not self._currentTool:
            return
        filePath = str(self._currentTool["path"])
        editor = os.environ.get("EDITOR", "")
        if editor and shutil.which(editor):
            QProcess.startDetached(editor, [filePath])
        else:
            QProcess.startDetached("xdg-open", [filePath])


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
class ToolMenuWindow(QMainWindow):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("My Tools")
        self.setMinimumSize(QSize(900, 600))

        self._tools: List[dict] = []
        self._categoryItems: dict = {}  # category name → QTreeWidgetItem

        self._setupUi()
        self._loadTools()
        self._restoreGeometry()

    def _setupUi(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        mainLayout = QVBoxLayout(central)
        mainLayout.setContentsMargins(6, 6, 6, 6)
        mainLayout.setSpacing(4)

        # Search bar
        searchRow = QHBoxLayout()
        searchLabel = QLabel("🔍")
        self._searchEdit = QLineEdit()
        self._searchEdit.setPlaceholderText("Filter tools…")
        self._searchEdit.textChanged.connect(self._onSearchChanged)
        searchRow.addWidget(searchLabel)
        searchRow.addWidget(self._searchEdit)
        mainLayout.addLayout(searchRow)

        # Splitter: tree | detail
        self._splitter = QSplitter(_Orientation.Horizontal)

        # Left — tree
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setColumnCount(1)
        self._tree.setMinimumWidth(200)
        self._tree.currentItemChanged.connect(self._onTreeSelectionChanged)
        self._splitter.addWidget(self._tree)

        # Right — detail pane
        self._detail = DetailPane()
        self._splitter.addWidget(self._detail)

        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 3)
        self._splitter.setSizes([250, 650])

        mainLayout.addWidget(self._splitter)

        # Status bar
        self.statusBar().showMessage(f"Qt backend: {_QT_BACKEND}")

    def _loadTools(self) -> None:
        self._tools = discoverTools()
        self._rebuildTree(self._tools)

    def _rebuildTree(self, tools: List[dict]) -> None:
        self._tree.clear()
        self._categoryItems = {}

        # Local repo categories come first in a fixed order, then Source repos
        # in declaration order, then anything else alphabetically.
        localOrder = ["General"] + list(CATEGORY_DIRS.values())
        sourceOrder = [r["label"] for r in SOURCE_REPOS]
        knownOrder = localOrder + sourceOrder
        extraCats = sorted({t["category"] for t in tools} - set(knownOrder))
        allCategories = knownOrder + extraCats

        for category in allCategories:
            catTools = [t for t in tools if t["category"] == category]
            if not catTools:
                continue

            catItem = QTreeWidgetItem(self._tree, [category])
            catFont = QFont()
            catFont.setBold(True)
            catItem.setFont(0, catFont)
            # Make category headers non-selectable
            catItem.setFlags(
                catItem.flags()
                & ~Qt.ItemFlag.ItemIsSelectable
                & ~Qt.ItemFlag.ItemIsUserCheckable
            )
            self._categoryItems[category] = catItem

            for tool in catTools:
                toolItem = QTreeWidgetItem(catItem, [tool["name"]])
                toolItem.setData(0, _ItemDataRole.UserRole, tool)

            catItem.setExpanded(True)

        self._tree.resizeColumnToContents(0)

    def _onSearchChanged(self, text: str) -> None:
        query = text.strip().lower()
        if not query:
            self._rebuildTree(self._tools)
            return

        filtered = [
            t
            for t in self._tools
            if query in t["name"].lower()
            or query in t["description"].lower()
            or query in t["category"].lower()
        ]
        self._rebuildTree(filtered)

    def _onTreeSelectionChanged(self, current: QTreeWidgetItem, previous: Optional[QTreeWidgetItem]) -> None:
        if current is None:
            return
        tool = current.data(0, _ItemDataRole.UserRole)
        if tool:
            self._detail.showTool(tool)

    def _restoreGeometry(self) -> None:
        settings = QSettings("Glawster", "myTools")
        geometry = settings.value("windowGeometry")
        if geometry:
            self.restoreGeometry(geometry)
        splitterState = settings.value("splitterState")
        if splitterState:
            self._splitter.restoreState(splitterState)

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        settings = QSettings("Glawster", "myTools")
        settings.setValue("windowGeometry", self.saveGeometry())
        settings.setValue("splitterState", self._splitter.saveState())
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("My Tools")
    app.setOrganizationName("Glawster")
    app.setStyle("Fusion")

    window = ToolMenuWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
