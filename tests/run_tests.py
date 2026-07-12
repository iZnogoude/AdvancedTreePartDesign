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
