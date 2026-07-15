"""Minimal headless test runner for ATPD, executed via FreeCADCmd.

FreeCADCmd's bundled Python does not ship pytest, so this collects and
runs test_* functions by hand: no fixtures, no assertion rewriting,
just a flat list of callables and a pass/fail count. Swap this out for
pytest if it ever becomes available in the target FreeCAD environment.

Usage:
    flatpak run --command=FreeCADCmd org.freecad.FreeCAD tests/run_tests.py
"""

import os
import shutil
import sys
import tempfile

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_REFERENCE_FILES_DIR = os.path.join(_REPO_ROOT, "tests", "files")

# Only matters for the one test that builds real Qt widgets
# (test_dependency_highlight) - setting this here, before any
# QApplication is constructed, lets it run without a display server
# regardless of how this file itself gets invoked.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import FreeCAD as App  # noqa: E402


def test_atpd_module_imports():
    """The atpd package and its subpackages must import without error."""
    import atpd.core  # noqa: F401
    import atpd.features  # noqa: F401
    import atpd.tree  # noqa: F401


def test_document_loads_without_error():
    """Each of the 5 reference .FCStd files must open and close without error."""
    fcstd_files = sorted(
        name for name in os.listdir(_REFERENCE_FILES_DIR) if name.endswith(".FCStd")
    )
    assert len(fcstd_files) == 5, (
        f"expected 5 reference .FCStd files in {_REFERENCE_FILES_DIR}, "
        f"found {len(fcstd_files)}: {fcstd_files}"
    )
    for filename in fcstd_files:
        path = os.path.join(_REFERENCE_FILES_DIR, filename)
        doc = App.openDocument(path)
        assert doc is not None, f"failed to open {filename}"
        App.closeDocument(doc.Name)


def test_tree_model_matches_body_group():
    """collect_body_features() must account for every object in each Body.

    The model is hierarchical (sketches/datums nest under their consumer
    feature), so the row count that must match Body.Group is the total
    across all nesting levels, not just the top-level rows.
    """
    from atpd.tree.model import collect_body_features, count_rows

    fcstd_files = sorted(
        name for name in os.listdir(_REFERENCE_FILES_DIR) if name.endswith(".FCStd")
    )
    for filename in fcstd_files:
        path = os.path.join(_REFERENCE_FILES_DIR, filename)
        doc = App.openDocument(path)
        bodies = [obj for obj in doc.Objects if obj.TypeId == "PartDesign::Body"]
        assert bodies, f"no PartDesign Body found in {filename}"
        for body in bodies:
            total = count_rows(collect_body_features(body))
            assert total == len(body.Group), (
                f"{filename}: tree model has {total} total rows, "
                f"Body.Group has {len(body.Group)}"
            )
        App.closeDocument(doc.Name)


def test_tree_hierarchy_cross_deps_and_sweep_loft():
    """Only sketches consumed by a feature nest - datums never do.

    03_cross_deps.FCStd has sketches attached to faces of other pads
    (must nest under the feature that consumes them as a Profile, not
    under the pad they're attached to). 04_sweep_loft.FCStd has a datum
    plane referencing another datum plane via AttachmentSupport purely
    for positioning - both must stay direct, top-level children of the
    Body, not nested under one another. Verified against the exact
    Link/LinkSub properties (checked directly against the .FCStd files,
    not guessed from names).
    """
    from atpd.tree.model import collect_body_features

    def build_parent_map(rows, parent_name=None, mapping=None):
        if mapping is None:
            mapping = {}
        for row in rows:
            if parent_name is not None:
                mapping[row.name] = parent_name
            build_parent_map(row.children, row.name, mapping)
        return mapping

    expectations = {
        "03_cross_deps.FCStd": {
            "top_level": {"Pad", "Pad001", "Pad002", "Pad003", "Pad004", "Pad005", "Pocket"},
            "parents": {
                "Sketch": "Pad",
                "Sketch001": "Pad001",
                "Sketch002": "Pad003",
                "Sketch003": "Pad004",
                "Sketch004": "Pad005",
                "Sketch005": "Pocket",
            },
        },
        "04_sweep_loft.FCStd": {
            "top_level": {"AdditivePipe", "AdditiveLoft", "DatumPlane", "DatumPlane001"},
            "parents": {
                "Sketch": "AdditivePipe",
                "Sketch001": "AdditivePipe",
                "Sketch002": "AdditiveLoft",
                "Sketch003": "AdditiveLoft",
                "Sketch004": "AdditiveLoft",
            },
        },
    }

    for filename, expected in expectations.items():
        path = os.path.join(_REFERENCE_FILES_DIR, filename)
        doc = App.openDocument(path)
        body = next(obj for obj in doc.Objects if obj.TypeId == "PartDesign::Body")
        rows = collect_body_features(body)

        top_level_names = {row.name for row in rows}
        assert top_level_names == expected["top_level"], (
            f"{filename}: top-level names {top_level_names} != {expected['top_level']}"
        )

        parent_map = build_parent_map(rows)
        for child_name, expected_parent in expected["parents"].items():
            actual_parent = parent_map.get(child_name)
            assert actual_parent == expected_parent, (
                f"{filename}: parent of {child_name} is {actual_parent!r}, "
                f"expected {expected_parent!r}"
            )

        App.closeDocument(doc.Name)


