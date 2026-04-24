"""Left pane: list of segments in the parsed message."""
from __future__ import annotations

from typing import List

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from .hl7_model import ParsedSegment


class SegmentList(QListWidget):
    """Displays segment names (with occurrence indices for repeats) and emits
    segmentSelected(index) when the user selects one."""

    segmentSelected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        font = QFont("Menlo", 11)
        font.setStyleHint(QFont.Monospace)
        self.setFont(font)
        self.setUniformItemSizes(True)
        self.currentRowChanged.connect(self._on_row_changed)

    def load(self, segments: List[ParsedSegment]) -> None:
        self.blockSignals(True)
        self.clear()
        for seg in segments:
            item = QListWidgetItem(seg.display)
            if seg.is_z_segment:
                item.setForeground(QColor("#A02060"))
            self.addItem(item)
        self.blockSignals(False)
        if segments:
            self.setCurrentRow(0)

    def _on_row_changed(self, row: int) -> None:
        if row >= 0:
            self.segmentSelected.emit(row)
