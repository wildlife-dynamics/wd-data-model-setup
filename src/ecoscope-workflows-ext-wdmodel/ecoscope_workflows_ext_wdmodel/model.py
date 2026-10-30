"""The WD standard data model, as shipped inside this package.

One file, 27 event types across four categories, every choice list they
reference. It travels in the wheel rather than being read from a reference
instance at run time, so a brand new organisation can be set up with nothing
else reachable and two runs a month apart produce the same thing.

Exported from the trwg_ test build on wildlifedynamics.pamdas.org and then
reconciled against the live Westgate, Naibunga and MMNR instances -- see
RECONCILIATION.md for what was taken from where and why.
"""

from __future__ import annotations

import copy
import csv
import io
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Literal

#: Every $ref in a v2 schema points at a registered choice list by this shape.
REF = "/api/v2.0/schemas/choices.json?field={}"

#: The list a site is most likely to want to replace with its own. Everything
#: else is purpose-specific (vulture species at a carcass, livestock species)
#: and is not worth offering as a knob.
SPECIES_LIST = "species"

#: The categories a user can pick, for the form.
#:
#: Spelled out rather than derived from the model file, because rjsf needs a
#: Literal's static members to render real choices -- a dynamic enum gives a
#: free-text box. It lives here, beside the data it mirrors, so that it needs
#: no ecoscope import and can be unit-tested; `test_the_form_choices_match_the
#: _model` pins the two together, because an option this forgets is one the
#: form silently never offers.
Category = Literal[
    "animal_health",
    "field_monitoring",
    "hwc",
    "rangeland_monitoring",
]


def _path() -> Path:
    return Path(__file__).parent / "data" / "wd-standard-model-v2.json"


@lru_cache(maxsize=1)
def load() -> dict[str, Any]:
    """The whole model. Cached: it is ~470 KB and never changes at run time."""
    with _path().open() as fh:
        return json.load(fh)


def categories() -> list[dict[str, Any]]:
    """The four categories, in display order."""
    return sorted(load()["categories"], key=lambda c: c.get("ordernum", 0))


def category_values() -> list[str]:
    return [c["value"] for c in categories()]


def event_types(selected: Iterable[str] | None = None) -> list[dict[str, Any]]:
    """Types belonging to the selected categories, or all of them.

    ``selected`` is the category *values*, not display names, because that is
    what the form sends back.

    Deep copies, deliberately. ``load()`` is cached for the life of the
    process, and ``repoint`` rewrites $refs in place -- hand out references to
    the cached dict and one run's species override silently becomes every
    later run's, in the same worker. A shallow copy is not enough: the schema
    is the nested object being rewritten.
    """
    types = load()["event_types"]
    if selected is None:
        return copy.deepcopy(types)
    wanted = set(selected)
    unknown = wanted - set(category_values())
    if unknown:
        raise ValueError(
            f"not categories in the standard model: {sorted(unknown)}. "
            f"Known: {category_values()}"
        )
    return copy.deepcopy([t for t in types if t["category"] in wanted])


def refs_in(node: Any) -> set[str]:
    """Every choice list a schema points at, nested collections included.

    A conditional field lives inside ``allOf[].then.properties`` rather than at
    the top level, and a collection's item fields are deeper still, so this
    walks rather than inspecting ``properties``.
    """
    found: set[str] = set()

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            ref = x.get("$ref")
            if isinstance(ref, str) and "field=" in ref:
                found.add(ref.split("field=")[1].split("&")[0])
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(node)
    return found


def lists_for(types: Iterable[dict[str, Any]]) -> set[str]:
    """The choice lists these types need, and no others.

    An organisation taking only Animal Health should not inherit the rangeland
    lists, so this is driven by the selected types rather than by the file.
    """
    out: set[str] = set()
    for t in types:
        out |= refs_in(t["schema"])
    return out


def choices_for(fields: Iterable[str]) -> list[dict[str, Any]]:
    """Rows for the named lists, in the order they should be created."""
    wanted = set(fields)
    return [c for c in load()["choices"] if c["field"] in wanted]


