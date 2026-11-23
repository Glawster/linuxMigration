"""PageView: one page of a PDF at a time, with paging and fit/width zoom.

Qt's own PDF renderer (QtPdf) draws the page; no image files are made.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class PageView(QWidget):
    """A PDF page viewer with ◀ ▶ paging and a Fit page / Fit width toggle."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.document = QPdfDocument(self)
        self._createLayout()

    ## public

    def load(self, pdf: Path) -> bool:
        """Show page 1 of a PDF fitted to the view; False if it cannot be read."""
        self.document.close()
        loaded = self.document.load(str(pdf)) == QPdfDocument.Error.None_
        self.view.setZoomMode(QPdfView.ZoomMode.FitInView)
        self._pageGo(0)
        self.pageLabel.setText(
            f"Page 1 of {self.document.pageCount()}" if loaded else "Page could not be shown"
        )
        return loaded

    def pageCurrent(self) -> int:
        """The page shown, counting from 0."""
        return self.view.pageNavigator().currentPage()

    ## layout

    def _createLayout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._createToolbar())
        self.view = QPdfView(self)
        self.view.setObjectName("pageView")
        self.view.setDocument(self.document)
        self.view.setPageMode(QPdfView.PageMode.SinglePage)
        self.view.setZoomMode(QPdfView.ZoomMode.FitInView)
        layout.addWidget(self.view, 1)

    def _createToolbar(self) -> QHBoxLayout:
        toolbar = QHBoxLayout()
        self.previousButton = QPushButton("◀")
        self.nextButton = QPushButton("▶")
        self.pageLabel = QLabel("Page 1 of 1")
        self.zoomButton = QPushButton("Fit width")
        for button in (self.previousButton, self.nextButton):
            button.setFixedWidth(40)
        self.previousButton.clicked.connect(lambda: self._pageMove(-1))
        self.nextButton.clicked.connect(lambda: self._pageMove(1))
        self.zoomButton.clicked.connect(self._zoomToggle)
        toolbar.addWidget(self.previousButton)
        toolbar.addWidget(self.pageLabel)
        toolbar.addWidget(self.nextButton)
        toolbar.addStretch(1)
        toolbar.addWidget(self.zoomButton)
        return toolbar

    ## actions

    def _pageGo(self, page: int) -> None:
        if self.document.pageCount():
            self.view.pageNavigator().jump(page, QPointF(), self.view.zoomFactor())
            self.pageLabel.setText(f"Page {page + 1} of {self.document.pageCount()}")

    def _pageMove(self, step: int) -> None:
        page = min(max(self.pageCurrent() + step, 0), max(self.document.pageCount() - 1, 0))
        if page != self.pageCurrent():
            self._pageGo(page)

    def _zoomToggle(self) -> None:
        fitPage = self.view.zoomMode() == QPdfView.ZoomMode.FitInView
        self.view.setZoomMode(
            QPdfView.ZoomMode.FitToWidth if fitPage else QPdfView.ZoomMode.FitInView
        )
        self.zoomButton.setText("Fit page" if fitPage else "Fit width")
