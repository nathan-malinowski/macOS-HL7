"""Main window: three-pane viewer. Top = raw ER7, left = segment list,
right = field / component / repetition / sub-component tables."""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .field_tables import (
    ComponentTable,
    FieldTable,
    RepetitionTable,
    SubcomponentTable,
)
from .hl7_model import ParsedMessage, parse
from .raw_editor import RawEditor
from .segment_list import SegmentList


APP_TITLE = "macOS-HL7"
SUPPORTED_EXT = (".hl7", ".hl7v2", ".er7", ".txt")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1280, 820)
        self.setAcceptDrops(True)

        self._parsed: Optional[ParsedMessage] = None

        self._build_widgets()
        self._build_actions()
        self._build_menubar()
        self._build_toolbar()
        self._build_statusbar()
        self._wire_signals()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build_widgets(self) -> None:
        self.raw_editor = RawEditor(self)
        self.segment_list = SegmentList(self)
        self.field_table = FieldTable(self)
        self.repetition_table = RepetitionTable(self)
        self.component_table = ComponentTable(self)
        self.subcomp_table = SubcomponentTable(self)

        left_pane = QSplitter(Qt.Vertical)
        left_pane.addWidget(self.field_table)
        left_pane.addWidget(self.repetition_table)
        left_pane.setSizes([450, 200])

        right_pane = QSplitter(Qt.Vertical)
        right_pane.addWidget(self.component_table)
        right_pane.addWidget(self.subcomp_table)
        right_pane.setSizes([450, 200])

        bottom_split = QSplitter(Qt.Horizontal)
        bottom_split.addWidget(self.segment_list)
        bottom_split.addWidget(left_pane)
        bottom_split.addWidget(right_pane)
        bottom_split.setSizes([160, 540, 540])

        main_split = QSplitter(Qt.Vertical)
        main_split.addWidget(self.raw_editor)
        main_split.addWidget(bottom_split)
        main_split.setSizes([260, 560])

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(main_split)
        self.setCentralWidget(container)

    def _build_actions(self) -> None:
        self.act_open = QAction("Open…", self)
        self.act_open.setShortcut(QKeySequence.Open)
        self.act_open.triggered.connect(self.open_file_dialog)

        self.act_paste = QAction("Paste from Clipboard", self)
        self.act_paste.setShortcut("Meta+V")  # also covered by Qt's default
        self.act_paste.triggered.connect(self.paste_from_clipboard)

        self.act_copy = QAction("Copy Message", self)
        self.act_copy.setShortcut(QKeySequence.Copy)
        self.act_copy.triggered.connect(self.copy_to_clipboard)

        self.act_clear = QAction("Clear", self)
        self.act_clear.setShortcut("Meta+K")
        self.act_clear.triggered.connect(self.clear)

    def _build_menubar(self) -> None:
        mb = self.menuBar()
        # On macOS, Qt auto-relocates these under the app menu where appropriate.
        file_menu = mb.addMenu("File")
        file_menu.addAction(self.act_open)
        file_menu.addSeparator()
        act_quit = QAction("Quit", self)
        act_quit.setShortcut(QKeySequence.Quit)
        act_quit.triggered.connect(QApplication.quit)
        file_menu.addAction(act_quit)

        edit_menu = mb.addMenu("Edit")
        edit_menu.addAction(self.act_paste)
        edit_menu.addAction(self.act_copy)
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_clear)

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main", self)
        tb.setMovable(False)
        tb.addAction(self.act_clear)
        tb.addAction(self.act_open)
        tb.addAction(self.act_copy)
        tb.addAction(self.act_paste)
        self.addToolBar(Qt.TopToolBarArea, tb)

    def _build_statusbar(self) -> None:
        bar = QStatusBar(self)
        self.setStatusBar(bar)
        self._status_label = QLabel("Ready", bar)
        bar.addWidget(self._status_label)

    def _wire_signals(self) -> None:
        self.segment_list.segmentSelected.connect(self._on_segment_selected)
        self.field_table.fieldSelected.connect(self._on_field_selected)
        self.repetition_table.repetitionSelected.connect(self._on_repetition_selected)
        self.component_table.componentSelected.connect(self._on_component_selected)
        self.raw_editor.segmentClicked.connect(self._on_raw_line_clicked)

    # ------------------------------------------------------------------
    # Data flow
    # ------------------------------------------------------------------

    def load_text(self, text: str, source_label: str = "clipboard") -> None:
        if not text or not text.strip():
            self._status(f"Nothing to parse ({source_label}).")
            return
        parsed = parse(text)
        self._parsed = parsed
        self.raw_editor.set_message(parsed.raw, parsed.encoding_chars)
        self.segment_list.load(parsed.segments)
        if parsed.segments:
            self._render_segment(0)

        header = f"{parsed.message_type}^{parsed.trigger_event}" if parsed.message_type else "unknown"
        msg_count = 1  # v1 single-message
        warn = f"  ⚠ {'; '.join(parsed.warnings)}" if parsed.warnings else ""
        self._status(
            f"{source_label} · {header} · v{parsed.version or '?'} · "
            f"{len(parsed.segments)} segments · {msg_count} message{warn}"
        )

    def load_path(self, path: str) -> None:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            QMessageBox.warning(self, "Open failed", str(e))
            return
        self.load_text(text, source_label=os.path.basename(path))

    def clear(self) -> None:
        self._parsed = None
        self.raw_editor.clear()
        self.segment_list.load([])
        self.field_table.load(None)
        self.repetition_table.load(None)
        self.component_table.load(None)
        self.subcomp_table.load(None)
        self._status("Cleared.")

    def copy_to_clipboard(self) -> None:
        if self._parsed is None:
            return
        QApplication.clipboard().setText(self._parsed.raw)
        self._status("Message copied to clipboard.")

    def paste_from_clipboard(self) -> None:
        text = QApplication.clipboard().text()
        self.load_text(text, source_label="clipboard")

    def open_file_dialog(self) -> None:
        filters = "HL7 (*.hl7 *.hl7v2 *.er7);;Text (*.txt);;All Files (*)"
        path, _ = QFileDialog.getOpenFileName(self, "Open HL7 Message", "", filters)
        if path:
            self.load_path(path)

    # ------------------------------------------------------------------
    # Selection cascade
    # ------------------------------------------------------------------

    def _render_segment(self, index: int) -> None:
        if not self._parsed or not (0 <= index < len(self._parsed.segments)):
            return
        seg = self._parsed.segments[index]
        self.field_table.load(seg)
        self.raw_editor.highlight_segment(index)

    def _on_segment_selected(self, index: int) -> None:
        self._render_segment(index)

    def _on_field_selected(self, row: int) -> None:
        if not self._parsed:
            return
        seg_row = self.segment_list.currentRow()
        if seg_row < 0:
            return
        seg = self._parsed.segments[seg_row]
        if 0 <= row < len(seg.fields):
            self.repetition_table.load(seg.fields[row], segment_name=seg.name)

    def _on_repetition_selected(self, row: int) -> None:
        if not self._parsed:
            return
        seg_row = self.segment_list.currentRow()
        field_row = self.field_table.currentRow()
        if seg_row < 0 or field_row < 0:
            return
        seg = self._parsed.segments[seg_row]
        if 0 <= field_row < len(seg.fields):
            f = seg.fields[field_row]
            if 0 <= row < len(f.repetitions):
                prefix = f"{seg.name}-{f.position}[{f.repetitions[row].index}]"
                self.component_table.load(f.repetitions[row], path_prefix=prefix)

    def _on_component_selected(self, row: int) -> None:
        if not self._parsed:
            return
        seg_row = self.segment_list.currentRow()
        field_row = self.field_table.currentRow()
        rep_row = self.repetition_table.currentRow()
        if seg_row < 0 or field_row < 0 or rep_row < 0:
            return
        seg = self._parsed.segments[seg_row]
        if field_row >= len(seg.fields):
            return
        f = seg.fields[field_row]
        if rep_row >= len(f.repetitions):
            return
        rep = f.repetitions[rep_row]
        if 0 <= row < len(rep.components):
            comp = rep.components[row]
            prefix = f"{seg.name}-{f.position}[{rep.index}].{comp.position}"
            self.subcomp_table.load(comp, path_prefix=prefix)

    def _on_raw_line_clicked(self, line_index: int) -> None:
        if not self._parsed:
            return
        if 0 <= line_index < len(self._parsed.segments):
            self.segment_list.setCurrentRow(line_index)

    # ------------------------------------------------------------------
    # Drag & drop
    # ------------------------------------------------------------------

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        md = event.mimeData()
        if md.hasUrls() and any(
            u.toLocalFile().lower().endswith(SUPPORTED_EXT) for u in md.urls()
        ):
            event.acceptProposedAction()
        elif md.hasText():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        md = event.mimeData()
        if md.hasUrls():
            for url in md.urls():
                p = url.toLocalFile()
                if p and os.path.isfile(p):
                    self.load_path(p)
                    return
        if md.hasText():
            self.load_text(md.text(), source_label="drop")

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def _status(self, text: str) -> None:
        self._status_label.setText(text)
