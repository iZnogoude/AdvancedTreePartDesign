"""Read-only QDockWidget showing the active Body's feature tree (M1).

QTreeWidget rather than QTreeView + a custom QAbstractItemModel: M1 is a
flat, read-only list with no drag-drop, editing, or lazy loading, so the
extra model/view machinery isn't earning its keep yet. The Qt-free data
layer (model.py) is already factored out, so upgrading to a real item
model later - needed once M2 adds interaction - won't require touching
that layer.
"""

import FreeCADGui as Gui
from PySide6 import QtCore, QtGui, QtWidgets

from .model import ACTIVE, ERROR, SUPPRESSED, collect_body_features

_STATE_COLORS = {
    ACTIVE: None,
    SUPPRESSED: QtGui.QColor("gray"),
    ERROR: QtGui.QColor("red"),
}


def _active_body():
    """Return the active PartDesign Body of the active document, or None."""
    doc = Gui.ActiveDocument
    if doc is None:
        return None
    view = doc.ActiveView
    if view is None:
        return None
    return view.getActiveObject("pdbody")


class _TreeDocumentObserver:
    """Refreshes a callback when the active document or its objects change."""

    def __init__(self, on_change):
        self._on_change = on_change

    def slotActivateDocument(self, doc):
        self._on_change()

    def slotRecomputedObject(self, obj):
        self._on_change()

    def slotChangedObject(self, obj, prop):
        self._on_change()

    def slotDeletedObject(self, obj):
        self._on_change()


class FeatureTreePanel(QtWidgets.QDockWidget):
    """Dockable, read-only view of the active Body's feature chain."""

    def __init__(self, parent=None):
        super().__init__("ATPD - Feature Tree", parent)
        self.setObjectName("ATPD_FeatureTreePanel")

        self._tree = QtWidgets.QTreeWidget(self)
        self._tree.setColumnCount(2)
        self._tree.setHeaderLabels(["Feature", "Type"])
        self.setWidget(self._tree)

        self._observer = _TreeDocumentObserver(self.refresh)
        Gui.addDocumentObserver(self._observer)

        self.refresh()

    def refresh(self):
        """Rebuild the tree from the currently active Body, if any."""
        self._tree.clear()
        body = _active_body()
        if body is None:
            return
        for row in collect_body_features(body):
            item = QtWidgets.QTreeWidgetItem([row.label, row.type_id])
            color = _STATE_COLORS.get(row.state)
            if color is not None:
                item.setForeground(0, color)
                item.setForeground(1, color)
            self._tree.addTopLevelItem(item)

    def closeEvent(self, event: QtCore.QEvent) -> None:
        Gui.removeDocumentObserver(self._observer)
        super().closeEvent(event)