def field_count(event_type: str) -> int:
    """How many fields a type's form has, conditionals included.

    Reported so an operator can tell a usable type from one that arrived with
    an empty form.
    """
    for t in load()["event_types"]:
        if t["value"] != event_type:
            continue
        schema = t["schema"].get("json", t["schema"])
        n = len(schema.get("properties") or {})
        for blk in schema.get("allOf") or []:
            n += len((blk.get("then") or {}).get("properties") or {})
        return n
    return 0


#: ER's choices.field column. A longer name fails with a 500 and no useful
#: message, so it is checked before anything is written.
MAX_LIST_NAME = 40

#: Stored choice values. The value is what a conditional matches on and what
#: every existing record carries, so it can never be changed once data exists
#: -- which is why the charset is enforced on the way in rather than tidied up
#: later.
VALUE_RE = re.compile(r"^[a-z0-9_]+$")


def parse_species_csv(text: str) -> list[dict[str, Any]]:
    """Rows from a user-supplied species CSV, or raise with the line number.

    Expected columns: ``value``, ``display``, and an optional ``ordernum``.

        value,display,ordernum
        grevys_zebra,Grevy's Zebra,10

    Everything is checked before a single row is returned. A list that is half
    written because row 80 was malformed is worse than one that was refused:
    choice rows have no transaction around them, and the half already created
    would have to be found and removed by hand.
    """
    rows: list[dict[str, Any]] = []
    reader = csv.DictReader(io.StringIO(text))

    missing = {"value", "display"} - set(reader.fieldnames or [])
    if missing:
        raise ValueError(
            f"species CSV is missing required column(s): {sorted(missing)}. "
            "Expected a header row: value,display[,ordernum]"
        )

    seen: set[str] = set()
    for i, raw in enumerate(reader, start=2):  # row 1 is the header
        value = (raw.get("value") or "").strip()
        display = (raw.get("display") or "").strip()
        order = (raw.get("ordernum") or "").strip()

        if not value and not display:
            continue  # blank line, usually a trailing newline
        if not value:
            raise ValueError(f"species CSV line {i}: 'value' is empty")
        if not display:
            raise ValueError(f"species CSV line {i}: 'display' is empty")
        if not VALUE_RE.match(value):
            raise ValueError(
                f"species CSV line {i}: value {value!r} must be lowercase "
                "letters, digits and underscores only -- it is stored on every "
                "record and matched by conditionals, so it cannot be changed "
                "later"
            )
        if value in seen:
            raise ValueError(
                f"species CSV line {i}: duplicate value {value!r}. "
                "EarthRanger would accept both and the dropdown would show the "
                "same option twice."
            )
        seen.add(value)

        row: dict[str, Any] = {"value": value, "display": display, "is_active": True}
        if order:
            try:
                row["ordernum"] = int(order)
            except ValueError:
                raise ValueError(
                    f"species CSV line {i}: ordernum {order!r} is not a whole " "number"
                ) from None
        else:
            row["ordernum"] = None
        rows.append(row)

    if not rows:
        raise ValueError("species CSV has a header but no rows")
    return rows


def repoint(types: list[dict[str, Any]], mapping: dict[str, str]) -> int:
    """Rewrite choice-list $refs in place. Returns how many were changed.

    Renaming a list is never enough on its own: every $ref inside every schema
    has to move with it, or the form silently binds to whatever list already
    carries the old name on the target instance. That half is what this exists
    for -- it is the bug that made MMNR's Left Tusk section unreachable.
    """
    hits = 0

    def walk(x: Any) -> None:
        nonlocal hits
        if isinstance(x, dict):
            ref = x.get("$ref")
            if isinstance(ref, str) and "field=" in ref:
                head, _, tail = ref.partition("field=")
                name, amp, rest = tail.partition("&")
                if name in mapping:
                    hits += 1
                    x["$ref"] = f"{head}field={mapping[name]}{amp}{rest}"
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    for t in types:
        walk(t["schema"])
    return hits
