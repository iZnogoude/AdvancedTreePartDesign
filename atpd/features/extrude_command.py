"""Workbench command that opens the unified Extrusion Task Panel.

Kept apart from extrude_task.py (which holds the actual Task Panel and is
imported by tests) for the same reason atpd/tree/command.py is kept apart
from atpd/tree/panel.py: Gui.addCommand() doesn't exist under FreeCADCmd's
stubbed FreeCADGui, so any module calling it at import time can't be
imported in the headless test suite.
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtWidgets

from .extrude_task import ExtrudeTaskPanel, resolve_profile


class UnifiedExtrudeCommand:
    """Workbench command opening the unified Extrusion Task Panel."""

    def GetResources(self):
        return {
            "MenuText": "Extrusion",
            "ToolTip": "Add or remove material by extruding a sketch or face (Pad/Pocket)",
        }

    def Activated(self):
        profile, sketch, error = resolve_profile()
        if error is not None:
            QtWidgets.QMessageBox.warning(Gui.getMainWindow(), "Extrusion", error)
            return
        Gui.Control.showDialog(ExtrudeTaskPanel(profile, sketch))

    def IsActive(self):
        return App.ActiveDocument is not None


Gui.addCommand("ATPD_UnifiedExtrude", UnifiedExtrudeCommand())
