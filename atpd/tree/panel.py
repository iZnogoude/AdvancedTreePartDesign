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
    create_group,
    delete_objects,
    dissolve_group,
    find_dependencies,
    find_dependents,
    find_downstream_dressup_risk,
    insert_feature_at_rollback_bar,
    is_hover_highlight_enabled,
    is_solid_feature,
    isolate_object,
    load_groups,
    move_rollback_bar,
    move_to_group,
    rename_group,
    rename_label,
    restore_visibilities,
    set_hover_highlight_enabled,
    toggle_suppressed,
)

_NAME_ROLE = QtCore.Qt.ItemDataRole.UserRole
_IS_GROUP_ROLE = QtCore.Qt.ItemDataRole.UserRole + 1
_IS_ROLLBACK_BAR_ROLE = QtCore.Qt.ItemDataRole.UserRole + 2

# Alpha values for the dependency-highlight background, applied to the
# palette's own Highlight color rather than a hardcoded RGB - stays
# theme-correct (light or dark) the same way the suppressed-row styling
# does. Parents (what the hovered/selected feature depends on, via
# OutList) get a lighter tint; children (what depends on it, via InList)
# a stronger one - a "simple enough" visual distinction per the issue,
# without inventing a second hue that might clash in some themes.
_HIGHLIGHT_PARENT_ALPHA = 55
_HIGHLIGHT_CHILD_ALPHA = 110


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


def _make_item(
    row: FeatureRow, registry: dict[str, QtWidgets.QTreeWidgetItem] | None = None
) -> QtWidgets.QTreeWidgetItem:
    """Build a QTreeWidgetItem for a row, recursively nesting its children.

    If registry is given, every item built (including group folders) is
    recorded under row.name - used by the dependency-highlight feature to
    look up an arbitrary object's item in O(1) instead of re-walking the
    tree for every parent/child on every hover.
    """
    if row.is_group:
        item = QtWidgets.QTreeWidgetItem([row.label, row.type_id])
        item.setToolTip(0, row.label)
        item.setData(0, _NAME_ROLE, row.name)
        item.setData(0, _IS_GROUP_ROLE, True)
        item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsEditable)
        item.setIcon(
            0, QtWidgets.QApplication.style().standardIcon(
                QtWidgets.QStyle.StandardPixmap.SP_DirIcon
            ),
        )
        if registry is not None:
            registry[row.name] = item
        for child in row.children:
            item.addChild(_make_item(child, registry))
        return item

    item = QtWidgets.QTreeWidgetItem([row.label, row.type_id])
    item.setToolTip(0, row.label)
    item.setToolTip(1, row.type_id)
    item.setData(0, _NAME_ROLE, row.name)
    if registry is not None:
        registry[row.name] = item
    # Qt.ItemIsEditable is per-item, not per-column - it also technically
    # makes the Type column editable. _on_item_changed() below only ever
    # acts on column 0, so editing column 1 is a harmless no-op that the
    # next refresh() silently overwrites back to the real type.
    item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsEditable)

    if row.beyond_tip:
        # Distinct from Suppressed on purpose (CDC 3.1 calls for a
        # visually different "beyond the rollback bar" state, not a
        # reuse of Suppressed's styling) - strikeout instead of italic,
        # and the palette's PlaceholderText role instead of Disabled/
        # Text, so the two are never confused even though both are some
        # shade of gray. Still theme-derived, never a hardcoded color.
        # A feature beyond the bar hasn't been part of the last
        # recompute, so its Suppressed/Error status isn't the relevant
        # thing to show right now - this takes priority over that below.
        placeholder_text = QtWidgets.QApplication.palette().color(
            QtGui.QPalette.ColorGroup.Active, QtGui.QPalette.ColorRole.PlaceholderText
        )
        for column in (0, 1):
            font = item.font(column)
            font.setStrikeOut(True)
            item.setFont(column, font)
            item.setForeground(column, placeholder_text)
    elif row.state == SUPPRESSED:
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
        item.addChild(_make_item(child, registry))
    return item