def test_suppress_state_reflected_in_model():
    """Suppressing a feature must flip its FeatureRow.state to "suppressed".

    Mutates a temp-directory copy of 04_sweep_loft.FCStd, never the
    reference file itself - the reference file's mtime is asserted
    unchanged at the end as a hard guarantee, on top of Suppressed being
    restored to False before the copy is closed.
    """
    from atpd.tree.model import SUPPRESSED, collect_body_features

    src = os.path.join(_REFERENCE_FILES_DIR, "04_sweep_loft.FCStd")
    mtime_before = os.path.getmtime(src)

    with tempfile.TemporaryDirectory() as tmp_dir:
        copy_path = os.path.join(tmp_dir, "04_sweep_loft_copy.FCStd")
        shutil.copyfile(src, copy_path)

        doc = App.openDocument(copy_path)
        try:
            body = next(obj for obj in doc.Objects if obj.TypeId == "PartDesign::Body")
            target = doc.getObject("AdditivePipe")
            assert target is not None, "AdditivePipe not found in the reference copy"

            rows_before = {row.name: row for row in collect_body_features(body)}
            assert rows_before["AdditivePipe"].state != SUPPRESSED, (
                "AdditivePipe should not start suppressed"
            )

            target.Suppressed = True
            doc.recompute()

            rows_after = {row.name: row for row in collect_body_features(body)}
            assert rows_after["AdditivePipe"].state == SUPPRESSED, (
                f"expected suppressed, got {rows_after['AdditivePipe'].state!r}"
            )

            target.Suppressed = False
            doc.recompute()
        finally:
            App.closeDocument(doc.Name)

    assert os.path.getmtime(src) == mtime_before, "reference file must never be modified"


def test_suppress_dependents_and_transaction():
    """find_dependents() must surface real dependents, and toggle_suppressed()
    must flip Suppressed inside a transaction and be reversible.

    Uses 03_cross_deps.FCStd, whose Pad001 has a real downstream
    dependent (Pad002 references Pad001's edges directly, not through a
    sketch) - exactly the interactive-suppress warning scenario. Mutates
    a temp-directory copy, never the reference file itself; the
    reference file's mtime is asserted unchanged at the end.
    """
    from atpd.tree.model import find_dependents, toggle_suppressed

    src = os.path.join(_REFERENCE_FILES_DIR, "03_cross_deps.FCStd")
    mtime_before = os.path.getmtime(src)

    with tempfile.TemporaryDirectory() as tmp_dir:
        copy_path = os.path.join(tmp_dir, "03_cross_deps_copy.FCStd")
        shutil.copyfile(src, copy_path)

        doc = App.openDocument(copy_path)
        try:
            target = doc.getObject("Pad001")
            assert target is not None, "Pad001 not found in the reference copy"

            dependent_names = {dep.Name for dep in find_dependents(target)}
            assert "Pad002" in dependent_names, (
                f"expected Pad002 among Pad001's dependents, got {dependent_names}"
            )

            assert target.Suppressed is False

            new_value = toggle_suppressed(doc, target)
            assert new_value is True
            assert target.Suppressed is True

            restored_value = toggle_suppressed(doc, target)
            assert restored_value is False
            assert target.Suppressed is False
        finally:
            App.closeDocument(doc.Name)

    assert os.path.getmtime(src) == mtime_before, "reference file must never be modified"


