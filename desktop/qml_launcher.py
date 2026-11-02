#!/usr/bin/env python3
"""Minimal QML host for the Continuity desktop client.

`pyside6-qml` is not shipped by every PySide6 build, so the AppImage and the portable archive use
this launcher instead. Arguments are forwarded untouched: Main.qml reads ``--api-config=<path>``
from ``Qt.application.arguments`` and never receives the bearer token itself.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    here = Path(__file__).resolve().parent
    qml = here / "qml" / "Main.qml"
    if not qml.is_file():
        print(f"missing QML entry point: {qml}", file=sys.stderr)
        return 2
    app = QGuiApplication(argv)
    app.setApplicationName("Continuity")
    app.setDesktopFileName("continuity")
    engine = QQmlApplicationEngine()
    engine.load(str(qml))
    if not engine.rootObjects():
        print("QML failed to load (see the messages above)", file=sys.stderr)
        return 1
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
