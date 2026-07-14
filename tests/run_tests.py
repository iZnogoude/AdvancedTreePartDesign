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
