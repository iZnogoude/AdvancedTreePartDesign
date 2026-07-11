"""Register the Advanced Tree Part Design (ATPD) workbench with FreeCAD.

This module is loaded by FreeCAD's Gui at startup and is responsible for
declaring the workbench so it shows up in the workbench selector. It stays
deliberately minimal for M0: no commands or toolbars are registered yet,
those will be added as the corresponding features land.
"""

import os

import FreeCADGui as Gui

_ICON_PATH = os.path.join(
    os.path.dirname(__file__), "atpd", "resources", "icons", "atpd_workbench.svg"
)


class ATPDWorkbench(Gui.Workbench):
    """Minimal workbench skeleton for Advanced Tree Part Design."""

    MenuText = "Advanced Tree Part Design"
    ToolTip = "Advanced Tree Part Design workbench"
    Icon = _ICON_PATH

    def Initialize(self):
        """Register commands and menus. No-op for now (M0 skeleton)."""
        pass

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(ATPDWorkbench())
