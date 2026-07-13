"""Minimal headless test runner for ATPD, executed via FreeCADCmd.

FreeCADCmd's bundled Python does not ship pytest, so this collects and
runs test_* functions by hand: no fixtures, no assertion rewriting,
just a flat list of callables and a pass/fail count. Swap this out for
pytest if it ever becomes available in the target FreeCAD environment.

Usage:
    flatpak run --command=FreeCADCmd org.freecad.FreeCAD tests/run_tests.py
"""

import os
import sys

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
    """Sketches/datums must nest under their real consumer, not by guesswork.

    03_cross_deps.FCStd has sketches attached to faces of other pads;
    04_sweep_loft.FCStd has a datum plane nested two levels deep under
    another datum plane, itself under a feature via AttachmentSupport.
    Both are verified against the exact Link/LinkSub properties (checked
    directly against the .FCStd files, not guessed from names).
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
            "top_level": {"AdditivePipe", "AdditiveLoft"},
            "parents": {
                "Sketch": "AdditivePipe",
                "Sketch001": "AdditivePipe",
                "Sketch002": "AdditiveLoft",
                "DatumPlane": "AdditivePipe",
                "Sketch003": "AdditiveLoft",
                "DatumPlane001": "DatumPlane",
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
