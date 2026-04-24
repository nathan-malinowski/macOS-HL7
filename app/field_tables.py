"""Right-side tables: fields, components, repetitions, sub-components.

Each table has three columns: #, Name [Type], Value. Values can be copied by:
  • ⌘C — copies selected rows as tab-separated text (path/label/value)
  • Double-click on a row — copies that row's value
  • Right-click — context menu: Copy Value, Copy Row, Copy as JSON
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHeaderView,
    QMenu,
    QTableWidget,
    QTableWidgetItem,
)

from .hl7_model import ParsedComponent, ParsedField, ParsedRepetition, ParsedSegment

_COL_POS = 0
_COL_LABEL = 1
_COL_VALUE = 2


def _mono_font() -> QFont:
    f = QFont("Menlo", 11)
    f.setStyleHint(QFont.Monospace)
    return f


def _cell(value: str) -> QTableWidgetItem:
    item = QTableWidgetItem(value)
    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
    return item


def _label_with_type(name: str, datatype: str) -> str:
    return f"{name} [{datatype}]" if datatype else name


class _CopyableTable(QTableWidget):
    """Base table with value-focused copy behavior. Subclasses define the
    label heading and implement ``_row_json(row)`` for JSON export."""

    def __init__(self, label_heading: str, parent=None):
        super().__init__(0, 3, parent)
        self.setHorizontalHeaderLabels(["#", label_heading, "Value"])
        self.setFont(_mono_font())
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.horizontalHeader().setStretchLastSection(True)
        self.setAlternatingRowColors(True)
        self.setColumnWidth(_COL_POS, 60)
        self.setColumnWidth(_COL_LABEL, 260)

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.cellDoubleClicked.connect(self._on_double_click)

    # -- Row data API (subclasses override) --------------------------------

    def _row_json(self, row: int) -> Optional[Dict[str, Any]]:
        """Return a dict for the row suitable for JSON serialization, or None
        if the row is out of range."""
        raise NotImplementedError

    def _row_value(self, row: int) -> str:
        item = self.item(row, _COL_VALUE)
        return item.text() if item else ""

    def _row_label(self, row: int) -> str:
        item = self.item(row, _COL_LABEL)
        return item.text() if item else ""

    def _row_path(self, row: int) -> str:
        item = self.item(row, _COL_POS)
        return item.text() if item else ""

    # -- Selection helpers -------------------------------------------------

    def _selected_rows(self) -> List[int]:
        return sorted({idx.row() for idx in self.selectionModel().selectedRows()})

    # -- Keyboard copy -----------------------------------------------------

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.matches(QKeySequence.Copy):
            self._copy_selected_tsv()
            event.accept()
            return
        super().keyPressEvent(event)

    def _copy_selected_tsv(self) -> None:
        rows = self._selected_rows()
        if not rows:
            return
        lines = []
        for r in rows:
            lines.append(
                "\t".join(
                    [self._row_path(r), self._row_label(r), self._row_value(r)]
                )
            )
        QApplication.clipboard().setText("\n".join(lines))

    # -- Double-click copy -------------------------------------------------

    def _on_double_click(self, row: int, _col: int) -> None:
        value = self._row_value(row)
        if value:
            QApplication.clipboard().setText(value)

    # -- Context menu ------------------------------------------------------

    def _on_context_menu(self, pos) -> None:
        row = self.rowAt(pos.y())
        if row < 0:
            return
        # If the right-clicked row isn't part of the current selection,
        # replace the selection with just that row (Finder-like behavior).
        if row not in self._selected_rows():
            self.clearSelection()
            self.selectRow(row)

        rows = self._selected_rows()
        menu = QMenu(self)

        act_value = menu.addAction(
            "Copy Value" if len(rows) == 1 else f"Copy Values ({len(rows)})"
        )
        act_row = menu.addAction(
            "Copy Row" if len(rows) == 1 else f"Copy Rows ({len(rows)})"
        )
        menu.addSeparator()
        act_json = menu.addAction(
            "Copy as JSON" if len(rows) == 1 else f"Copy as JSON ({len(rows)})"
        )

        chosen = menu.exec(self.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen is act_value:
            self._copy_values(rows)
        elif chosen is act_row:
            self._copy_selected_tsv()
        elif chosen is act_json:
            self._copy_json(rows)

    def _copy_values(self, rows: List[int]) -> None:
        text = "\n".join(self._row_value(r) for r in rows)
        QApplication.clipboard().setText(text)

    def _copy_json(self, rows: List[int]) -> None:
        records = [self._row_json(r) for r in rows]
        records = [rec for rec in records if rec is not None]
        if not records:
            return
        payload = records[0] if len(records) == 1 else records
        QApplication.clipboard().setText(json.dumps(payload, indent=2))


# ---------------------------------------------------------------------------
# Concrete tables
# ---------------------------------------------------------------------------


class FieldTable(_CopyableTable):
    """Top-left pane. Fields of the selected segment."""

    fieldSelected = Signal(int)

    def __init__(self, parent=None):
        super().__init__("Field", parent)
        self._fields: List[ParsedField] = []
        self._segment_name: str = ""
        self.currentCellChanged.connect(self._on_cell_changed)

    def load(self, segment: Optional[ParsedSegment]) -> None:
        self.blockSignals(True)
        self.setRowCount(0)
        self._fields = segment.fields if segment else []
        self._segment_name = segment.name if segment else ""
        for f in self._fields:
            row = self.rowCount()
            self.insertRow(row)
            self.setItem(row, _COL_POS, _cell(f"{self._segment_name}-{f.position}"))
            self.setItem(row, _COL_LABEL, _cell(_label_with_type(f.name, f.datatype)))
            rep_count = len(f.repetitions)
            value_text = (
                f.raw if rep_count <= 1 else f"{f.raw}   [{rep_count} repetitions]"
            )
            self.setItem(row, _COL_VALUE, _cell(value_text))
        self.blockSignals(False)
        if self._fields:
            self.setCurrentCell(0, _COL_LABEL)

    def _on_cell_changed(self, current_row: int, *_) -> None:
        if 0 <= current_row < len(self._fields):
            self.fieldSelected.emit(current_row)

    def _row_json(self, row: int) -> Optional[Dict[str, Any]]:
        if not (0 <= row < len(self._fields)):
            return None
        f = self._fields[row]
        return {
            "path": f"{self._segment_name}-{f.position}",
            "name": f.name,
            "datatype": f.datatype,
            "value": f.raw,
            "repetitions": len(f.repetitions),
        }


class RepetitionTable(_CopyableTable):
    """Bottom-left pane. Repetitions of the selected field."""

    repetitionSelected = Signal(int)

    def __init__(self, parent=None):
        super().__init__("Repeat", parent)
        self._repetitions: List[ParsedRepetition] = []
        self._segment_name: str = ""
        self._field_position: int = 0
        self.currentCellChanged.connect(self._on_cell_changed)

    def load(
        self,
        field: Optional[ParsedField],
        segment_name: str = "",
    ) -> None:
        self.blockSignals(True)
        self.setRowCount(0)
        self._repetitions = field.repetitions if field else []
        self._segment_name = segment_name
        self._field_position = field.position if field else 0
        for r in self._repetitions:
            row = self.rowCount()
            self.insertRow(row)
            self.setItem(row, _COL_POS, _cell(self._path(r.index)))
            self.setItem(row, _COL_LABEL, _cell(f"Repetition {r.index + 1}"))
            self.setItem(row, _COL_VALUE, _cell(r.raw))
        self.blockSignals(False)
        if self._repetitions:
            self.setCurrentCell(0, _COL_LABEL)

    def _path(self, index: int) -> str:
        if not self._segment_name:
            return str(index + 1)
        return f"{self._segment_name}-{self._field_position}[{index}]"

    def _on_cell_changed(self, current_row: int, *_) -> None:
        if 0 <= current_row < len(self._repetitions):
            self.repetitionSelected.emit(current_row)

    def _row_json(self, row: int) -> Optional[Dict[str, Any]]:
        if not (0 <= row < len(self._repetitions)):
            return None
        r = self._repetitions[row]
        return {
            "path": self._path(r.index),
            "index": r.index,
            "value": r.raw,
        }


class ComponentTable(_CopyableTable):
    """Top-right pane. Components of the selected repetition."""

    componentSelected = Signal(int)

    def __init__(self, parent=None):
        super().__init__("Component", parent)
        self._components: List[ParsedComponent] = []
        self._path_prefix: str = ""
        self.currentCellChanged.connect(self._on_cell_changed)

    def load(
        self,
        repetition: Optional[ParsedRepetition],
        path_prefix: str = "",
    ) -> None:
        self.blockSignals(True)
        self.setRowCount(0)
        self._components = repetition.components if repetition else []
        self._path_prefix = path_prefix
        for c in self._components:
            row = self.rowCount()
            self.insertRow(row)
            self.setItem(row, _COL_POS, _cell(self._path(c.position)))
            self.setItem(row, _COL_LABEL, _cell(_label_with_type(c.name, c.datatype)))
            self.setItem(row, _COL_VALUE, _cell(c.raw))
        self.blockSignals(False)
        if self._components:
            self.setCurrentCell(0, _COL_LABEL)

    def _path(self, position: int) -> str:
        if not self._path_prefix:
            return str(position)
        return f"{self._path_prefix}.{position}"

    def _on_cell_changed(self, current_row: int, *_) -> None:
        if 0 <= current_row < len(self._components):
            self.componentSelected.emit(current_row)

    def _row_json(self, row: int) -> Optional[Dict[str, Any]]:
        if not (0 <= row < len(self._components)):
            return None
        c = self._components[row]
        return {
            "path": self._path(c.position),
            "name": c.name,
            "datatype": c.datatype,
            "value": c.raw,
        }


class SubcomponentTable(_CopyableTable):
    """Bottom-right pane. Sub-components of the selected component."""

    def __init__(self, parent=None):
        super().__init__("Sub-component", parent)
        self._component: Optional[ParsedComponent] = None
        self._path_prefix: str = ""

    def load(
        self,
        component: Optional[ParsedComponent],
        path_prefix: str = "",
    ) -> None:
        self.setRowCount(0)
        self._component = component
        self._path_prefix = path_prefix
        if not component:
            return
        for sub in component.subcomponents:
            row = self.rowCount()
            self.insertRow(row)
            self.setItem(row, _COL_POS, _cell(self._path(sub.position)))
            self.setItem(
                row, _COL_LABEL, _cell(_label_with_type(sub.name, sub.datatype))
            )
            self.setItem(row, _COL_VALUE, _cell(sub.value))

    def _path(self, position: int) -> str:
        if not self._path_prefix:
            return str(position)
        return f"{self._path_prefix}.{position}"

    def _row_json(self, row: int) -> Optional[Dict[str, Any]]:
        if not self._component or not (0 <= row < len(self._component.subcomponents)):
            return None
        sub = self._component.subcomponents[row]
        return {
            "path": self._path(sub.position),
            "name": sub.name,
            "datatype": sub.datatype,
            "value": sub.value,
        }
