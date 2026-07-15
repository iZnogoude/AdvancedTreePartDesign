"""Workbench command that opens the ATPD read-only feature tree panel."""

import FreeCADGui as Gui

from .panel import get_or_create_panel


class ShowFeatureTreeCommand:
    """Opens (or brings forward) the ATPD feature tree dock widget."""

    def GetResources(self):
        return {
            "MenuText": "Feature Tree",
            "ToolTip": "Show the ATPD feature tree panel",
        }

    def Activated(self):
        panel = get_or_create_panel(Gui.getMainWindow())
        panel.show()
        panel.raise_()

    def IsActive(self):
        return True


Gui.addCommand("ATPD_ShowFeatureTree", ShowFeatureTreeCommand())
