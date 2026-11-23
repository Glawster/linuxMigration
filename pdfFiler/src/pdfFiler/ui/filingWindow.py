"""FilingWindow: the page on the left, the filled-in filing form on the right.

One window is reused for every PDF in a run. `decide()` shows a form and
returns the user's Decision: File, Skip or Stop (ADR 013).
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

from PySide6.QtCore import QEventLoop, Qt
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from pdfFiler.cabinet import CabinetIndex
from pdfFiler.form import (
    FILE,
    SKIP,
    STOP,
    Decision,
    FormCheck,
    FormState,
    formCheck,
    formFolderSet,
    formTypeSet,
)
from pdfFiler.ui.widgets.pageView import PageView

_STYLES = Path(__file__).resolve().parent / "styles" / "filingWindow.qss"


class FilingWindow(QMainWindow):
    """File, Skip or Stop for each PDF, with every field editable."""

    def __init__(self, index: CabinetIndex, today: dt.date) -> None:
        self.app = QApplication.instance() or QApplication(sys.argv[:1])
        super().__init__()
        self.index = index
        self.today = today
        self._state: FormState | None = None
        self._check: FormCheck | None = None
        self._decision: Decision | None = None
        self._loop: QEventLoop | None = None
        self._createLayout()

    ## public

    def decide(self, state: FormState, position: int, total: int) -> Decision:
        """Show one PDF's form and wait for File, Skip or Stop."""
        self._state = state
        self._decision = None
        self.setWindowTitle(f"pdfFiler - {state.pdf.name} ({position} of {total})")
        self.titleLabel.setText(f"{state.pdf.name}   ({position} of {total})")
        self._fieldsShow()
        self.pageView.load(state.pdf)
        self.show()
        self.raise_()
        self.activateWindow()
        self.folderBox.setFocus()
        self._loop = QEventLoop()
        self._loop.exec()
        self._loop = None
        return self._decision or Decision(STOP)

    def message(self, kind: str, text: str) -> None:
        """Show an info, warning or error message over the window."""
        show = {"error": QMessageBox.critical, "warning": QMessageBox.warning}.get(
            kind, QMessageBox.information
        )
        show(self, "pdfFiler", text)

    ## layout

    def _createLayout(self) -> None:
        self.resize(1500, 950)
        self.setMinimumSize(1100, 700)
        if _STYLES.is_file():
            self.setStyleSheet(_STYLES.read_text(encoding="utf-8"))
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.addLayout(self._createHeader())
        splitter = QSplitter(Qt.Orientation.Horizontal, central)
        self.pageView = PageView(splitter)
        splitter.addWidget(self.pageView)
        splitter.addWidget(self._createContent())
        splitter.setSizes([700, 800])
        layout.addWidget(splitter, 1)
        self.setCentralWidget(central)
        self._createShortcuts()

    def _createHeader(self) -> QHBoxLayout:
        header = QHBoxLayout()
        self.titleLabel = QLabel(objectName="titleLabel")
        header.addWidget(self.titleLabel)
        header.addStretch(1)
        return header

    def _createContent(self) -> QWidget:
        side = QWidget()
        layout = QVBoxLayout(side)
        layout.setContentsMargins(14, 0, 0, 0)
        layout.addLayout(self._createFields())
        layout.addWidget(self._separator())
        layout.addLayout(self._createResult())
        layout.addStretch(1)
        layout.addLayout(self._createFooter())
        return side

    def _createFields(self) -> QFormLayout:
        fields = QFormLayout()
        fields.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.folderBox = QComboBox(editable=True)
        self.folderBox.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._folderBrowse)
        folderRow = QHBoxLayout()
        folderRow.addWidget(self.folderBox, 1)
        folderRow.addWidget(browse)
        fields.addRow("Folder", folderRow)

        self.typeBox = QComboBox(editable=True)
        self.typeBox.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        fields.addRow("Type", self.typeBox)

        self.dateEdit = QLineEdit(placeholderText="YYYY-MM-DD", maxLength=10)
        self.dateEdit.setFixedWidth(130)
        fields.addRow("Date", self.dateEdit)

        self.labelEdit = QLineEdit()
        fields.addRow("Label", self.labelEdit)

        # Only the user's own changes reach these handlers: `activated` and
        # `textEdited` do not fire when the form is filled in by code.
        self.folderBox.activated.connect(lambda _index: self._folderChanged())
        self.folderBox.lineEdit().textEdited.connect(lambda _text: self._folderChanged())
        self.typeBox.activated.connect(lambda _index: self._typeChanged())
        self.typeBox.lineEdit().textEdited.connect(lambda _text: self._typeChanged())
        self.dateEdit.textEdited.connect(lambda _text: self._typed("date", self.dateEdit))
        self.labelEdit.textEdited.connect(lambda _text: self._typed("label", self.labelEdit))
        return fields

    def _createResult(self) -> QVBoxLayout:
        result = QVBoxLayout()
        result.addWidget(QLabel("File as"))
        # One line, the whole path; it scrolls rather than wrapping.
        self.fileAsEdit = QLineEdit(objectName="fileAs", readOnly=True)
        result.addWidget(self.fileAsEdit)
        self.statusLabel = QLabel(objectName="status", wordWrap=True)
        result.addWidget(self.statusLabel)
        result.addSpacing(10)
        result.addWidget(QLabel("Why suggested"))
        self.whyLabel = QLabel(objectName="why", wordWrap=True)
        result.addWidget(self.whyLabel)
        return result

    def _createFooter(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        footer.addWidget(QLabel("Enter = File    Esc = Skip", objectName="keysHint"))
        footer.addStretch(1)
        self.stopButton = QPushButton("Stop")
        self.skipButton = QPushButton("Skip")
        self.fileButton = QPushButton("File", objectName="fileButton")
        self.stopButton.clicked.connect(lambda: self._decide(STOP))
        self.skipButton.clicked.connect(lambda: self._decide(SKIP))
        self.fileButton.clicked.connect(self._fileIfReady)
        for button in (self.stopButton, self.skipButton, self.fileButton):
            button.setAutoDefault(False)
            footer.addWidget(button)
        return footer

    def _createShortcuts(self) -> None:
        for key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            QShortcut(QKeySequence(key), self, activated=self._fileIfReady)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=lambda: self._decide(SKIP))

    ## fields

    def _fieldsShow(self) -> None:
        """Copy the form state into the widgets."""
        state = self._state
        _comboFill(self.folderBox, state.folderChoices, state.folder)
        _comboFill(self.typeBox, state.typeChoices, state.docType)
        self.dateEdit.setText(state.date)
        self.labelEdit.setText(state.label)
        self.whyLabel.setText("; ".join(state.reasons))
        self._refresh()

    def _folderChanged(self) -> None:
        formFolderSet(self._state, self.folderBox.currentText(), self.index, self.today)
        _comboFill(self.typeBox, self._state.typeChoices, self._state.docType)
        self.dateEdit.setText(self._state.date)
        self.labelEdit.setText(self._state.label)
        self._refresh()

    def _typeChanged(self) -> None:
        formTypeSet(self._state, self.typeBox.currentText(), self.today)
        self.dateEdit.setText(self._state.date)
        self._refresh()

    def _typed(self, name: str, edit: QLineEdit) -> None:
        setattr(self._state, name, edit.text())
        self._state.edited.add(name)
        self._refresh()

    def _refresh(self) -> None:
        """Show the one-line destination and anything stopping the file."""
        check = formCheck(self._state, self.today)
        self._check = check
        self.fileAsEdit.setText(check.shown or "—")
        self.fileAsEdit.setCursorPosition(0)
        if check.problem:
            self._statusShow(check.problem, "problem")
            self.fileButton.setText("File")
            self.fileButton.setEnabled(False)
        elif check.outcome == "duplicate":
            self._statusShow(
                f"Already filed as {check.existing.name}: this scan will go to the Trash.",
                "duplicate",
            )
            self.fileButton.setText("Trash duplicate")
            self.fileButton.setEnabled(True)
        else:
            self._statusShow("", "ok")
            self.fileButton.setText("File")
            self.fileButton.setEnabled(True)

    def _statusShow(self, text: str, level: str) -> None:
        self.statusLabel.setText(text)
        self.statusLabel.setProperty("level", level)
        # Re-apply the style so the [level=...] rule takes effect.
        self.statusLabel.style().unpolish(self.statusLabel)
        self.statusLabel.style().polish(self.statusLabel)

    ## actions

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt override)
        """Closing the window stops the run."""
        if self._loop is not None:
            self._decide(STOP)
        event.accept()

    def _decide(self, action: str) -> None:
        self._decision = Decision(action, self._check if action == FILE else None)
        if self._loop is not None:
            self._loop.quit()

    def _fileIfReady(self) -> None:
        if self._check is not None and self._check.problem is None:
            self._decide(FILE)

    def _folderBrowse(self) -> None:
        root = self._state.root
        start = root / self._state.folder if self._state.folder else root
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose filing folder", str(start if start.is_dir() else root)
        )
        if not chosen:
            return
        chosenPath = Path(chosen).resolve()
        if root.resolve() not in chosenPath.parents:
            self.message("error", f"The folder must be inside {root}")
            return
        self.folderBox.setEditText(chosenPath.relative_to(root.resolve()).as_posix())
        self._folderChanged()

    ## utilities

    @staticmethod
    def _separator() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        return line


def _comboFill(box: QComboBox, values: list[str], current: str) -> None:
    """Replace a combo box's items and text without firing user signals."""
    box.clear()
    box.addItems(values)
    box.setEditText(current)
