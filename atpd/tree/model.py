"""Pure-Python data layer for the ATPD feature tree.

Deliberately has no Qt/Gui dependency, so it can be exercised headlessly
(FreeCADCmd, no QApplication) - see tests/run_tests.py. The Qt-facing
panel (panel.py) is a thin consumer of collect_body_features().
"""

from dataclasses import dataclass, field

ACTIVE = "active"
SUPPRESSED = "suppressed"
ERROR = "error"

_LINK_PROPERTY_TYPES = frozenset(
    {
        "App::PropertyLink",
        "App::PropertyLinkChild",
        "App::PropertyLinkSub",
        "App::PropertyLinkSubChild",
        "App::PropertyLinkList",
        "App::PropertyLinkListChild",
        "App::PropertyLinkSubList",
        "App::PropertyLinkSubListChild",
    }
)

# Properties that describe an object's own historical/positional anchor
# rather than a feature "consuming" another object to build its shape.
# Excluded when looking for a "P uses N" edge, otherwise a Pad's
# BaseFeature (the previous feature in the chain) or a Sketch's
# AttachmentSupport/ExternalGeometry (what it's drawn on/against) would
# get treated as a "this feature uses that object" relationship, which
# would misplace or reverse the nesting.
_NON_CONSUMER_LINK_PROPERTIES = frozenset(
    {"BaseFeature", "AttachmentSupport", "ExternalGeometry"}
)


@dataclass(frozen=True)
class FeatureRow:
    """One row of the read-only feature tree, with its nested children."""

    name: str
    label: str
    type_id: str
    state: str
    children: list["FeatureRow"] = field(default_factory=list)


def simplify_type_id(type_id: str) -> str:
    """Turn "PartDesign::Pad" into "Pad"."""
    return type_id.rsplit("::", 1)[-1]


def is_nestable(obj) -> bool:
    """Only sketches consumed by a feature nest; everything else stays top-level.

    Datums are deliberately excluded, even though a DatumPlane commonly
    references another DatumPlane (or a feature's face) via
    AttachmentSupport for its own positioning: that's a geometric anchor,
    not an ownership relationship, and the native Model tree keeps every
    datum a direct child of the Body regardless of what it's attached to.
    """
    return obj.TypeId == "Sketcher::SketchObject"


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


def _linked_object_names(obj, property_name: str) -> list[str]:
    """Names of every DocumentObject referenced by a Link*-type property.

    Handles the shapes PropertyLink/PropertyLinkSub/PropertyLinkList/
    PropertyLinkSubList actually return: a bare object, a (object, subs)
    tuple, or a list of either.
    """
    value = getattr(obj, property_name)
    if value is None:
        return []
    if hasattr(value, "Name"):
        return [value.Name]
    if isinstance(value, tuple) and len(value) == 2 and hasattr(value[0], "Name"):
        return [value[0].Name]
    if isinstance(value, (list, tuple)):
        names = []
        for item in value:
            if hasattr(item, "Name"):
                names.append(item.Name)
            elif isinstance(item, tuple) and len(item) == 2 and hasattr(item[0], "Name"):
                names.append(item[0].Name)
        return names
    return []


def _consumer_links(obj) -> list[str]:
    """Names of objects this object references via a "uses" Link property."""
    names = []
    for prop in obj.PropertiesList:
        if prop in _NON_CONSUMER_LINK_PROPERTIES:
            continue
        try:
            type_id = obj.getTypeIdOfProperty(prop)
        except Exception:
            continue
        if type_id not in _LINK_PROPERTY_TYPES:
            continue
        names.extend(_linked_object_names(obj, prop))
    return names


def _resolve_parents(body_objects) -> dict[str, str]:
    """Map each nestable (sketch) object's Name to its consumer feature's Name.

    A sketch nests under whatever other object in the body references it
    via a normal "uses" Link property - e.g. Pad.Profile -> Sketch is how
    the native tree nests a feature's own sketch under that feature. A
    sketch with no such consumer (unused, or only referenced via
    AttachmentSupport/ExternalGeometry) stays top-level.
    """
    by_name = {obj.Name: obj for obj in body_objects}
    parent_of: dict[str, str] = {}

    for obj in body_objects:
        for target_name in _consumer_links(obj):
            if target_name == obj.Name or target_name not in by_name:
                continue
            target = by_name[target_name]
            if is_nestable(target) and target_name not in parent_of:
                parent_of[target_name] = obj.Name

    return parent_of


def count_rows(rows: list[FeatureRow]) -> int:
    """Total number of rows in a tree, including nested children."""
    return sum(1 + count_rows(row.children) for row in rows)


def collect_body_features(body) -> list[FeatureRow]:
    """Build the hierarchical feature tree for a PartDesign Body.

    Top-level features (Pad, Pocket, Fillet, ...) keep the Body.Group /
    Tip order, as do datums - only sketches nest, and only under whatever
    consumes them as a profile/section/spine (see _resolve_parents),
    never guessed from names, only from real Link/LinkSub properties.
    """
    objects = list(body.Group)
    parent_of = _resolve_parents(objects)

    rows_by_name = {
        obj.Name: FeatureRow(
            name=obj.Name,
            label=obj.Label,
            type_id=simplify_type_id(obj.TypeId),
            state=feature_state(obj),
        )
        for obj in objects
    }

    top_level: list[FeatureRow] = []
    for obj in objects:
        row = rows_by_name[obj.Name]
        parent_name = parent_of.get(obj.Name)
        if parent_name is not None and parent_name in rows_by_name:
            rows_by_name[parent_name].children.append(row)
        else:
            top_level.append(row)

    return top_level
