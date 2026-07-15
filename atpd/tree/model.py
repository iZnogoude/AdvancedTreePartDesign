"""Pure-Python data layer for the ATPD feature tree.

Deliberately has no Qt/Gui dependency, so it can be exercised headlessly
(FreeCADCmd, no QApplication) - see tests/run_tests.py. The Qt-facing
panel (panel.py) is a thin consumer of collect_body_features().
"""

import json
from dataclasses import dataclass, field

ACTIVE = "active"
SUPPRESSED = "suppressed"
ERROR = "error"

GROUP_TYPE_ID = "Group"
_GROUPS_PROPERTY = "ATPD_Groups"

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
    """One row of the read-only feature tree, with its nested children.

    A row with is_group=True is a purely visual folder (see the group_*
    functions below): name holds the group id, label its display name,
    type_id is GROUP_TYPE_ID, and state is always ACTIVE (folders have no
    Suppressed/error concept of their own).
    """

    name: str
    label: str
    type_id: str
    state: str
    children: list["FeatureRow"] = field(default_factory=list)
    is_group: bool = False


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

    return _apply_groups(body, top_level)


def _apply_groups(body, top_level: list[FeatureRow]) -> list[FeatureRow]:
    """Nest top-level rows under their ATPD group folder, if any.

    A group folder appears at the position of its earliest member (the
    first one encountered while walking top_level, which is already in
    Tip order) - no separate ordering field needed. Rows for objects
    with no recorded group, or whose recorded group id no longer exists,
    are left untouched at the top level.
    """
    groups, membership = load_groups(body)
    if not groups:
        return top_level

    group_rows: dict[str, FeatureRow] = {}
    result: list[FeatureRow] = []
    for row in top_level:
        group_id = membership.get(row.name)
        if group_id is None or group_id not in groups:
            result.append(row)
            continue
        if group_id not in group_rows:
            group_row = FeatureRow(
                name=group_id,
                label=groups[group_id],
                type_id=GROUP_TYPE_ID,
                state=ACTIVE,
                is_group=True,
            )
            group_rows[group_id] = group_row
            result.append(group_row)
        group_rows[group_id].children.append(row)
    return result


def _related_objects(obj, list_attr: str) -> list:
    """Shared dedup + own-Body exclusion for the InList/OutList lookups below.

    obj.InList/OutList always include the Body (via its Group property),
    which isn't a meaningful dependency relationship for either warning
    or highlighting purposes, so it's filtered out. Both lists can also
    list the same object more than once when it's linked through several
    properties (e.g. both AttachmentSupport and ExternalGeometry), so
    results are deduped, preserving order.
    """
    seen = set()
    related = []
    for other in getattr(obj, list_attr):
        if other.TypeId == "PartDesign::Body" or other.Name in seen:
            continue
        seen.add(other.Name)
        related.append(other)
    return related


def find_dependents(obj) -> list:
    """Other document objects that reference obj (consume/depend on it).

    This is obj.InList: objects pointing *to* obj. Used for the
    suppress/delete impact warning and, as "children", for the
    dependency-highlight feature.
    """
    return _related_objects(obj, "InList")


def find_dependencies(obj) -> list:
    """Other document objects that obj itself references (its prerequisites).

    This is obj.OutList: objects obj points *to* - e.g. a Pad's Profile
    sketch or its BaseFeature. Used as "parents" for the
    dependency-highlight feature.
    """
    return _related_objects(obj, "OutList")


def toggle_suppressed(doc, obj) -> bool:
    """Flip obj.Suppressed inside a transaction and recompute. Returns the new value.

    The transaction is committed only if both the property change and the
    recompute succeed; any exception aborts it first, so the document is
    never left half-changed, then re-raises for the caller to report.
    """
    new_value = not obj.Suppressed
    doc.openTransaction(f"{'Suppress' if new_value else 'Unsuppress'} {obj.Label}")
    try:
        obj.Suppressed = new_value
        doc.recompute()
    except Exception:
        doc.abortTransaction()
        raise
    doc.commitTransaction()
    return new_value


def rename_label(doc, obj, new_label: str) -> bool:
    """Set obj.Label (never obj.Name, the immutable internal identifier)
    inside a transaction. Returns whether it was actually applied.

    Blank/whitespace-only input is rejected (the caller should restore
    the displayed text). FreeCAD's own Label setter already resolves
    duplicates by auto-appending a numeric suffix when another object in
    the document already has that exact Label (verified empirically -
    the Label property is not a simple pass-through), so no separate
    uniqueness check is needed here.
    """
    new_label = new_label.strip()
    if not new_label or new_label == obj.Label:
        return False
    doc.openTransaction(f"Rename {obj.Label} to {new_label}")
    try:
        obj.Label = new_label
    except Exception:
        doc.abortTransaction()
        raise
    doc.commitTransaction()
    return True


def delete_objects(doc, names: list[str]) -> None:
    """Remove multiple objects by name inside a single transaction.

    All-or-nothing: any exception aborts the whole transaction and
    re-raises, so a partially-completed delete never lingers. Order
    matters only in that it's applied as given - callers wanting a
    feature's children gone first should list them before the feature.
    """
    doc.openTransaction("Delete " + ", ".join(names))
    try:
        for name in names:
            doc.removeObject(name)
        doc.recompute()
    except Exception:
        doc.abortTransaction()
        raise
    doc.commitTransaction()