def test_rename_label():
    """rename_label() must only ever touch Label, reject blank input, and
    leave FreeCAD's own duplicate-Label auto-disambiguation alone.

    Uses a temp-directory copy of 01_simple.FCStd, never the reference
    file itself; its mtime is asserted unchanged at the end.
    """
    from atpd.tree.model import rename_label

    src = os.path.join(_REFERENCE_FILES_DIR, "01_simple.FCStd")
    mtime_before = os.path.getmtime(src)

    with tempfile.TemporaryDirectory() as tmp_dir:
        copy_path = os.path.join(tmp_dir, "01_simple_copy.FCStd")
        shutil.copyfile(src, copy_path)

        doc = App.openDocument(copy_path)
        try:
            pad = doc.getObject("Pad")
            fillet = doc.getObject("Fillet")
            assert pad is not None and fillet is not None
            original_name = pad.Name

            applied = rename_label(doc, pad, "My Renamed Pad")
            assert applied is True
            assert pad.Label == "My Renamed Pad"
            assert pad.Name == original_name, "Name (internal id) must never change"

            applied_blank = rename_label(doc, pad, "   ")
            assert applied_blank is False, "blank input must be rejected"
            assert pad.Label == "My Renamed Pad", "label must be unchanged after a rejected rename"

            # FreeCAD auto-disambiguates duplicate labels by appending a
            # suffix rather than erroring or silently overwriting - this
            # must keep working, not something rename_label() needs to
            # prevent itself.
            applied_dup = rename_label(doc, pad, fillet.Label)
            assert applied_dup is True
            assert pad.Label != fillet.Label, (
                f"expected FreeCAD to auto-disambiguate, got matching labels {pad.Label!r}"
            )
            assert pad.Label.startswith(fillet.Label)
        finally:
            App.closeDocument(doc.Name)

    assert os.path.getmtime(src) == mtime_before, "reference file must never be modified"


def test_delete_objects():
    """delete_objects() must remove every listed object inside one
    transaction, including the feature-plus-its-children pattern used by
    the "Delete with Children" context-menu action.

    Uses a temp-directory copy of 01_simple.FCStd, never the reference
    file itself; its mtime is asserted unchanged at the end.
    """
    from atpd.tree.model import delete_objects

    src = os.path.join(_REFERENCE_FILES_DIR, "01_simple.FCStd")
    mtime_before = os.path.getmtime(src)

    with tempfile.TemporaryDirectory() as tmp_dir:
        copy_path = os.path.join(tmp_dir, "01_simple_copy.FCStd")
        shutil.copyfile(src, copy_path)

        doc = App.openDocument(copy_path)
        try:
            assert doc.getObject("Fillet001") is not None
            delete_objects(doc, ["Fillet001"])
            assert doc.getObject("Fillet001") is None

            assert doc.getObject("Pad") is not None
            assert doc.getObject("Sketch002") is not None
            delete_objects(doc, ["Sketch002", "Pad"])
            assert doc.getObject("Pad") is None
            assert doc.getObject("Sketch002") is None
        finally:
            App.closeDocument(doc.Name)

    assert os.path.getmtime(src) == mtime_before, "reference file must never be modified"


def test_isolate_object_degrades_gracefully_headlessly():
    """isolate_object()/restore_visibilities() must not crash without a Gui
    session.

    Every object's ViewObject is None under FreeCADCmd (no Gui), so these
    degrade to a no-op rather than raising - isolating is a visual
    convenience with nothing to roll back if it can't act. This can only
    verify the headless-degradation path; the actual visibility toggling
    needs a real Gui session to observe.
    """
    from atpd.tree.model import isolate_object, restore_visibilities

    doc = App.openDocument(os.path.join(_REFERENCE_FILES_DIR, "01_simple.FCStd"))
    try:
        body = next(obj for obj in doc.Objects if obj.TypeId == "PartDesign::Body")
        target = doc.getObject("Pad")
        assert target.ViewObject is None, "expected no ViewObject under FreeCADCmd"

        saved = isolate_object(body.Group, target)
        assert saved == {}, "no ViewObject anywhere means nothing to save"

        restore_visibilities(doc, saved)  # must not raise
    finally:
        App.closeDocument(doc.Name)


