"""Top pane: read-only ER7 viewer with delimiter-aware syntax highlighting
and segment-line selection."""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import QPlainTextEdit


class _ER7Highlighter(QSyntaxHighlighter):
    """Colors segment names and delimiters. Colors chosen to work in both
    light and dark Aqua themes."""

    def __init__(self, document, encoding_chars):
        super().__init__(document)
        self.enc = encoding_chars

        self.fmt_segment = QTextCharFormat()
        self.fmt_segment.setForeground(QColor("#0A58CA"))
        self.fmt_segment.setFontWeight(QFont.Bold)

        self.fmt_field = QTextCharFormat()
        self.fmt_field.setForeground(QColor("#888888"))

        self.fmt_component = QTextCharFormat()
        self.fmt_component.setForeground(QColor("#C77700"))

        self.fmt_repetition = QTextCharFormat()
        self.fmt_repetition.setForeground(QColor("#007A3D"))

        self.fmt_subcomp = QTextCharFormat()
        self.fmt_subcomp.setForeground(QColor("#A02060"))

    def update_encoding(self, encoding_chars):
        self.enc = encoding_chars
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:  # noqa: N802 — Qt naming
        if len(text) >= 3 and text[:3].isalpha():
            self.setFormat(0, 3, self.fmt_segment)

        for i, ch in enumerate(text):
            if ch == self.enc.field_sep:
                self.setFormat(i, 1, self.fmt_field)
            elif ch == self.enc.component_sep:
                self.setFormat(i, 1, self.fmt_component)
            elif ch == self.enc.repetition_sep:
                self.setFormat(i, 1, self.fmt_repetition)
            elif ch == self.enc.subcomponent_sep:
                self.setFormat(i, 1, self.fmt_subcomp)


class RawEditor(QPlainTextEdit):
    """Read-only raw message view. Emits segmentClicked(line_index) when the
    user clicks on a segment line."""

    segmentClicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        font = QFont("Menlo", 11)
        font.setStyleHint(QFont.Monospace)
        self.setFont(font)
        self._highlighter: Optional[_ER7Highlighter] = None

    def set_message(self, raw: str, encoding_chars) -> None:
        """Load raw ER7 into the viewer, applying syntax highlighting."""
        # Display with LF so Qt renders one line per segment.
        display = raw.replace("\r\n", "\n").replace("\r", "\n")
        self.setPlainText(display)
        if self._highlighter is None:
            self._highlighter = _ER7Highlighter(self.document(), encoding_chars)
        else:
            self._highlighter.update_encoding(encoding_chars)

    def highlight_segment(self, line_index: int) -> None:
        """Move the cursor to the start of the given segment line and select
        the entire line."""
        block = self.document().findBlockByNumber(line_index)
        if not block.isValid():
            return
        cursor = QTextCursor(block)
        cursor.select(QTextCursor.LineUnderCursor)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        super().mouseReleaseEvent(event)
        if event.button() == Qt.LeftButton:
            cursor = self.textCursor()
            self.segmentClicked.emit(cursor.blockNumber())
