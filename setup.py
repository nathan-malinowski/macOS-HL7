"""
py2app build config for macOS-HL7.

Usage:
    python setup.py py2app
"""
import os
from setuptools import setup

APP = ["launch.py"]
APP_NAME = "macOS-HL7"

_zprofiles_present = os.path.isdir("app/zprofiles/zprofiles")

_includes = [
    "app",
    "app.main_window",
    "app.raw_editor",
    "app.segment_list",
    "app.field_tables",
    "app.hl7_model",
]
if _zprofiles_present:
    _includes.append("app.zprofiles.zprofiles")

OPTIONS = {
    "argv_emulation": False,
    "emulate_shell_environment": True,
    "packages": ["hl7apy", "yaml", "PySide6"],
    "includes": _includes,
    "resources": ["app/zprofiles"] if _zprofiles_present else [],
    "plist": {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": "com.malinowski.macoshl7",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "NSHumanReadableCopyright": "Copyright © 2026 Nathan Malinowski. MIT Licensed.",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "12.0",
        "NSRequiresAquaSystemAppearance": False,
        "CFBundleDocumentTypes": [
            {
                "CFBundleTypeName": "HL7 Message",
                "CFBundleTypeExtensions": ["hl7", "hl7v2", "er7"],
                "CFBundleTypeRole": "Viewer",
                "LSHandlerRank": "Alternate",
            }
        ],
    },
}

setup(
    app=APP,
    name=APP_NAME,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