def test_group_persistence_across_real_reopen():
    """Groups must survive an actual save-to-disk + close + reopen cycle,
    not just staying correct in memory.

    Uses 02_complex.FCStd (30+ features, the intended real-world case for
    grouping) via a temp-directory copy - the reference file itself is
    only ever read, never opened as the mutation target, and its mtime
    is asserted unchanged at the end.
    """
    from atpd.tree.model import collect_body_features, create_group, load_groups

    src = os.path.join(_REFERENCE_FILES_DIR, "02_complex.FCStd")
    mtime_before = os.path.getmtime(src)

    with tempfile.TemporaryDirectory() as tmp_dir:
        copy_path = os.path.join(tmp_dir, "02_complex_copy.FCStd")
        shutil.copyfile(src, copy_path)

        doc = App.openDocument(copy_path)
        body = next(obj for obj in doc.Objects if obj.TypeId == "PartDesign::Body")

        group_ids = {
            create_group(doc, body, "Base Pads", ["Pad", "Pad001", "Pad002"]),
            create_group(doc, body, "Dress-up", ["Chamfer", "Chamfer001", "Fillet"]),
            create_group(doc, body, "Datums", ["DatumPlane", "DatumPlane001", "DatumLine"]),
        }
        assert len(group_ids) == 3, "expected 3 distinct group ids"

        doc.save()
        App.closeDocument(doc.Name)

        # Real reopen from disk - a fresh Python object, not the same one
        # we just wrote to, so there's no way stale in-memory state could
        # paper over a persistence bug.
        doc2 = App.openDocument(copy_path)
        try:
            body2 = next(obj for obj in doc2.Objects if obj.TypeId == "PartDesign::Body")

            groups, membership = load_groups(body2)
            assert len(groups) == 3, f"expected 3 groups after reopen, got {groups}"
            assert set(groups.values()) == {"Base Pads", "Dress-up", "Datums"}
            assert membership["Pad"] == membership["Pad001"] == membership["Pad002"]
            assert membership["Chamfer"] == membership["Fillet"]

            rows = collect_body_features(body2)
            group_rows = {row.label: row for row in rows if row.is_group}
            assert set(group_rows) == {"Base Pads", "Dress-up", "Datums"}
            assert {child.name for child in group_rows["Base Pads"].children} == {
                "Pad",
                "Pad001",
                "Pad002",
            }
        finally:
            App.closeDocument(doc2.Name)

    assert os.path.getmtime(src) == mtime_before, "reference file must never be modified"


def test_dependency_highlight():
    """Hovering/selecting a feature must highlight its parents (OutList)
    and children (InList) - and only those - via background color.

    Uses 03_cross_deps.FCStd, the file built for this exact
    cross-dependency scenario, and exercises the real
    _apply_highlight()/_make_item() logic under a genuine (offscreen)
    QApplication - a FeatureTreePanel is built via __new__() rather than
    the normal constructor, since __init__ calls
    Gui.addDocumentObserver(), unavailable under FreeCADCmd; only the
    Qt-item/highlighting behavior is under test here, not the observer
    wiring (already covered structurally by every other panel-touching
    test in this file relying on __init__ never being reachable
    headlessly at all).
    """
    from PySide6 import QtCore, QtGui, QtWidgets

    from atpd.tree.model import collect_body_features
    from atpd.tree.panel import (
        _HIGHLIGHT_CHILD_ALPHA,
        _HIGHLIGHT_PARENT_ALPHA,
        FeatureTreePanel,
        _make_item,
    )

    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    doc = App.openDocument(os.path.join(_REFERENCE_FILES_DIR, "03_cross_deps.FCStd"))
    try:
        body = next(obj for obj in doc.Objects if obj.TypeId == "PartDesign::Body")
        rows = collect_body_features(body)

        panel = FeatureTreePanel.__new__(FeatureTreePanel)
        panel._items_by_name = {}
        panel._highlighted_items = []
        panel._selected_highlight_name = None
        for row in rows:
            _make_item(row, panel._items_by_name)

        # _apply_highlight() gates on the header toggle's checked state
        # (see test_header_toggle_persists_and_gates_highlighting for
        # that behavior itself) - stand in a plain checked QAction here
        # since this test is only about the highlight set, not the
        # toggle.
        panel._hover_highlight_action = QtGui.QAction()
        panel._hover_highlight_action.setCheckable(True)
        panel._hover_highlight_action.setChecked(True)

        # Pad001: consumed by Pad002 (child, via InList) via its edges;
        # itself consumes Sketch001 (Profile) and Pad (BaseFeature) as
        # parents, via OutList.
        panel._apply_highlight("Pad001")

        name_role = QtCore.Qt.ItemDataRole.UserRole
        highlighted = {
            item.data(0, name_role): item.background(0).color().alpha()
            for item in panel._highlighted_items
        }
        assert highlighted == {
            "Sketch001": _HIGHLIGHT_PARENT_ALPHA,
            "Pad": _HIGHLIGHT_PARENT_ALPHA,
            "Pad002": _HIGHLIGHT_CHILD_ALPHA,
        }, highlighted

        untouched_names = set(panel._items_by_name) - set(highlighted) - {"Pad001"}
        for name in untouched_names:
            style = panel._items_by_name[name].background(0).style()
            assert style == QtCore.Qt.BrushStyle.NoBrush, f"{name} unexpectedly highlighted"

        panel._clear_highlight()
        assert panel._highlighted_items == []
        for name in highlighted:
            style = panel._items_by_name[name].background(0).style()
            assert style == QtCore.Qt.BrushStyle.NoBrush, f"{name} still highlighted after clear"
    finally:
        App.closeDocument(doc.Name)


