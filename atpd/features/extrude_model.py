"""Qt-free orchestration for the unified Extrusion dialog (M4).

Creates real, native ``PartDesign::Pad``/``PartDesign::Pocket`` objects -
never a custom ATPD object type (ENF3). This module has no Gui/Qt imports;
profile *selection* (which needs ``FreeCADGui.Selection``) lives in
``extrude_task.py``.
"""

from atpd.tree.model import insert_feature_at_rollback_bar

ADD_MATERIAL = "add"
REMOVE_MATERIAL = "remove"

_MODES = (ADD_MATERIAL, REMOVE_MATERIAL)


def create_extrusion(
    doc,
    body,
    profile,
    mode,
    length,
    midplane=False,
    body_is_new=False,
    sketch=None,
):
    """Create a Pad (add) or Pocket (remove) feature from ``profile``.

    Args:
        doc: the active ``App.Document``.
        body: the target ``PartDesign::Body``.
        profile: the sketch object, or a ``(face_object, (subelement_name,))``
            tuple, to use as ``.Profile``.
        mode: ``ADD_MATERIAL`` or ``REMOVE_MATERIAL``.
        length: extrusion length (mm).
        midplane: symmetric extrusion about the profile plane.
        body_is_new: True if ``body`` was just created and has no Tip yet -
            skips the rollback-bar insertion machinery, since a body's very
            first feature has no meaningful "insert at Tip" semantics.
        sketch: the sketch object to add to ``body.Group`` alongside the new
            feature, if the profile is a sketch not yet a member of the body.
            None when the profile is a face on an existing solid.

    Returns:
        The newly created ``PartDesign::Pad`` or ``PartDesign::Pocket``.
    """
    if mode not in _MODES:
        raise ValueError(f"Unknown extrusion mode: {mode!r}")
    if body_is_new and mode != ADD_MATERIAL:
        raise ValueError("A new Body's first feature cannot remove material")

    type_id = "PartDesign::Pad" if mode == ADD_MATERIAL else "PartDesign::Pocket"
    name = "Pad" if mode == ADD_MATERIAL else "Pocket"
    feature = doc.addObject(type_id, name)
    feature.Profile = profile
    feature.Length = length
    if midplane:
        feature.SideType = "Symmetric"

    if body_is_new:
        _add_first_feature(doc, body, sketch, feature)
    else:
        insert_feature_at_rollback_bar(doc, body, feature, sketch=sketch)

    return feature


def _add_first_feature(doc, body, sketch, feature):
    """Add ``feature`` (and its ``sketch``, if any) as a new Body's first
    feature - plain append, since there is no Tip/rollback-bar yet."""
    doc.openTransaction(f"Add {feature.Label}")
    try:
        if sketch is not None:
            body.addObject(sketch)
        body.addObject(feature)
        body.Tip = feature
        doc.recompute()
    except Exception:
        doc.abortTransaction()
        raise
    doc.commitTransaction()
