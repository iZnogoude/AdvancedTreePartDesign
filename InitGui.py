"""Register the Advanced Tree Part Design (ATPD) workbench with FreeCAD.

This module is loaded by FreeCAD's Gui at startup and is responsible for
declaring the workbench so it shows up in the workbench selector. It stays
deliberately minimal for M0: no commands or toolbars are registered yet,
those will be added as the corresponding features land.
"""

import FreeCADGui as Gui


class ATPDWorkbench(Gui.Workbench):
    """Minimal workbench skeleton for Advanced Tree Part Design."""

    MenuText = "Advanced Tree Part Design"
    ToolTip = "Advanced Tree Part Design workbench"
    # No icon yet: the Addon Manager appears to run InitGui.py before
    # FreeCAD/App is fully initialized, so any icon path computation at
    # module level is fragile. Real icon loading is deferred to
    # Initialize() - see the tracking issue for details.
    Icon = ""

    def Initialize(self):
        """Register commands and menus. No-op for now (M0 skeleton)."""
        pass

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(ATPDWorkbench())
