"""Pure-Python data layer for the ATPD feature tree.

Deliberately has no Qt/Gui dependency, so it can be exercised headlessly
(FreeCADCmd, no QApplication) - see tests/run_tests.py. The Qt-facing
panel (panel.py) is a thin consumer of collect_body_features().
"""

from dataclasses import dataclass

ACTIVE = "active"
SUPPRESSED = "suppressed"
ERROR = "error"


@dataclass(frozen=True)
class FeatureRow:
    """One row of the read-only feature tree."""

    name: str
    label: str
    type_id: str
    state: str


def simplify_type_id(type_id: str) -> str:
    """Turn "PartDesign::Pad" into "Pad"."""
    return type_id.rsplit("::", 1)[-1]


def feature_state(obj) -> str:
    """Classify a document object as active, suppressed, or in error.

    Suppressed takes priority: a suppressed PartDesign feature is skipped
    during recompute and isn't meaningfully "in error" even if isValid()
    happens to report False for it.
    """
    if getattr(obj, "Suppressed", False):
        return SUPPRESSED
    if not obj.isValid():
        return ERROR
    return ACTIVE


def collect_body_features(body) -> list[FeatureRow]:
    """List every object in a PartDesign Body's Group, in Tip order.

    Body.Group already reflects the order features were added to the
    body, which is what the native Model tree shows (last feature at the
    bottom, matching the Tip).
    """
    return [
        FeatureRow(
            name=obj.Name,
            label=obj.Label,
            type_id=simplify_type_id(obj.TypeId),
            state=feature_state(obj),
        )
        for obj in body.Group
    ]
