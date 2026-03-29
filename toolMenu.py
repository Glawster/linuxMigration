#!/usr/bin/env python3
"""
toolMenu.py

Qt-based visual launcher and catalogue for all the tools in this repository.

Browse tools organised by category (subfolder), read what each one does,
and launch it — all from a single window.

Usage:
    python3 toolMenu.py
    ./toolMenu.sh

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
    from PyQt6.QtGui import QFont, QColor, QBrush

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
    from PySide6.QtGui import QFont, QColor, QBrush  # type: ignore[no-redef]

    _QT_BACKEND = "PySide6"
    _ItemDataRole = Qt.ItemDataRole
    _Orientation = Qt.Orientation
    _AlignmentFlag = Qt.AlignmentFlag
    _WindowModality = Qt.WindowModality
    _CheckState = Qt.CheckState
    _SizePolicy = QSizePolicy.Policy

# ---------------------------------------------------------------------------
import re
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
    r"(__init__|Config|Utils|Common)\.py$|^toolMenu\.py$", re.IGNORECASE
)

# Shebang / boilerplate lines to strip when extracting Bash descriptions
_BASH_STRIP_PATTERNS = re.compile(
    r"^(#!.*|set\s+-[a-z]+|#\s*-\*-.*-\*-)\s*$", re.IGNORECASE
)


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


def _extractDescription(path: Path) -> str:
    """Extract a human-readable description from a tool file.

    For Python files: first docstring found.
    For Bash files: leading block of # comment lines (ignoring shebang /
    set -euo pipefail lines).
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""

    if path.suffix == ".py":
        # Walk the token stream looking for the first string literal
        import ast

        try:
            tree = ast.parse(text)
        except SyntaxError:
            return _fallbackDocstring(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                val = node.value.value
                if isinstance(val, str) and val.strip():
                    # Split into paragraphs; skip bare-filename paragraphs
                    paragraphs = [p.strip() for p in val.strip().split("\n\n") if p.strip()]
                    for para in paragraphs:
                        firstLine = para.splitlines()[0].strip()
                        # Skip a paragraph whose only content is the filename
                        if re.match(r"^\w[\w.\-]+\.(py|sh)$", firstLine) and len(para.splitlines()) <= 1:
                            continue
                        if firstLine.lower() == path.stem.lower():
                            continue
                        return para
                    return paragraphs[0] if paragraphs else ""
        return _fallbackDocstring(text)

    # Bash: collect leading # lines
    lines = text.splitlines()
    descLines: List[str] = []
    started = False
    for line in lines:
        stripped = line.strip()
        if _BASH_STRIP_PATTERNS.match(stripped):
            continue
        if stripped.startswith("#"):
            comment = stripped.lstrip("#").strip()
            if comment:
                descLines.append(comment)
                started = True
        elif started:
            break  # first non-comment line after we collected some text

    return " ".join(descLines).strip()


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


def discoverTools() -> List[dict]:
    """Scan the repo and return a list of tool metadata dicts."""
    tools: List[dict] = []

    def _scan(directory: Path, maxDepth: int = 1) -> None:
        for entry in sorted(directory.iterdir()):
            if entry.name.startswith(".") or entry.name.startswith("_"):
                continue
            if entry.is_dir() and maxDepth > 0:
                if entry.name in CATEGORY_DIRS or entry.name == directory.name:
                    _scan(entry, maxDepth - 1)
            elif entry.is_file() and _isRunnable(entry):
                tools.append(
                    {
                        "path": entry,
                        "name": entry.name,
                        "type": _toolType(entry),
                        "category": _categoryName(entry),
                        "description": _extractDescription(entry),
                        "usage": "",  # loaded lazily on selection
                    }
                )

    # Root-level files
    for entry in sorted(REPO_ROOT.iterdir()):
        if entry.is_file() and _isRunnable(entry):
            tools.append(
                {
                    "path": entry,
                    "name": entry.name,
                    "type": _toolType(entry),
                    "category": "General",
                    "description": _extractDescription(entry),
                    "usage": "",
                }
            )

    # Subfolders
    for dirName in CATEGORY_DIRS:
        subdir = REPO_ROOT / dirName
        if subdir.is_dir():
            for entry in sorted(subdir.iterdir()):
                if entry.is_file() and _isRunnable(entry):
                    tools.append(
                        {
                            "path": entry,
                            "name": entry.name,
                            "type": _toolType(entry),
                            "category": CATEGORY_DIRS[dirName],
                            "description": _extractDescription(entry),
                            "usage": "",
                        }
                    )

    return tools


# ---------------------------------------------------------------------------
# Run dialog
# ---------------------------------------------------------------------------
class RunDialog(QDialog):
    """Terminal-style dialog that runs a tool via QProcess."""

    def __init__(self, tool: dict, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tool = tool
        self._process: Optional[QProcess] = None
        self._confirmCheck: Optional[QCheckBox] = None
        self._setupUi()
        self.setWindowModality(_WindowModality.WindowModal)
        self.resize(700, 500)

    def _setupUi(self) -> None:
        self.setWindowTitle(f"Run — {self._tool['name']}")
        layout = QVBoxLayout(self)

        # Options row
        optionsRow = QHBoxLayout()
        self._confirmCheck: Optional[QCheckBox] = None
        desc = self._tool.get("description", "")
        usage = self._tool.get("usage", "")
        combined = (desc + " " + usage).lower()
        if "--confirm" in combined:
            self._confirmCheck = QCheckBox("Execute changes (default is dry-run)")
            self._confirmCheck.setChecked(False)
            optionsRow.addWidget(self._confirmCheck)
        optionsRow.addStretch()
        layout.addLayout(optionsRow)

        # Output area
        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)
        self._output.setFont(QFont("Monospace", 10))
        self._output.setStyleSheet(
            "background:#1e1e1e; color:#d4d4d4; border:1px solid #444;"
        )
        layout.addWidget(self._output)

        # Status label
        self._statusLabel = QLabel("Ready.")
        layout.addWidget(self._statusLabel)

        # Buttons
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

    def _buildCommand(self) -> Tuple[str, List[str]]:
        """Return (program, args) for QProcess."""
        path = self._tool["path"]
        extraArgs: List[str] = []
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

    def closeEvent(self, event) -> None:  # type: ignore[override]
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

        # Name label
        self._nameLabel = QLabel()
        nameFont = QFont()
        nameFont.setPointSize(16)
        nameFont.setBold(True)
        self._nameLabel.setFont(nameFont)
        self._nameLabel.setWordWrap(True)
        layout.addWidget(self._nameLabel)

        # Type badge
        self._typeBadge = QLabel()
        self._typeBadge.setFixedHeight(24)
        self._typeBadge.setAlignment(_AlignmentFlag.AlignLeft | _AlignmentFlag.AlignVCenter)
        layout.addWidget(self._typeBadge)

        # Separator
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep1)

        # Description header
        descHeader = QLabel("Description")
        descHeader.setFont(QFont("", -1, QFont.Weight.Bold))
        layout.addWidget(descHeader)

        # Description text
        self._descLabel = QLabel()
        self._descLabel.setWordWrap(True)
        self._descLabel.setAlignment(_AlignmentFlag.AlignTop)
        self._descLabel.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self._descLabel)

        # Usage header
        self._usageHeader = QLabel("Usage / Arguments")
        self._usageHeader.setFont(QFont("", -1, QFont.Weight.Bold))
        layout.addWidget(self._usageHeader)

        # Usage text
        self._usageLabel = QLabel()
        self._usageLabel.setWordWrap(True)
        self._usageLabel.setAlignment(_AlignmentFlag.AlignTop)
        self._usageLabel.setTextFormat(Qt.TextFormat.PlainText)
        self._usageLabel.setFont(QFont("Monospace", 9))
        layout.addWidget(self._usageLabel)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep2)

        # Buttons
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

        layout.addStretch()

        self._showEmpty()

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
        if self._currentTool:
            dlg = RunDialog(self._currentTool, self)
            dlg.exec()

    def _onOpenEditor(self) -> None:
        if not self._currentTool:
            return
        import os
        import shutil

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
        self.setWindowTitle("Linux Migration Tools")
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

        categoryOrder = ["General"] + list(CATEGORY_DIRS.values())
        # Collect any extra categories not in the predefined order
        extraCats = sorted({t["category"] for t in tools} - set(categoryOrder))
        allCategories = categoryOrder + extraCats

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

    def _onTreeSelectionChanged(self, current: QTreeWidgetItem, previous) -> None:
        if current is None:
            return
        tool = current.data(0, _ItemDataRole.UserRole)
        if tool:
            self._detail.showTool(tool)

    def _restoreGeometry(self) -> None:
        settings = QSettings("Glawster", "linuxMigrationTools")
        geometry = settings.value("windowGeometry")
        if geometry:
            self.restoreGeometry(geometry)
        splitterState = settings.value("splitterState")
        if splitterState:
            self._splitter.restoreState(splitterState)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        settings = QSettings("Glawster", "linuxMigrationTools")
        settings.setValue("windowGeometry", self.saveGeometry())
        settings.setValue("splitterState", self._splitter.saveState())
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Linux Migration Tools")
    app.setOrganizationName("Glawster")
    app.setStyle("Fusion")

    window = ToolMenuWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