def isolate_object(body_objects, obj) -> dict[str, bool]:
    """Hide every object's ViewObject except obj's.

    Returns the prior visibility state (name -> bool) so it can be
    restored later via restore_visibilities(). No-op for any object
    lacking a ViewObject (e.g. no Gui session, such as FreeCADCmd), and
    for the whole call if that applies to everything - it degrades to
    doing nothing rather than raising, since isolating is purely a
    visual convenience with nothing to roll back if it can't act.
    """
    previous = {}
    for other in body_objects:
        view_object = getattr(other, "ViewObject", None)
        if view_object is None:
            continue
        previous[other.Name] = view_object.Visibility
        view_object.Visibility = other.Name == obj.Name
    return previous


def restore_visibilities(doc, previous: dict[str, bool]) -> None:
    """Undo isolate_object(): reapply each object's saved Visibility."""
    for name, visible in previous.items():
        obj = doc.getObject(name)
        view_object = getattr(obj, "ViewObject", None) if obj is not None else None
        if view_object is not None:
            view_object.Visibility = visible


def _ensure_groups_property(obj) -> None:
    """Add the ATPD_Groups custom property to obj (the Body) if missing.

    A plain App::PropertyString holding JSON - a real, ordinary FreeCAD
    property, so the file stays ENF3-compatible: vanilla FreeCAD just
    shows it as an extra Data-tab property it doesn't understand, and
    nothing about the document's actual geometry/features changes.
    Hidden from the property editor since it's an ATPD implementation
    detail, not something a user should hand-edit.
    """
    if _GROUPS_PROPERTY not in obj.PropertiesList:
        obj.addProperty(
            "App::PropertyString",
            _GROUPS_PROPERTY,
            "ATPD",
            "ATPD feature groups (JSON) - organizational only, not a real FreeCAD structure",
        )
        obj.setPropertyStatus(_GROUPS_PROPERTY, "Hidden")


def load_groups(obj) -> tuple[dict[str, str], dict[str, str]]:
    """Read (group_id -> group_name, feature_name -> group_id) from obj.

    obj is normally the Body. Missing property, blank value, or corrupt
    JSON all return two empty dicts rather than raising - groups are a
    pure UI convenience layered on top of the real document, never
    something that should stop the tree from displaying.
    """
    if _GROUPS_PROPERTY not in obj.PropertiesList:
        return {}, {}
    raw = getattr(obj, _GROUPS_PROPERTY, "")
    if not raw:
        return {}, {}
    try:
        data = json.loads(raw)
        return dict(data.get("groups", {})), dict(data.get("membership", {}))
    except (json.JSONDecodeError, AttributeError, TypeError):
        return {}, {}


def save_groups(
    doc, obj, groups: dict[str, str], membership: dict[str, str]
) -> None:
    """Persist (groups, membership) to obj's custom property, in a transaction."""
    _ensure_groups_property(obj)
    payload = json.dumps({"groups": groups, "membership": membership})
    doc.openTransaction("Update ATPD groups")
    try:
        setattr(obj, _GROUPS_PROPERTY, payload)
    except Exception:
        doc.abortTransaction()
        raise
    doc.commitTransaction()


def _new_group_id(existing: dict[str, str]) -> str:
    i = 1
    while f"group_{i}" in existing:
        i += 1
    return f"group_{i}"


def create_group(doc, obj, name: str, member_names: list[str]) -> str:
    """Create a new group named `name` containing member_names.

    Any member already in another group is moved (a name can only ever
    belong to one group at a time). Returns the new group's id.
    """
    groups, membership = load_groups(obj)
    group_id = _new_group_id(groups)
    groups[group_id] = name
    for member in member_names:
        membership[member] = group_id
    save_groups(doc, obj, groups, membership)
    return group_id


def rename_group(doc, obj, group_id: str, new_name: str) -> bool:
    """Rename a group. Returns whether it was actually applied.

    Blank/whitespace-only input and an unknown group_id are both
    rejected (no-op), same rejection shape as rename_label().
    """
    new_name = new_name.strip()
    groups, membership = load_groups(obj)
    if group_id not in groups or not new_name or groups[group_id] == new_name:
        return False
    groups[group_id] = new_name
    save_groups(doc, obj, groups, membership)
    return True


def dissolve_group(doc, obj, group_id: str) -> None:
    """Remove a group, promoting its members back to the top level."""
    groups, membership = load_groups(obj)
    if group_id not in groups:
        return
    del groups[group_id]
    membership = {name: gid for name, gid in membership.items() if gid != group_id}
    save_groups(doc, obj, groups, membership)


def move_to_group(doc, obj, member_names: list[str], group_id: str | None) -> None:
    """Move features into a group, or to the top level if group_id is None."""
    groups, membership = load_groups(obj)
    for member in member_names:
        if group_id is None:
            membership.pop(member, None)
        else:
            membership[member] = group_id
    save_groups(doc, obj, groups, membership)
