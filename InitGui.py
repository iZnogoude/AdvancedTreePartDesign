"""Register the Advanced Tree Part Design (ATPD) workbench with FreeCAD.

This module is loaded by FreeCAD's Gui at startup and is responsible for
declaring the workbench so it shows up in the workbench selector.
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
        """Register commands and menus."""
        from atpd.features import extrude_command  # noqa: F401  (registers ATPD_UnifiedExtrude)
        from atpd.tree import command  # noqa: F401  (registers ATPD_ShowFeatureTree on import)

        self.appendToolbar("ATPD", ["ATPD_ShowFeatureTree"])
        # Modeling toolbar (CDC section 3.2) - the unified extrusion is its
        # first command; other unified modeling functions (revolve, etc.)
        # will join it in later M4 issues.
        self.appendToolbar("Modeling", ["ATPD_UnifiedExtrude"])

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(ATPDWorkbench())