def test_header_toggle_persists_and_gates_highlighting():
    """The header toolbar's hover-highlight toggle must:
    - load its initial checked state from the persisted user preference
    - persist every change back to that preference (via ParamGet, a
      *user* setting - never touches the document)
    - immediately gate _apply_highlight(): off clears any current
      highlight and suppresses new ones, back on re-shows the selection

    Restores the preference's original value at the end - this is a
    real FreeCAD user preference (shared with the actual installation,
    not something scoped to a temp file), so leaving it flipped would be
    a real side effect on whoever runs this suite.
    """
    from PySide6 import QtWidgets

    from atpd.tree.model import (
        collect_body_features,
        is_hover_highlight_enabled,
        set_hover_highlight_enabled,
    )
    from atpd.tree.panel import FeatureTreePanel, _make_item

    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    original = is_hover_highlight_enabled()
    try:
        doc = App.openDocument(os.path.join(_REFERENCE_FILES_DIR, "03_cross_deps.FCStd"))
        try:
            body = next(obj for obj in doc.Objects if obj.TypeId == "PartDesign::Body")
            rows = collect_body_features(body)

            panel = FeatureTreePanel.__new__(FeatureTreePanel)
            panel._items_by_name = {}
            panel._highlighted_items = []
            panel._selected_highlight_name = None
            for row in rows:
                _make_item(row, panel._items_by_name)

            toolbar = QtWidgets.QToolBar()
            icon = QtWidgets.QApplication.style().standardIcon(
                QtWidgets.QStyle.StandardPixmap.SP_FileDialogInfoView
            )
            panel._hover_highlight_action = panel._add_persisted_toggle(
                toolbar,
                icon,
                "Highlight dependencies on hover/selection",
                is_hover_highlight_enabled,
                set_hover_highlight_enabled,
                on_toggled=panel._on_hover_highlight_toggled,
            )
            assert panel._hover_highlight_action.isChecked() == original, (
                "initial checked state must match the persisted preference"
            )

            panel._selected_highlight_name = "Pad001"
            panel._apply_highlight("Pad001")
            assert len(panel._highlighted_items) == 3

            panel._hover_highlight_action.setChecked(False)
            assert is_hover_highlight_enabled() is False, "toggle-off must persist"
            assert panel._highlighted_items == [], "toggle-off must clear the current highlight"

            panel._apply_highlight("Pad001")
            assert panel._highlighted_items == [], "must not highlight anything while toggled off"

            panel._hover_highlight_action.setChecked(True)
            assert is_hover_highlight_enabled() is True, "toggle-on must persist"
            assert len(panel._highlighted_items) == 3, (
                "toggle-on must re-show the selection's highlight immediately"
            )
        finally:
            App.closeDocument(doc.Name)
    finally:
        set_hover_highlight_enabled(original)


def _collect_tests():
    module = sys.modules[__name__]
    return [
        getattr(module, name)
        for name in sorted(vars(module))
        if name.startswith("test_") and callable(getattr(module, name))
    ]


def run():
    tests = _collect_tests()
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
        except Exception as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc}", flush=True)
        else:
            passed += 1
            print(f"PASS {test.__name__}", flush=True)

    total = passed + failed
    print(f"\n{passed}/{total} passed, {failed} failed", flush=True)
    return 0 if failed == 0 else 1


# FreeCADCmd runs this file as an imported module (__name__ is the module's
# basename, never "__main__"), so a `if __name__ == "__main__"` guard would
# silently never fire. Run unconditionally instead, and flush stdout before
# sys.exit() since FreeCADCmd tears the interpreter down before the buffer
# would otherwise be flushed.
sys.exit(run())
