"""Workbench command that opens the ATPD read-only feature tree panel."""

import FreeCADGui as Gui
from PySide6 import QtCore

from .panel import FeatureTreePanel

_panel = None


class ShowFeatureTreeCommand:
    """Opens (or brings forward) the ATPD feature tree dock widget."""

    def GetResources(self):
        return {
            "MenuText": "Feature Tree",
            "ToolTip": "Show the ATPD feature tree panel",
        }

    def Activated(self):
        global _panel
        main_window = Gui.getMainWindow()
        if _panel is None:
            _panel = FeatureTreePanel(main_window)
            main_window.addDockWidget(QtCore.Qt.RightDockWidgetArea, _panel)
        _panel.show()
        _panel.raise_()

    def IsActive(self):
        return True


Gui.addCommand("ATPD_ShowFeatureTree", ShowFeatureTreeCommand())
