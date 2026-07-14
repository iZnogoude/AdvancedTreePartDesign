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
    delete_objects,
    find_dependents,
    isolate_object,
    rename_label,
    restore_visibilities,
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
    - double-click a feature to suppress/unsuppress it
    - F2, or clicking an already-selected feature, to rename it inline
    - right-click for the full menu: Suppress/Unsuppress, Edit, Delete,
      Delete with Children, Go to Sketch (only if the feature has one),
      Isolate/Restore Visibility
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

        # Isolate/restore-visibility toggle state - which object (if any)
        # is currently isolated, and the visibility every object in the
        # body had right before that, so a second click can undo it.
        self._isolated_name: str | None = None
        self._isolated_saved_visibility: dict[str, bool] = {}

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

    def _find_sketch_child(
        self, item: QtWidgets.QTreeWidgetItem
    ) -> QtWidgets.QTreeWidgetItem | None:
        """The item's direct child that represents a Sketch, if any."""
        for i in range(item.childCount()):
            child_item = item.child(i)
            child_obj = self._resolve_object(child_item)
            if child_obj is not None and child_obj.TypeId == "Sketcher::SketchObject":
                return child_item
        return None

    def _on_context_menu(self, pos: QtCore.QPoint) -> None:
        item = self._tree.itemAt(pos)
        obj = self._resolve_object(item) if item is not None else None
        if obj is None:
            return

        menu = QtWidgets.QMenu(self._tree)

        suppress_action = None
        if hasattr(obj, "Suppressed"):
            suppress_action = menu.addAction("Unsuppress" if obj.Suppressed else "Suppress")

        edit_action = menu.addAction("Edit")

        menu.addSeparator()
        delete_action = menu.addAction("Delete")
        delete_children_action = (
            menu.addAction("Delete with Children") if item.childCount() > 0 else None
        )

        sketch_child = self._find_sketch_child(item)
        goto_sketch_action = None
        if sketch_child is not None:
            menu.addSeparator()
            goto_sketch_action = menu.addAction("Go to Sketch")

        menu.addSeparator()
        isolate_action = menu.addAction(
            "Restore Visibility" if self._isolated_name == obj.Name else "Isolate"
        )

        chosen = menu.exec(self._tree.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen is suppress_action:
            self._toggle_suppress(obj)
        elif chosen is edit_action:
            self._edit_object(obj)
        elif chosen is delete_action:
            self._delete_object(obj)
        elif chosen is delete_children_action:
            self._delete_object_with_children(item, obj)
        elif chosen is goto_sketch_action:
            self._goto_sketch(sketch_child)
        elif chosen is isolate_action:
            self._toggle_isolate(obj)

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

    def _edit_object(self, obj) -> None:
        """Open obj in its native edit dialog - the same mechanism a
        double-click on its icon triggers in the native tree."""
        gui_doc = Gui.ActiveDocument
        if gui_doc is None:
            return
        App.Console.PrintMessage(f"ATPD tree DEBUG: setEdit({obj.Name})\n")
        gui_doc.setEdit(obj.Name)

    def _delete_object(self, obj) -> None:
        """Permanently delete obj (not Suppress), after confirmation."""
        dependents = find_dependents(obj)
        App.Console.PrintMessage(
            f"ATPD tree DEBUG: delete requested for {obj.Name}, "
            f"{len(dependents)} dependent(s)\n"
        )
        text = f'Permanently delete "{obj.Label}"?\n\nThis action is irreversible.'
        if dependents:
            names = ", ".join(dep.Label for dep in dependents)
            text += f"\n\nDependent feature(s) that may break: {names}."

        reply = QtWidgets.QMessageBox.warning(
            self,
            "Confirm delete",
            text,
            QtWidgets.QMessageBox.StandardButton.Ok | QtWidgets.QMessageBox.StandardButton.Cancel,
        )
        if reply != QtWidgets.QMessageBox.StandardButton.Ok:
            App.Console.PrintMessage("ATPD tree DEBUG: delete cancelled by user\n")
            return

        try:
            delete_objects(obj.Document, [obj.Name])
        except Exception as exc:
            App.Console.PrintError(f"ATPD tree: failed to delete {obj.Name}: {exc}\n")
            QtWidgets.QMessageBox.critical(self, "Error", f'Failed to delete "{obj.Label}":\n{exc}')
            return

        App.Console.PrintMessage(f"ATPD tree DEBUG: deleted {obj.Name}\n")
        self.refresh()

    def _delete_object_with_children(
        self, item: QtWidgets.QTreeWidgetItem, obj
    ) -> None:
        """Permanently delete obj and its direct children, after confirmation."""
        children = [
            child_obj
            for i in range(item.childCount())
            if (child_obj := self._resolve_object(item.child(i))) is not None
        ]
        dependents = find_dependents(obj)
        App.Console.PrintMessage(
            f"ATPD tree DEBUG: delete-with-children requested for {obj.Name}, "
            f"{len(children)} child(ren), {len(dependents)} other dependent(s)\n"
        )

        child_labels = ", ".join(child.Label for child in children)
        text = (
            f'Permanently delete "{obj.Label}" and its {len(children)} child feature(s) '
            f"({child_labels})?\n\nThis action is irreversible."
        )
        if dependents:
            names = ", ".join(dep.Label for dep in dependents)
            text += f"\n\nOther dependent feature(s) that may break: {names}."

        reply = QtWidgets.QMessageBox.warning(
            self,
            "Confirm delete with children",
            text,
            QtWidgets.QMessageBox.StandardButton.Ok | QtWidgets.QMessageBox.StandardButton.Cancel,
        )
        if reply != QtWidgets.QMessageBox.StandardButton.Ok:
            App.Console.PrintMessage("ATPD tree DEBUG: delete-with-children cancelled by user\n")
            return

        try:
            delete_objects(obj.Document, [child.Name for child in children] + [obj.Name])
        except Exception as exc:
            App.Console.PrintError(
                f"ATPD tree: failed to delete {obj.Name} with children: {exc}\n"
            )
            QtWidgets.QMessageBox.critical(
                self, "Error", f'Failed to delete "{obj.Label}" with children:\n{exc}'
            )
            return

        App.Console.PrintMessage(
            f"ATPD tree DEBUG: deleted {obj.Name} and {len(children)} child(ren)\n"
        )
        self.refresh()

    def _goto_sketch(self, sketch_item: QtWidgets.QTreeWidgetItem) -> None:
        """Select and reveal a feature's sketch, in both trees, without editing it."""
        obj = self._resolve_object(sketch_item)
        if obj is None:
            return
        App.Console.PrintMessage(f"ATPD tree DEBUG: go to sketch {obj.Name}\n")
        self._tree.setCurrentItem(sketch_item)
        self._tree.scrollToItem(sketch_item)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(obj.Document.Name, obj.Name)

    def _toggle_isolate(self, obj) -> None:
        """Hide every other object in the Body, or restore visibility.

        Purely visual (ViewObject.Visibility) - never touches Suppressed,
        and needs no transaction since it isn't a document-structure
        change.
        """
        if self._isolated_name == obj.Name:
            App.Console.PrintMessage(
                f"ATPD tree DEBUG: restoring visibility (was isolating {obj.Name})\n"
            )
            restore_visibilities(obj.Document, self._isolated_saved_visibility)
            self._isolated_name = None
            self._isolated_saved_visibility = {}
            return

        body = _active_body()
        if body is None:
            return
        App.Console.PrintMessage(f"ATPD tree DEBUG: isolating {obj.Name}\n")
        self._isolated_saved_visibility = isolate_object(body.Group, obj)
        self._isolated_name = obj.Name
