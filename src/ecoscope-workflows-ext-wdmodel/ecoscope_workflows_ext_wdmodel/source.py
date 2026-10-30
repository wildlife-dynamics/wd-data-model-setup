"""Where a model comes from: the shipped file, or another live instance.

Two cases, one shape. ``Source.shipped()`` is the WD standard model travelling
inside the wheel; ``Source.from_export()`` is whatever a user pointed at. The
planner takes a Source and does not care which it got, so copying one site's
categories onto another reuses the ordering, idempotency and collision checks
already built for the standard model rather than growing a second code path.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Iterable

from . import model


@dataclass
class Source:
    """A set of categories, event types and the choice lists they reference."""

    categories: list[dict[str, Any]] = field(default_factory=list)
    event_types: list[dict[str, Any]] = field(default_factory=list)
    choices: list[dict[str, Any]] = field(default_factory=list)
    origin: str = "shipped"

    # ---------------------------------------------------------- builders ---

    @classmethod
    def shipped(cls) -> "Source":
        m = model.load()
        return cls(
            categories=copy.deepcopy(m["categories"]),
            event_types=copy.deepcopy(m["event_types"]),
            choices=copy.deepcopy(m["choices"]),
            origin="the WD standard model",
        )

    @classmethod
    def from_export(
        cls,
        categories: list[dict[str, Any]],
        event_types: list[dict[str, Any]],
        choices: list[dict[str, Any]],
        origin: str,
    ) -> "Source":
        """A model read off a live instance.

        The caller does the HTTP and hands the three lists in, so this stays
        testable with fixtures.
        """
        return cls(
            categories=copy.deepcopy(categories),
            event_types=copy.deepcopy(event_types),
            choices=copy.deepcopy(choices),
            origin=origin,
        )

    # ----------------------------------------------------------- queries ---

    def category_values(self) -> list[str]:
        return [c["value"] for c in self.categories]

    def types_in(self, selected: Iterable[str] | None = None) -> list[dict[str, Any]]:
        if selected is None:
            return copy.deepcopy(self.event_types)
        wanted = set(selected)
        unknown = wanted - set(self.category_values())
        if unknown:
            raise ValueError(
                f"not categories in {self.origin}: {sorted(unknown)}. "
                f"Available: {self.category_values()}"
            )
        return copy.deepcopy([t for t in self.event_types if t["category"] in wanted])

    def types_named(self, values: Iterable[str]) -> list[dict[str, Any]]:
        """Specific event types, by value.

        The copy path selects types rather than categories, because the form
        can populate a list of an instance's event types from the connection
        and cannot do the same for categories. Each type carries its own
        category, so the categories follow.
        """
        wanted = list(values)
        have = {t["value"] for t in self.event_types}
        missing = [v for v in wanted if v not in have]
        if missing:
            raise ValueError(
                f"not event types on the source: {sorted(missing)}. "
                "They may be v1 only -- a v1 form keeps its options inline "
                "rather than in registered choice lists and cannot be copied."
            )
        return copy.deepcopy([t for t in self.event_types if t["value"] in set(wanted)])

    def categories_of(self, types: Iterable[dict[str, Any]]) -> list[str]:
        """The categories the given types belong to, in model order."""
        used = {t["category"] for t in types}
        return [c["value"] for c in self.categories if c["value"] in used]

    def recategorise(
        self, types: list[dict[str, Any]], value: str, display: str = ""
    ) -> None:
        """Put every one of these types into a single category on the target.

        Copying does not have to preserve the source's filing. Westgate's
        standard-model types lived in `field_monitoring_2` -- a name it carries
        only because of a permissions collision in its own history -- and they
        were written into MMNR as plain `field_monitoring`. Inheriting the
        source's category would have carried that accident across, and every
        later instance would have inherited it again.

        The category is added to this Source if it is not already one of its
        own, so the planner creates it on the target like any other.
        """
        for t in types:
            t["category"] = value
        if value not in self.category_values():
            self.categories.append(
                {
                    "value": value,
                    "display": display or value.replace("_", " ").title(),
                    "ordernum": len(self.categories) + 1,
                    "flag": "user",
                }
            )

    def rename_lists(self, mapping: dict[str, str]) -> int:
        """Rename choice lists and move every $ref with them.

        Both halves, always. Renaming the rows without rewriting the schemas
        leaves the form bound to whatever carries the old name on the target --
        which is the bug the rename was meant to avoid, now harder to see.
        """
        if not mapping:
            return 0
        moved = model.repoint(self.event_types, mapping)
        for row in self.choices:
            if row["field"] in mapping:
                row["field"] = mapping[row["field"]]
        return moved

    def lists_for(self, types: Iterable[dict[str, Any]]) -> set[str]:
        """The choice lists these types reference, and no others."""
        out: set[str] = set()
        for t in types:
            out |= model.refs_in(t["schema"])
        return out

    def rows_for(self, fields: Iterable[str]) -> list[dict[str, Any]]:
        wanted = set(fields)
        return [c for c in self.choices if c["field"] in wanted]

    def values_of(self, field_name: str) -> set[str]:
        return {c["value"] for c in self.choices if c["field"] == field_name}

    def field_count(self, event_type: str) -> int:
        for t in self.event_types:
            if t["value"] != event_type:
                continue
            schema = t["schema"].get("json", t["schema"])
            n = len(schema.get("properties") or {})
            for blk in schema.get("allOf") or []:
                n += len((blk.get("then") or {}).get("properties") or {})
            return n
        return 0

    def display_of(self, category_value: str) -> str:
        for c in self.categories:
            if c["value"] == category_value:
                return c.get("display") or category_value
        return category_value


def export_everything(read, origin: str) -> tuple["Source", list[str]]:
    """List every v2 event type on an instance -- names only, no schemas.

    Used by the copy path, which selects event types rather than categories:
    the form can populate a type list from the connection and cannot do the
    same for categories.

    Deliberately WITHOUT schemas. The v2 list endpoint ignores
    include_schema, so asking for them here returns types whose `schema` is
    empty and they all get dropped as unusable -- a copy that reports nothing
    to do and looks like the source was empty. Schemas come one type at a
    time from the detail endpoint, so `fetch_schemas` runs after the
    selection narrows the list, and the same is true of choice rows.
    """
    warnings: list[str] = []
    cats = read("activity/events/categories", {"include_inactive": "true"})
    # page_size, because nothing here follows `next`. An instance with more
    # types than one default page would come back truncated, and the missing
    # ones would look like types that do not exist -- then fail on create as
    # duplicates.
    v2 = read("activity/eventtypes", {"include_inactive": "true", "page_size": 1000})

    def cat_of(t: dict) -> str:
        c = t.get("category")
        return (c or {}).get("value") if isinstance(c, dict) else c

    for t in v2:
        t["category"] = cat_of(t)

    return cls_from(cats, v2, origin), warnings


def fetch_schemas(read_one, types: list[dict]) -> list[str]:
    """Fill in each chosen type's schema, in place, from the v2 detail route.

    `read_one` must return ONE record, not a list. This is a detail route,
    and a list-shaped reader turns a dict into a list of its keys -- which
    reads as "no schema" and reports a perfectly good v2 type as v1.

    One request per type, which is why it runs on the selection rather than
    the whole instance. A type whose schema cannot be read is left with an
    empty one and named in the warnings; the caller drops it rather than
    writing an event type with no form.
    """
    warnings: list[str] = []
    for t in types:
        tid = t.get("id")
        if not tid:
            warnings.append(
                f"event type '{t.get('value')}' has no id on the source and "
                "could not be read"
            )
            t["schema"] = {}
            continue
        detail = (
            read_one(f"activity/eventtypes/{tid}/", {"include_schema": "true"}) or {}
        )
        schema = detail.get("schema")
        if isinstance(schema, str):
            import json as _json

            try:
                schema = _json.loads(schema)
            except ValueError:
                schema = None
        # A v2 schema is {"json": ..., "ui": ...}. Some instances answer with
        # the bare json document instead of the wrapper, so accept that too
        # rather than discarding a schema that is actually there.
        if isinstance(schema, dict) and not schema.get("json"):
            if schema.get("properties") or schema.get("definition"):
                schema = {"json": schema}
        if not isinstance(schema, dict) or not schema.get("json"):
            warnings.append(
                f"event type '{t.get('value')}' returned no v2 schema and "
                "was skipped. Most likely a v1 type -- a v1 form keeps its "
                "options inline rather than in choice lists and cannot be "
                f"copied as a v2 form. Got: {_shape(detail)}"
            )
            t["schema"] = {}
            continue
        t["schema"] = schema
    return warnings


def _shape(payload: Any) -> str:
    """A short description of what came back, for a warning the reader can act
    on. 'no v2 schema' alone cannot be told apart from a parsing mistake."""
    if not payload:
        return "an empty response"
    if isinstance(payload, dict):
        keys = sorted(payload)[:8]
        return f"an object with keys {keys}"
    return f"a {type(payload).__name__}"


def cls_from(cats, types, origin) -> "Source":
    return Source.from_export(
        categories=cats, event_types=types, choices=[], origin=origin
    )


def fetch_rows(read, src: "Source", needed: Iterable[str]) -> list[str]:
    """Fill in the choice rows for the lists these types reference.

    Only the referenced ones: a source instance may carry hundreds of lists
    belonging to other people's forms.
    """
    warnings: list[str] = []
    rows: list[dict[str, Any]] = []
    for f in sorted(set(needed)):
        got = read(
            "choices", {"field": f, "page_size": 500, "include_inactive": "true"}
        )
        rows += [
            {
                "field": f,
                "value": r.get("value"),
                "display": r.get("display"),
                "ordernum": r.get("ordernum"),
                "is_active": r.get("is_active", True),
            }
            for r in got
            if r.get("field") == f
        ]
    src.choices = rows
    empty = sorted(set(needed) - {r["field"] for r in rows})
    if empty:
        warnings.append(
            f"{len(empty)} referenced choice list(s) came back empty from the "
            f"source: {empty[:6]}. They would copy across as empty dropdowns."
        )
    return warnings


def export_from(
    read,
    wanted_categories: Iterable[str],
    origin: str,
) -> tuple["Source", list[str]]:
    """Read a model off a live instance. Returns (source, warnings).

    NOT ON THE LIVE PATH. The copy workflow selects event types, not
    categories, so it uses `export_everything` + `fetch_schemas` instead.
    This is kept for a category-wise export and is covered by tests whose
    fake instance returns schemas from the LIST endpoint -- which the real
    v2 API does not do. That fiction is precisely what let the live bug
    through, so do not take these tests as evidence this function works
    against a real instance. Fix the include_schema read here before using
    it.

    ``read(path, params) -> list[dict]`` is the only way out to the network.

    v2 only. The v1 and v2 event-type namespaces are disjoint -- a v1 type is
    invisible to the v2 endpoint -- and a v1 schema carries its options inline
    rather than as registered choice lists, so it cannot be copied as a v2
    form. Anything only in v1 is reported rather than silently dropped.
    """
    warnings: list[str] = []
    wanted = [c.strip() for c in wanted_categories if c.strip()]

    # include_inactive everywhere: ER hides deactivated things by default, and
    # an inactive CATEGORY hides its active types too. Export against the
    # partial view and the copy arrives missing forms nobody noticed were
    # there.
    cats = read("activity/events/categories", {"include_inactive": "true"})
    v2 = read(
        "activity/eventtypes", {"include_inactive": "true", "include_schema": "true"}
    )
    v1 = read("activity/events/eventtypes", {"include_inactive": "true"})

    known = {c.get("value") for c in cats}
    missing = [c for c in wanted if c not in known]
    if missing:
        raise ValueError(
            f"not categories on the source instance: {missing}. "
            f"Available: {sorted(v for v in known if v)}"
        )

    def cat_of(t: dict) -> str:
        c = t.get("category")
        return (c or {}).get("value") if isinstance(c, dict) else c

    types = [t for t in v2 if cat_of(t) in set(wanted)]

    v2_values = {t.get("value") for t in v2}
    v1_only = [
        t.get("value")
        for t in v1
        if cat_of(t) in set(wanted) and t.get("value") not in v2_values
    ]
    if v1_only:
        warnings.append(
            f"{len(v1_only)} event type(s) in the selected categories are v1 "
            f"only and were NOT copied: {sorted(v1_only)[:8]}. A v1 form keeps "
            "its options inline instead of in registered choice lists, so it "
            "cannot be recreated as a v2 form without being rebuilt."
        )

    # Normalise to the shape the shipped model uses, so the planner cannot
    # tell the two apart. ER returns `category` as a nested object here and as
    # a plain value in the export file, and `schema` as a JSON string on some
    # instances and a dict on others.
    for t in types:
        t["category"] = cat_of(t)
        s = t.get("schema")
        if isinstance(s, str):
            import json as _json

            t["schema"] = _json.loads(s)

    src = Source.from_export(
        categories=[c for c in cats if c.get("value") in set(wanted)],
        event_types=types,
        choices=[],
        origin=origin,
    )

    # Only the lists these schemas actually reference. A source instance may
    # carry hundreds belonging to other people's forms.
    needed = src.lists_for(types)
    rows: list[dict[str, Any]] = []
    for f in sorted(needed):
        got = read(
            "choices", {"field": f, "page_size": 500, "include_inactive": "true"}
        )
        rows += [
            {
                "field": f,
                "value": r.get("value"),
                "display": r.get("display"),
                "ordernum": r.get("ordernum"),
                "is_active": r.get("is_active", True),
            }
            for r in got
            if r.get("field") == f
        ]
    src.choices = rows

    empty = sorted(needed - {r["field"] for r in rows})
    if empty:
        warnings.append(
            f"{len(empty)} referenced choice list(s) came back empty from the "
            f"source: {empty[:6]}. They would copy across as empty dropdowns."
        )
    return src, warnings


def plan_renames(
    src: "Source",
    needed: Iterable[str],
    target_rows: Iterable[dict[str, Any]],
    prefix: str,
) -> tuple[dict[str, str], list[str]]:
    """Give colliding lists a prefixed name of their own. Returns (map, warnings).

    Only the ones that actually clash. A list whose options already match the
    target's is left alone and shared, which is the point -- renaming
    everything would give each instance its own private vocabulary and defeat
    the comparability the standard model exists for.

    A rename is refused rather than forced when the new name would not be
    usable, because a half-applied rename is worse than none: the schema would
    point at one name and the rows would be written under another.
    """
    warnings: list[str] = []
    mapping: dict[str, str] = {}

    if not model.VALUE_RE.match(prefix.rstrip("_") or "x"):
        raise ValueError(
            f"prefix {prefix!r} must be lowercase letters, digits and " "underscores"
        )

    clashing = collisions(src, needed, target_rows)
    if not clashing:
        return mapping, warnings

    on_target = {r.get("field") for r in target_rows}
    taken = set(on_target) | set(needed)

    for old in sorted(clashing):
        new = f"{prefix}{old}"
        if len(new) > model.MAX_LIST_NAME:
            warnings.append(
                f"'{old}' clashes with a different list on the target, but "
                f"'{new}' is {len(new)} characters and the field column is "
                f"varchar({model.MAX_LIST_NAME}). Rename it by hand, or use a "
                "shorter prefix."
            )
            continue
        if new in taken:
            warnings.append(
                f"'{old}' clashes with a different list on the target, but "
                f"'{new}' is already taken too -- renaming would collide "
                "again. Use a different prefix."
            )
            continue
        mapping[old] = new
        taken.add(new)

    if mapping:
        warnings.append(
            f"{len(mapping)} clashing choice list(s) renamed on the way in: "
            + ", ".join(f"{o} -> {n}" for o, n in sorted(mapping.items()))
            + ". The target's own lists are untouched."
        )
    return mapping, warnings


def collisions(
    source: Source,
    needed: Iterable[str],
    target_rows: Iterable[dict[str, Any]],
) -> dict[str, tuple[set[str], set[str]]]:
    """Lists that exist on both sides with different options.

    This is the failure that does not announce itself. A list already on the
    target is skipped rather than overwritten -- correct, because overwriting
    somebody else's vocabulary would be worse -- but it means the copied form
    binds to the TARGET's version. If the two differ, a conditional that keys
    on a value the target does not have simply never fires, and the section it
    guards never appears. No error, no warning from EarthRanger, and the form
    looks complete until a ranger needs that section.

    Returns ``{field: (only_in_source, only_in_target)}`` for lists that differ.
    """
    by_field: dict[str, set[str]] = {}
    for row in target_rows:
        f = row.get("field")
        if f:
            by_field.setdefault(f, set()).add(row.get("value"))

    out: dict[str, tuple[set[str], set[str]]] = {}
    for f in needed:
        if f not in by_field:
            continue  # not on the target; it will be created
        mine = source.values_of(f)
        theirs = by_field[f]
        if mine and mine != theirs:
            out[f] = (mine - theirs, theirs - mine)
    return out
