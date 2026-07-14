"""QDockWidget showing the active Body's feature tree, with suppress toggling.

QTreeWidget rather than QTreeView + a custom QAbstractItemModel: there's
still no drag-drop or lazy loading, so the extra model/view machinery
isn't earning its keep yet - QTreeWidgetItem nesting is enough to show a
consumed sketch under the feature that uses it, and item flags/data are
enough for the M2 suppress/unsuppress interaction added here. The
Qt-free data layer (model.py) is already factored out, so upgrading to
a real item model later - if drag-drop reordering needs it - won't
require touching that layer.
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtCore, QtGui, QtWidgets

from .model import (
    ERROR,
    SUPPRESSED,
    FeatureRow,
    collect_body_features,
    count_rows,
    find_dependents,
    rename_label,
    toggle_suppressed,
)

_NAME_ROLE = QtCore.Qt.ItemDataRole.UserRole


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
    item.setData(0, _NAME_ROLE, row.name)
    # Qt.ItemIsEditable is per-item, not per-column - it also technically
    # makes the Type column editable. _on_item_changed() below only ever
    # acts on column 0, so editing column 1 is a harmless no-op that the
    # next refresh() silently overwrites back to the real type.
    item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsEditable)

    if row.state == SUPPRESSED:
        # Never hardcode a color: a gray that reads fine in a light theme
        # can be unreadable in a dark one. Read the *current* palette's
        # disabled-text color instead - theme-safe without hardcoding
        # anything. This item deliberately keeps Qt.ItemFlag.ItemIsEnabled
        # set (unlike the M1 version): suppressed rows must stay
        # double-clickable/right-clickable so they can be unsuppressed
        # from here.
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
    """Dockable view of the active Body's feature chain.

    Read-only display plus a few interactions:
    - double-click or right-click a feature to suppress/unsuppress it
    - F2, or clicking an already-selected feature, to rename it inline
    """

    def __init__(self, parent=None):
        super().__init__("ATPD - Feature Tree", parent)
        self.setObjectName("ATPD_FeatureTreePanel")

        self._tree = QtWidgets.QTreeWidget(self)
        self._tree.setColumnCount(2)
        self._tree.setHeaderLabels(["Feature", "Type"])
        self._tree.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        # EditKeyPressed = F2. SelectedClicked = clicking an item that is
        # already selected, same convention native file explorers use for
        # rename - deliberately *not* DoubleClicked, which already means
        # suppress/unsuppress here (see _on_item_double_clicked).
        self._tree.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.EditKeyPressed
            | QtWidgets.QAbstractItemView.EditTrigger.SelectedClicked
        )
        self._tree.itemChanged.connect(self._on_item_changed)
        self.setWidget(self._tree)

        self._observer = _TreeDocumentObserver(self.refresh)
        Gui.addDocumentObserver(self._observer)

        App.Console.PrintMessage("ATPD tree DEBUG: panel __init__, running initial refresh()\n")
        self.refresh()

    def refresh(self):
        """Rebuild the tree from the currently active Body, if any."""
        App.Console.PrintMessage("ATPD tree DEBUG: refresh() called\n")
        # Rebuilding the tree calls addTopLevelItem()/setText() on items
        # that aren't user edits - block itemChanged while doing it so
        # _on_item_changed() never mistakes a rebuild for a rename.
        self._tree.blockSignals(True)
        try:
            self._tree.clear()
            body = _active_body()
            if body is None:
                App.Console.PrintMessage(
                    "ATPD tree DEBUG: refresh() found no body, tree left empty\n"
                )
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
        finally:
            self._tree.blockSignals(False)

    def closeEvent(self, event: QtCore.QEvent) -> None:
        Gui.removeDocumentObserver(self._observer)
        super().closeEvent(event)

    def _resolve_object(self, item: QtWidgets.QTreeWidgetItem):
        """The live FreeCAD object an item represents, or None."""
        name = item.data(0, _NAME_ROLE)
        doc = App.ActiveDocument
        if doc is None or not name:
            return None
        return doc.getObject(name)

    def _on_item_double_clicked(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        self._try_toggle_suppress(item)

    def _on_context_menu(self, pos: QtCore.QPoint) -> None:
        item = self._tree.itemAt(pos)
        obj = self._resolve_object(item) if item is not None else None
        if obj is None or not hasattr(obj, "Suppressed"):
            return

        menu = QtWidgets.QMenu(self._tree)
        label = "Unsuppress" if obj.Suppressed else "Suppress"
        action = menu.addAction(label)
        chosen = menu.exec(self._tree.viewport().mapToGlobal(pos))
        if chosen is action:
            self._toggle_suppress(obj)

    def _try_toggle_suppress(self, item: QtWidgets.QTreeWidgetItem) -> None:
        obj = self._resolve_object(item)
        if obj is None or not hasattr(obj, "Suppressed"):
            App.Console.PrintMessage(
                "ATPD tree DEBUG: double-click on a non-suppressible item, ignored\n"
            )
            return
        self._toggle_suppress(obj)

    def _toggle_suppress(self, obj) -> None:
        """Suppress/unsuppress obj, warning about dependents first if any."""
        action = "unsuppress" if obj.Suppressed else "suppress"
        dependents = find_dependents(obj)
        App.Console.PrintMessage(
            f"ATPD tree DEBUG: {action} requested for {obj.Name}, "
            f"{len(dependents)} dependent(s)\n"
        )

        if dependents:
            names = ", ".join(dep.Label for dep in dependents)
            reply = QtWidgets.QMessageBox.question(
                self,
                f"Confirm {action}",
                f'"{obj.Label}" has {len(dependents)} dependent feature(s) that may be '
                f"affected: {names}.\n\nContinue?",
                QtWidgets.QMessageBox.StandardButton.Ok
                | QtWidgets.QMessageBox.StandardButton.Cancel,
            )
            if reply != QtWidgets.QMessageBox.StandardButton.Ok:
                App.Console.PrintMessage(f"ATPD tree DEBUG: {action} cancelled by user\n")
                return

        try:
            new_value = toggle_suppressed(obj.Document, obj)
        except Exception as exc:
            App.Console.PrintError(f"ATPD tree: failed to {action} {obj.Name}: {exc}\n")
            QtWidgets.QMessageBox.critical(
                self, "Error", f'Failed to {action} "{obj.Label}":\n{exc}'
            )
            return

        App.Console.PrintMessage(f"ATPD tree DEBUG: {obj.Name}.Suppressed -> {new_value}\n")
        self.refresh()

    def _on_item_changed(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        """Apply an inline-edited label to the real object, or restore it.

        Enter commits the edit (firing this), Escape cancels it without
        firing anything - both handled by Qt's built-in item editor, no
        custom keyPressEvent needed here.
        """
        if column != 0:
            return
        obj = self._resolve_object(item)
        if obj is None:
            return

        new_text = item.text(0)
        try:
            applied = rename_label(obj.Document, obj, new_text)
        except Exception as exc:
            App.Console.PrintError(f"ATPD tree: failed to rename {obj.Name}: {exc}\n")
            QtWidgets.QMessageBox.critical(
                self, "Error", f'Failed to rename "{obj.Label}":\n{exc}'
            )
            item.setText(0, obj.Label)
            return

        if applied:
            App.Console.PrintMessage(f"ATPD tree DEBUG: {obj.Name}.Label -> {obj.Label!r}\n")
            self.refresh()
        else:
            App.Console.PrintMessage(
                f"ATPD tree DEBUG: rename of {obj.Name} rejected (blank or unchanged), "
                f"restoring {obj.Label!r}\n"
            )
            item.setText(0, obj.Label)
