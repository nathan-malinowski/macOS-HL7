"""Entry point for macOS-HL7."""
from __future__ import annotations

import sys

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


class _App(QApplication):
    """Application subclass that handles macOS FileOpen events (when a user
    double-clicks an associated .hl7 file in Finder or drops one on the Dock
    icon)."""

    def __init__(self, argv):
        super().__init__(argv)
        self._window: MainWindow | None = None

    def set_window(self, window: MainWindow) -> None:
        self._window = window

    def event(self, ev: QEvent) -> bool:
        if ev.type() == QEvent.FileOpen and self._window is not None:
            self._window.load_path(ev.file())
            return True
        return super().event(ev)


def main() -> int:
    app = _App(sys.argv)
    app.setApplicationName("macOS-HL7")
    app.setOrganizationName("Malinowski")
    app.setOrganizationDomain("malinowski.com")

    window = MainWindow()
    app.set_window(window)

    # Command-line file argument (non-bundle launch)
    for arg in sys.argv[1:]:
        if arg and not arg.startswith("-"):
            window.load_path(arg)
            break

    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