def _make_rollback_bar_item() -> QtWidgets.QTreeWidgetItem:
    """A non-selectable row rendered as an actual horizontal line -
    the rollback bar itself, distinct from styling applied to a feature
    row (see FeatureRow.beyond_tip in _make_item above)."""
    item = QtWidgets.QTreeWidgetItem()
    item.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)
    item.setData(0, _IS_ROLLBACK_BAR_ROLE, True)
    return item


def _make_rollback_bar_widget() -> QtWidgets.QWidget:
    frame = QtWidgets.QFrame()
    frame.setFrameShape(QtWidgets.QFrame.Shape.HLine)
    frame.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
    frame.setLineWidth(2)
    return frame


class FeatureTreePanel(QtWidgets.QDockWidget):
    """Dockable view of the active Body's feature chain.

    Read-only display plus a few interactions:
    - double-click a feature to edit it (same as the context menu's Edit)
    - F2, or clicking an already-selected feature, to rename it inline
    - right-click for the full menu: Suppress/Unsuppress, Edit, Delete,
      Delete with Children, Go to Sketch (only if the feature has one),
      Isolate/Restore Visibility
    """

    def __init__(self, parent=None):
        super().__init__("ATPD - Feature Tree", parent)
        self.setObjectName("ATPD_FeatureTreePanel")

        container = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QtWidgets.QToolBar(container)
        header.setObjectName("ATPD_FeatureTreeHeaderToolbar")
        header.setIconSize(QtCore.QSize(16, 16))
        header.setMovable(False)
        header.setFloatable(False)
        layout.addWidget(header)

        self._hover_highlight_action = self._add_persisted_toggle(
            header,
            QtWidgets.QApplication.style().standardIcon(
                QtWidgets.QStyle.StandardPixmap.SP_FileDialogInfoView
            ),
            "Highlight dependencies on hover/selection",
            is_hover_highlight_enabled,
            set_hover_highlight_enabled,
            on_toggled=self._on_hover_highlight_toggled,
        )

        self._tree = QtWidgets.QTreeWidget(container)
        self._tree.setColumnCount(2)
        self._tree.setHeaderLabels(["Feature", "Type"])
        # Explicit, not relying on Qt's default: Ctrl/Shift-click multi-select
        # is required for "Group into Folder".
        self._tree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self._tree.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        # EditKeyPressed = F2. SelectedClicked = clicking an item that is
        # already selected, same convention native file explorers use for
        # rename - deliberately *not* DoubleClicked, which already means
        # Edit here (see _on_item_double_clicked), matching both the
        # native tree and file-explorer conventions: a fast double-click
        # opens/edits, a slow second click on an already-selected item
        # renames.
        self._tree.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.EditKeyPressed
            | QtWidgets.QAbstractItemView.EditTrigger.SelectedClicked
        )
        self._tree.itemChanged.connect(self._on_item_changed)
        # itemEntered only fires with mouse tracking on - it's off by
        # default since most QTreeWidget uses don't need per-item hover.
        self._tree.setMouseTracking(True)
        self._tree.itemEntered.connect(self._on_item_hover)
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)
        # No itemLeft signal in Qt - catch the mouse leaving the viewport
        # entirely (as opposed to moving to a different item, which just
        # fires itemEntered again) via an event filter instead.
        self._tree.viewport().installEventFilter(self)
        layout.addWidget(self._tree)
        self.setWidget(container)

        self._observer = _TreeDocumentObserver(self.refresh)
        Gui.addDocumentObserver(self._observer)

        # Isolate/restore-visibility toggle state - which object (if any)
        # is currently isolated, and the visibility every object in the
        # body had right before that, so a second click can undo it.
        self._isolated_name: str | None = None
        self._isolated_saved_visibility: dict[str, bool] = {}

        # Dependency-highlight state: name -> item for O(1) lookup, the
        # currently-highlighted items (to clear on the next hover/
        # selection change), and which name the *selection* (as opposed
        # to a transient hover) is highlighting, so a hover that ends
        # reverts to showing the selection's highlight rather than
        # clearing it outright.
        self._items_by_name: dict[str, QtWidgets.QTreeWidgetItem] = {}
        self._highlighted_items: list[QtWidgets.QTreeWidgetItem] = []
        self._selected_highlight_name: str | None = None

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
            # Old items are gone (clear() deletes them) - drop every
            # reference to them so nothing stale lingers.
            self._items_by_name = {}
            self._highlighted_items = []
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
                self._tree.addTopLevelItem(_make_item(row, self._items_by_name))
            self._insert_rollback_bar(body)
            self._tree.expandAll()
            self._tree.resizeColumnToContents(0)
            self._tree.resizeColumnToContents(1)
        finally:
            self._tree.blockSignals(False)

    def _insert_rollback_bar(self, body) -> None:
        """Insert the rollback-bar row right after the Tip's top-level item.

        The Tip is always a solid feature, never nestable (see
        is_solid_feature()), but it can be inside one of our own group
        folders - walk up to that folder's own top-level item in that
        case, since the bar itself is always a top-level row.
        """
        tip = body.Tip
        if tip is None:
            return
        tip_item = self._items_by_name.get(tip.Name)
        if tip_item is None:
            return

        top_level_item = tip_item
        while top_level_item.parent() is not None:
            top_level_item = top_level_item.parent()
        index = self._tree.indexOfTopLevelItem(top_level_item)

        bar_item = _make_rollback_bar_item()
        self._tree.insertTopLevelItem(index + 1, bar_item)
        self._tree.setFirstColumnSpanned(index + 1, QtCore.QModelIndex(), True)
        self._tree.setItemWidget(bar_item, 0, _make_rollback_bar_widget())

    def closeEvent(self, event: QtCore.QEvent) -> None:
        Gui.removeDocumentObserver(self._observer)
        super().closeEvent(event)

    def _add_persisted_toggle(
        self,
        toolbar: QtWidgets.QToolBar,
        icon: QtGui.QIcon,
        tooltip: str,
        get_value,
        set_value,
        on_toggled=None,
    ) -> QtGui.QAction:
        """Add a checkable header-toolbar action backed by a persisted
        (non-document) FreeCAD user preference.

        This is the pattern to follow for any future header button that
        needs a remembered on/off state: write get/set functions in
        model.py (see is_hover_highlight_enabled/set_hover_highlight_enabled)
        and call this once with them - loading the saved state, wiring
        persistence, and optionally reacting to the change are all
        handled here instead of being copy-pasted per button.
        """
        action = toolbar.addAction(icon, tooltip)
        action.setCheckable(True)
        action.setChecked(get_value())

        def handle_toggled(checked: bool) -> None:
            set_value(checked)
            if on_toggled is not None:
                on_toggled(checked)

        action.toggled.connect(handle_toggled)
        return action

    def _on_hover_highlight_toggled(self, checked: bool) -> None:
        App.Console.PrintMessage(f"ATPD tree DEBUG: hover highlight enabled -> {checked}\n")
        # _apply_highlight() itself gates on the action's checked state
        # and always clears first, so this one call correctly handles
        # both directions: turning it off wipes any current highlight,
        # turning it back on immediately re-shows the selection's.
        self._apply_highlight(self._selected_highlight_name if checked else None)

    def eventFilter(self, watched, event: QtCore.QEvent) -> bool:
        if watched is self._tree.viewport() and event.type() == QtCore.QEvent.Type.Leave:
            # Mouse left the tree entirely - revert to the selection's
            # highlight (if any) rather than leaving the last-hovered
            # item's highlight stuck on.
            self._apply_highlight(self._selected_highlight_name)
        return super().eventFilter(watched, event)

    def _on_item_hover(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        if item.data(0, _IS_GROUP_ROLE) or item.data(0, _IS_ROLLBACK_BAR_ROLE):
            return
        self._apply_highlight(item.data(0, _NAME_ROLE))

    def _on_selection_changed(self) -> None:
        selected = self._tree.selectedItems()
        if len(selected) == 1 and not selected[0].data(0, _IS_GROUP_ROLE):
            self._selected_highlight_name = selected[0].data(0, _NAME_ROLE)
        else:
            self._selected_highlight_name = None
        self._apply_highlight(self._selected_highlight_name)

    def _highlight_color(self, alpha: int) -> QtGui.QColor:
        """A tint of the palette's own Highlight color, not a hardcoded
        RGB - stays correct in both light and dark themes."""
        color = QtGui.QColor(
            QtWidgets.QApplication.palette().color(QtGui.QPalette.ColorRole.Highlight)
        )
        color.setAlpha(alpha)
        return color

    def _apply_highlight(self, name: str | None) -> None:
        """Background-highlight name's parents (OutList) and children
        (InList), on top of whatever suppressed/error foreground styling
        is already on those rows - setBackground()/setForeground() are
        independent, so neither overwrites the other.

        Single gate point for the header toolbar's on/off toggle: every
        caller (hover, selection change, hover-leave reverting to the
        selection) goes through here, so checking
        self._hover_highlight_action once is enough - no need to guard
        each call site separately.
        """
        self._clear_highlight()
        if not name or not self._hover_highlight_action.isChecked():
            return
        doc = App.ActiveDocument
        if doc is None:
            return
        obj = doc.getObject(name)
        if obj is None:
            return

        parent_color = self._highlight_color(_HIGHLIGHT_PARENT_ALPHA)
        for parent in find_dependencies(obj):
            self._set_item_background(parent.Name, parent_color)

        child_color = self._highlight_color(_HIGHLIGHT_CHILD_ALPHA)
        for child in find_dependents(obj):
            self._set_item_background(child.Name, child_color)

    def _set_item_background(self, name: str, color: QtGui.QColor) -> None:
        item = self._items_by_name.get(name)
        if item is None:
            return
        for column in (0, 1):
            item.setBackground(column, color)
        self._highlighted_items.append(item)

    def _clear_highlight(self) -> None:
        empty_brush = QtGui.QBrush()
        for item in self._highlighted_items:
            for column in (0, 1):
                item.setBackground(column, empty_brush)
        self._highlighted_items = []

    def _resolve_object(self, item: QtWidgets.QTreeWidgetItem):
        """The live FreeCAD object an item represents, or None."""
        name = item.data(0, _NAME_ROLE)
        doc = App.ActiveDocument
        if doc is None or not name:
            return None
        return doc.getObject(name)

    def _on_item_double_clicked(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        """Fast double-click means Edit - Suppress/Unsuppress is context-menu only.

        A group folder has no native "edit" concept and no real object to
        resolve; Qt's own default expand/collapse-on-double-click already
        applies to it, so there's nothing extra to do here.
        """
        if item.data(0, _IS_GROUP_ROLE) or item.data(0, _IS_ROLLBACK_BAR_ROLE):
            return
        obj = self._resolve_object(item)
        if obj is None:
            App.Console.PrintMessage("ATPD tree DEBUG: double-click on an unresolved item\n")
            return
        self._edit_object(obj)

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
        if item is None or item.data(0, _IS_ROLLBACK_BAR_ROLE):
            return

        selected = self._tree.selectedItems()
        if len(selected) > 1:
            self._show_multi_select_menu(pos, selected)
            return

        if item.data(0, _IS_GROUP_ROLE):
            self._show_group_menu(pos, item)
            return

        self._show_feature_menu(pos, item)

    def _show_multi_select_menu(
        self, pos: QtCore.QPoint, selected_items: list[QtWidgets.QTreeWidgetItem]
    ) -> None:
        """Menu for a multi-selection: only "Group into Folder" for now.

        Group folders can't themselves be grouped (no nested folders in
        this version) - any selected folder is silently skipped.
        """
        member_names = [
            obj.Name
            for it in selected_items
            if not it.data(0, _IS_GROUP_ROLE) and (obj := self._resolve_object(it)) is not None
        ]
        if not member_names:
            return

        menu = QtWidgets.QMenu(self._tree)
        group_action = menu.addAction("Group into Folder…")
        chosen = menu.exec(self._tree.viewport().mapToGlobal(pos))
        if chosen is group_action:
            self._group_into_folder(member_names)

    def _show_group_menu(self, pos: QtCore.QPoint, item: QtWidgets.QTreeWidgetItem) -> None:
        """Menu for a group folder. Renaming reuses F2/click-to-edit, same
        as features - no separate "Rename" entry needed here."""
        group_id = item.data(0, _NAME_ROLE)
        menu = QtWidgets.QMenu(self._tree)
        dissolve_action = menu.addAction("Dissolve Folder")
        chosen = menu.exec(self._tree.viewport().mapToGlobal(pos))
        if chosen is dissolve_action:
            self._dissolve_group(group_id)

    def _show_feature_menu(self, pos: QtCore.QPoint, item: QtWidgets.QTreeWidgetItem) -> None:
        obj = self._resolve_object(item)
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

        body = _active_body()

        move_bar_action = None
        if (
            body is not None
            and is_solid_feature(obj)
            and (body.Tip is None or obj.Name != body.Tip.Name)
        ):
            menu.addSeparator()
            move_bar_action = menu.addAction("Move Rollback Bar Here")

        groups, membership = load_groups(body) if body is not None else ({}, {})
        move_actions: dict[QtGui.QAction, str | None] = {}
        if groups:
            menu.addSeparator()
            move_menu = menu.addMenu("Move to")
            current_group = membership.get(obj.Name)
            for group_id, group_name in groups.items():
                if group_id == current_group:
                    continue
                move_actions[move_menu.addAction(group_name)] = group_id
            if current_group is not None:
                move_actions[move_menu.addAction("Top Level")] = None

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
        elif chosen is move_bar_action:
            self._move_rollback_bar(obj)
        elif chosen in move_actions:
            self._move_feature(obj, move_actions[chosen])

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
        if item.data(0, _IS_GROUP_ROLE):
            self._on_group_renamed(item)
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

    def _move_rollback_bar(self, obj) -> None:
        """Move the Body's Tip - the rollback bar's position - to obj.

        Moving alone never breaks anything (verified in the M3 spike -
        docs/spike_rollback_findings.md): the Topological Naming Problem
        risk only appears if something is later *inserted* at the new
        position, which is warned about separately in
        _insert_feature_with_rollback_warning() below - not here.
        """
        body = _active_body()
        if body is None:
            return
        try:
            move_rollback_bar(body.Document, body, obj)
        except Exception as exc:
            App.Console.PrintError(f"ATPD tree: failed to move rollback bar to {obj.Name}: {exc}\n")
            QtWidgets.QMessageBox.critical(
                self, "Error", f'Failed to move rollback bar to "{obj.Label}":\n{exc}'
            )
            return
        App.Console.PrintMessage(f"ATPD tree DEBUG: rollback bar moved to {obj.Name}\n")
        self.refresh()

    def _insert_feature_with_rollback_warning(self, new_feature, sketch=None) -> bool:
        """Insert new_feature (and its sketch, if any) at the current
        rollback bar, warning first if a Dress-Up feature immediately
        downstream of the Tip is at risk of FreeCAD's Topological Naming
        Problem (docs/spike_rollback_findings.md).

        Not wired to a context-menu entry yet - actually creating a new
        feature (a sketch + Pad/Pocket/etc.) is out of scope for the
        rollback bar itself (M4's unified feature commands are the
        intended caller once they exist). This is the reusable building
        block for that, exercised directly by this PR's tests in the
        meantime. Returns whether the insertion actually happened
        (False if cancelled, or the body couldn't be resolved).
        """
        body = _active_body()
        if body is None:
            return False

        at_risk = find_downstream_dressup_risk(body)
        if at_risk:
            names = ", ".join(feature.Label for feature in at_risk)
            reply = QtWidgets.QMessageBox.warning(
                self,
                "Topological naming risk",
                f"Inserting a feature here may invalidate the following "
                f"Dress-Up feature(s), which reference specific edges/faces "
                f"of the shape at this point: {names}.\n\n"
                f"This is a known FreeCAD kernel limitation (the "
                f"Topological Naming Problem), not something ATPD can "
                f"prevent - see docs/spike_rollback_findings.md.\n\nContinue?",
                QtWidgets.QMessageBox.StandardButton.Ok
                | QtWidgets.QMessageBox.StandardButton.Cancel,
            )
            if reply != QtWidgets.QMessageBox.StandardButton.Ok:
                App.Console.PrintMessage("ATPD tree DEBUG: insert at rollback bar cancelled\n")
                return False

        try:
            insert_feature_at_rollback_bar(body.Document, body, new_feature, sketch)
        except Exception as exc:
            App.Console.PrintError(
                f"ATPD tree: failed to insert {new_feature.Name} at rollback bar: {exc}\n"
            )
            QtWidgets.QMessageBox.critical(
                self, "Error", f'Failed to insert "{new_feature.Label}":\n{exc}'
            )
            return False

        App.Console.PrintMessage(f"ATPD tree DEBUG: inserted {new_feature.Name} at rollback bar\n")
        self.refresh()
        return True

    def _group_into_folder(self, member_names: list[str]) -> None:
        body = _active_body()
        if body is None:
            return
        name, ok = QtWidgets.QInputDialog.getText(self, "Group into Folder", "Folder name:")
        if not ok or not name.strip():
            App.Console.PrintMessage("ATPD tree DEBUG: group-into-folder cancelled or blank\n")
            return
        try:
            group_id = create_group(body.Document, body, name.strip(), member_names)
        except Exception as exc:
            App.Console.PrintError(f"ATPD tree: failed to create group: {exc}\n")
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to create folder:\n{exc}")
            return
        App.Console.PrintMessage(
            f"ATPD tree DEBUG: created group {group_id!r} with members {member_names}\n"
        )
        self.refresh()

    def _dissolve_group(self, group_id: str) -> None:
        body = _active_body()
        if body is None:
            return
        try:
            dissolve_group(body.Document, body, group_id)
        except Exception as exc:
            App.Console.PrintError(f"ATPD tree: failed to dissolve group {group_id}: {exc}\n")
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to dissolve folder:\n{exc}")
            return
        App.Console.PrintMessage(f"ATPD tree DEBUG: dissolved group {group_id}\n")
        self.refresh()

    def _move_feature(self, obj, group_id: str | None) -> None:
        body = _active_body()
        if body is None:
            return
        try:
            move_to_group(body.Document, body, [obj.Name], group_id)
        except Exception as exc:
            App.Console.PrintError(f"ATPD tree: failed to move {obj.Name}: {exc}\n")
            QtWidgets.QMessageBox.critical(self, "Error", f'Failed to move "{obj.Label}":\n{exc}')
            return
        App.Console.PrintMessage(f"ATPD tree DEBUG: moved {obj.Name} to group {group_id!r}\n")
        self.refresh()

    def _on_group_renamed(self, item: QtWidgets.QTreeWidgetItem) -> None:
        """Apply an inline-edited folder name, or restore it if rejected."""
        group_id = item.data(0, _NAME_ROLE)
        body = _active_body()
        if body is None:
            return

        new_text = item.text(0)
        try:
            applied = rename_group(body.Document, body, group_id, new_text)
        except Exception as exc:
            App.Console.PrintError(f"ATPD tree: failed to rename group {group_id}: {exc}\n")
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to rename folder:\n{exc}")
            applied = False

        groups, _ = load_groups(body)
        current_name = groups.get(group_id, item.text(0))
        if applied:
            App.Console.PrintMessage(
                f"ATPD tree DEBUG: group {group_id}.name -> {current_name!r}\n"
            )
            self.refresh()
        else:
            App.Console.PrintMessage(
                f"ATPD tree DEBUG: rename of group {group_id} rejected, "
                f"restoring {current_name!r}\n"
            )
            item.setText(0, current_name)
