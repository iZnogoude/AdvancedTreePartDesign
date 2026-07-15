"""Throwaway spike script - NOT production code, NOT covered by CI/tests.

Answers the 4 feasibility questions from issue #35 by actually doing
each operation on a temp copy of tests/files/02_complex.FCStd and
inspecting the result. See docs/spike_rollback_findings.md for the
findings this script produced. Kept for reproducibility, not meant to
be maintained or reused as-is by real ATPD code.

Run with:
    flatpak run --command=FreeCADCmd org.freecad.FreeCAD docs/spike_rollback_experiment.py
"""

import os
import shutil
import tempfile
import traceback

import FreeCAD as App
import Part


def dump_state(body, label):
    print(f"--- {label} ---", flush=True)
    print(f"Tip = {body.Tip.Name if body.Tip else None}", flush=True)
    for obj in body.Group:
        try:
            valid = obj.isValid()
        except Exception as exc:
            valid = f"ERROR: {exc}"
        try:
            has_shape = hasattr(obj, "Shape") and not obj.Shape.isNull()
        except Exception as exc:
            has_shape = f"ERROR: {exc}"
        base = getattr(obj, "BaseFeature", None)
        print(
            f"  {obj.Name:20s} TypeId={obj.TypeId:30s} State={obj.State} "
            f"Valid={valid} HasShape={has_shape} "
            f"BaseFeature={base.Name if base else None}",
            flush=True,
        )


def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(repo_root, "tests", "files", "02_complex.FCStd")

    tmp_dir = tempfile.mkdtemp()
    copy_path = os.path.join(tmp_dir, "copy.FCStd")
    shutil.copyfile(src, copy_path)

    doc = App.openDocument(copy_path)
    body = next(obj for obj in doc.Objects if obj.TypeId == "PartDesign::Body")

    dump_state(body, "INITIAL STATE (Tip=Fillet, full chain computed)")
    original_tip = body.Tip
    print(f"\noriginal_tip = {original_tip.Name}", flush=True)

    # Q1/Q2: move Tip backward to an intermediate feature
    print("\n=== TEST: moving Tip backward to 'Pocket' (intermediate feature) ===", flush=True)
    pocket = doc.getObject("Pocket")
    try:
        body.Tip = pocket
        doc.recompute()
        print("Tip move + recompute: OK, no exception", flush=True)
    except Exception:
        traceback.print_exc()
    dump_state(body, "AFTER Tip = Pocket, recomputed")

    # Q1: insert a NEW feature at the rollback point (right after Pocket)
    print("\n=== TEST: insertObject - insert a NEW Pad right after Pocket ===", flush=True)
    try:
        sketch = doc.addObject("Sketcher::SketchObject", "SpikeSketch")
        sketch.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 5), False)
        pad = doc.addObject("PartDesign::Pad", "SpikePad")
        pad.Profile = sketch
        pad.Length = 5.0

        body.insertObject(sketch, pocket, True)
        body.insertObject(pad, pocket, True)
        print("insertObject calls: OK, no exception", flush=True)
    except Exception:
        traceback.print_exc()

    print(f"\nGroup order after insert: {[o.Name for o in body.Group]}", flush=True)

    try:
        body.Tip = pad
        doc.recompute()
        print("Tip = pad + recompute: OK, no exception", flush=True)
    except Exception:
        traceback.print_exc()
    dump_state(body, "AFTER inserting SpikePad after Pocket, Tip=SpikePad")

    # Q3: move Tip forward again to the (now-shifted) original last feature
    print("\n=== TEST: moving Tip forward again to the original last feature ===", flush=True)
    try:
        body.Tip = original_tip
        doc.recompute()
        print("Tip = original_tip + recompute: OK, no exception", flush=True)
    except Exception:
        traceback.print_exc()
    dump_state(body, "FINAL STATE (Tip back at original last feature)")

    print(f"\nFinal Group order: {[o.Name for o in body.Group]}", flush=True)
    print(f"Final Group size: {len(body.Group)} (should be original 15 + 2 new = 17)", flush=True)

    App.closeDocument(doc.Name)
    shutil.rmtree(tmp_dir)
    print("\nDONE", flush=True)


main()
