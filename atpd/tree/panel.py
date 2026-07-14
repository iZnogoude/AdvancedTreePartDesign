"""Read-only QDockWidget showing the active Body's feature tree (M1).

QTreeWidget rather than QTreeView + a custom QAbstractItemModel: M1 has
no drag-drop, editing, or lazy loading, so the extra model/view
machinery isn't earning its keep yet - QTreeWidgetItem nesting is enough
to show a consumed sketch under the feature that uses it. The Qt-free
data layer (model.py) is already factored out, so upgrading to a real
item model later - needed once M2 adds interaction - won't require
touching that layer.
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtCore, QtGui, QtWidgets

from .model import ERROR, SUPPRESSED, FeatureRow, collect_body_features, count_rows


def _active_body():
    """Return the active PartDesign Body of the active document, or None.

    Prefers the Gui-tracked "active body" (view.getActiveObject("pdbody")),
    but that is only set once a Body has been explicitly activated (e.g.
    double-clicked in the native tree) - a document that was already open
    when the panel appeared may have a Body nobody has activated yet. Fall
    back to scanning the document's objects by TypeId (never by name/Label,
    which is user-editable and can be anything, e.g. "Corps").
    """
    doc = App.ActiveDocument
    if doc is None:
        App.Console.PrintMessage("ATPD tree DEBUG: App.ActiveDocument is None\n")
        return None
    App.Console.PrintMessage(f"ATPD tree DEBUG: active document = {doc.Name}\n")

    gui_doc = Gui.ActiveDocument
    view = gui_doc.ActiveView if gui_doc is not None else None
    body = view.getActiveObject("pdbody") if view is not None else None
    if body is not None:
        App.Console.PrintMessage(f"ATPD tree DEBUG: Gui-tracked active body = {body.Name}\n")
        return body

    App.Console.PrintMessage(
        "ATPD tree DEBUG: no Gui-tracked active body, scanning objects by TypeId\n"
    )
    bodies = [obj for obj in doc.Objects if obj.TypeId == "PartDesign::Body"]
    App.Console.PrintMessage(
        f"ATPD tree DEBUG: found {len(bodies)} PartDesign::Body object(s) by scan\n"
    )
    return bodies[0] if bodies else None


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


def _make_item(row: FeatureRow) -> QtWidgets.QTreeWidgetItem:
    """Build a QTreeWidgetItem for a row, recursively nesting its children."""
    item = QtWidgets.QTreeWidgetItem([row.label, row.type_id])
    item.setToolTip(0, row.label)
    item.setToolTip(1, row.type_id)

    if row.state == SUPPRESSED:
        # Never hardcode a color: a gray that reads fine in a light theme
        # can be unreadable in a dark one, and a plain setForeground() can
        # also get overridden by a theme's stylesheet. Disabling the item
        # lets Qt's style engine dim it using the *current* palette on
        # its own, and explicitly reading the palette's disabled-text
        # role as a backup covers styles that don't dim disabled items
        # much. The tree is read-only in M1 anyway, so losing
        # selectability costs nothing yet - revisit if M2 needs to select
        # a suppressed row (e.g. to unsuppress it).
        item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEnabled)
        disabled_text = QtWidgets.QApplication.palette().color(
            QtGui.QPalette.ColorGroup.Disabled, QtGui.QPalette.ColorRole.Text
        )
        for column in (0, 1):
            font = item.font(column)
            font.setItalic(True)
            item.setFont(column, font)
            item.setForeground(column, disabled_text)
    elif row.state == ERROR:
        icon = QtWidgets.QApplication.style().standardIcon(
            QtWidgets.QStyle.StandardPixmap.SP_MessageBoxWarning
        )
        item.setIcon(0, icon)

    for child in row.children:
        item.addChild(_make_item(child))
    return item


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

        App.Console.PrintMessage("ATPD tree DEBUG: panel __init__, running initial refresh()\n")
        self.refresh()

    def refresh(self):
        """Rebuild the tree from the currently active Body, if any."""
        App.Console.PrintMessage("ATPD tree DEBUG: refresh() called\n")
        self._tree.clear()
        body = _active_body()
        if body is None:
            App.Console.PrintMessage("ATPD tree DEBUG: refresh() found no body, tree left empty\n")
            return
        rows = collect_body_features(body)
        App.Console.PrintMessage(
            f"ATPD tree DEBUG: refresh() got {len(rows)} top-level row(s), "
            f"{count_rows(rows)} total (incl. nested) from body {body.Name}\n"
        )
        for row in rows:
            self._tree.addTopLevelItem(_make_item(row))
        self._tree.expandAll()
        self._tree.resizeColumnToContents(0)
        self._tree.resizeColumnToContents(1)

    def closeEvent(self, event: QtCore.QEvent) -> None:
        Gui.removeDocumentObserver(self._observer)
        super().closeEvent(event)
