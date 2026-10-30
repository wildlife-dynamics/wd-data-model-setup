"""Work out what is missing on a target instance, and in what order.

Pure functions: nothing here touches the network. The task wrappers read the
instance, hand the lists in, and apply whatever comes back. That split is what
makes the ordering rule testable without a live instance.

The ordering rule, which must not move:

    1. categories
    2. choice lists
    3. event types
    4. schemas

A schema whose $refs point at lists that do not exist yet is accepted by the
API and renders as empty dropdowns. Nothing errors, nobody notices until a
ranger opens the form in the field.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from . import model

#: Creation order. Also the sort order of a plan, so reading it top to bottom
#: is the order the writes happen in.
KINDS = ("category", "choice", "event_type", "schema")


@dataclass(frozen=True)
class Action:
    kind: str  # one of KINDS
    name: str  # human-facing identifier
    value: str  # the value written to ER
    detail: str = ""  # why, or what it belongs to
    payload: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def order(self) -> int:
        return KINDS.index(self.kind)


def target_value(event_type: str, prefix: str = "") -> str:
    """The value an event type takes on the target.

    A prefix exists so a rehearsal does not consume the name the real build
    needs later -- event type values are unique per instance, so an unprefixed
    test build is a name you cannot have back.
    """
    return f"{prefix}{event_type}" if prefix else event_type


def plan(
    *,
    selected_categories: Iterable[str],
    existing_categories: Iterable[dict[str, Any]],
    existing_types: Iterable[dict[str, Any]],
    existing_choice_fields: Iterable[str],
    src: "Source | None" = None,
    existing_choice_rows: Iterable[dict[str, Any]] | None = None,
    prefix: str = "",
    species_list: str = "",
    activate: bool = False,
    replace_schema: bool = False,
) -> tuple[list[Action], list[str]]:
    """What to create, in order. Returns (actions, warnings).

    ``src`` is where the model comes from -- the shipped file by default, or a
    Source exported from another instance when copying. Nothing is written.
    Anything already present is skipped rather than recreated, so a re-run
    after a partial failure finishes the job instead of colliding with itself.
    """
    from .source import Source, collisions

    if src is None:
        src = Source.shipped()
    warnings: list[str] = []
    selected = list(selected_categories)
    types = src.types_in(selected)

    # A site may keep its own species list. Repoint rather than create: the
    # alternative is two species lists on one instance, which is how a model
    # starts to fork.
    if species_list and species_list != model.SPECIES_LIST:
        moved = model.repoint(types, {model.SPECIES_LIST: species_list})
        if moved == 0:
            warnings.append(
                f"asked to use '{species_list}' for species, but no schema in "
                f"the selected categories references '{model.SPECIES_LIST}' -- "
                "nothing was repointed."
            )
        if species_list not in set(existing_choice_fields):
            warnings.append(
                f"'{species_list}' is not a choice list on this instance. The "
                "species dropdown will render empty until it exists."
            )

    have_cats = {c.get("value") for c in existing_categories}
    have_types = {t.get("value") for t in existing_types}
    have_lists = set(existing_choice_fields)

    actions: list[Action] = []

    # 1. categories
    for c in src.categories:
        if c["value"] not in selected:
            continue
        if c["value"] in have_cats:
            continue
        actions.append(
            Action(
                "category",
                c.get("display") or c["value"],
                c["value"],
                "create",
                payload=dict(c),
            )
        )

    # 2. choice lists -- only those the selected types actually reference
    needed = src.lists_for(types)
    # a repointed species list belongs to the site, not to us
    if species_list and species_list != model.SPECIES_LIST:
        needed.discard(species_list)

    # Same name, different options. Skipping is right -- overwriting somebody
    # else's vocabulary would be worse -- but the copied form then binds to the
    # target's list, and a conditional keyed on a value the target lacks never
    # fires. Nothing errors. This is the Left Tusk failure, and it is why MMNR
    # needed fm_tusk_status.
    if existing_choice_rows is not None:
        for f, (only_src, only_tgt) in sorted(
            collisions(src, needed, existing_choice_rows).items()
        ):
            warnings.append(
                f"choice list '{f}' already exists on the target with "
                f"different options and will NOT be overwritten. Missing "
                f"there: {sorted(only_src)[:6]}. Extra there: "
                f"{sorted(only_tgt)[:6]}. Any form rule keyed on a missing "
                "value will silently never fire -- rename the list or "
                "reconcile it before relying on these forms."
            )

    for f in sorted(needed - have_lists):
        rows = src.rows_for([f])
        if not rows:
            warnings.append(
                f"'{f}' is referenced by a schema but has no rows in "
                f"{src.origin} -- it would render as an empty dropdown."
            )
            continue
        if len(f) > model.MAX_LIST_NAME:
            warnings.append(
                f"choice list name '{f}' is {len(f)} characters; the field "
                "column is varchar(40) and the write will fail."
            )
        actions.append(
            Action(
                "choice", f, f, f"{len(rows)} rows", payload={"field": f, "rows": rows}
            )
        )

    # 3 and 4. event types, then their schemas
    for t in types:
        value = target_value(t["value"], prefix)
        if value in have_types:
            if replace_schema:
                actions.append(
                    Action("schema", t["display"], value, "replace existing", payload=t)
                )
            continue
        body = dict(t)
        body["value"] = value
        body["is_active"] = bool(activate)
        actions.append(
            Action(
                "event_type",
                t["display"],
                value,
                f"{src.field_count(t['value'])} fields",
                payload=body,
            )
        )
        actions.append(
            Action("schema", t["display"], value, "with the event type", payload=body)
        )

    actions.sort(key=lambda a: (a.order, a.value))

    if not activate:
        warnings.append(
            "types are being created INACTIVE. A category with no active types "
            "is invisible in EarthRanger to everyone, superusers included -- "
            "nothing will appear until they are activated."
        )
    return actions, warnings


def summarise(actions: Iterable[Action]) -> dict[str, int]:
    out = {k: 0 for k in KINDS}
    for a in actions:
        out[a.kind] += 1
    return out


@dataclass
class Result:
    action: Action
    outcome: str  # planned | created | failed
    detail: str = ""


#: Where each kind of thing is written, and with which verb. A category and an
#: event type are POSTed; a schema is a field on an event type and goes on with
#: PATCH. v2 additionally requires `schema` in the CREATE body -- a type created
#: without it is rejected outright, which is not true of v1.
ENDPOINTS = {
    "category": ("POST", "activity/events/categories"),
    "choice": ("POST", "choices"),
    "event_type": ("POST", "activity/eventtypes"),
}


def _payload(action: Action) -> dict[str, Any]:
    """The body for one write."""
    if action.kind == "category":
        return {
            k: v
            for k, v in action.payload.items()
            if k in ("value", "display", "ordernum", "flag")
        }
    if action.kind == "event_type":
        t = action.payload
        return {
            "value": t["value"],
            "display": t["display"],
            "category": t["category"],
            "geometry_type": t.get("geometry_type") or "Point",
            "default_priority": t.get("default_priority", 0),
            "ordernum": t.get("ordernum"),
            "is_collection": t.get("is_collection", False),
            "icon": t.get("icon"),
            "is_active": t.get("is_active", False),
            # v2 refuses a create without this.
            "schema": t["schema"],
        }
    raise ValueError(f"no single payload for {action.kind}")


def apply(
    actions: Iterable[Action],
    send,
    *,
    dry_run: bool = True,
    existing_ids: dict[str, str] | None = None,
) -> list[Result]:
    """Execute the plan in order. Returns one Result per action.

    ``send(method, path, payload) -> response`` is the only way out to the
    network; everything else here is arithmetic, so the ordering and the
    stop-on-failure behaviour are testable with a fake.

    Stops at the first failure. The alternative -- carrying on -- leaves an
    instance half built in a way nobody can read: the report would say
    "created" for things whose dependencies never landed. Stopping means the
    next run resumes from the same point, because the plan is recomputed
    against what is actually there.
    """
    ids = dict(existing_ids or {})
    created_types: set[str] = set()
    results: list[Result] = []

    for action in actions:
        if dry_run:
            results.append(Result(action, "planned", "dry run - nothing written"))
            continue

        try:
            if action.kind == "choice":
                # One row per POST; there is no bulk endpoint.
                n = 0
                for row in action.payload["rows"]:
                    send(
                        "POST",
                        "choices",
                        {
                            "model": "activity.event",
                            "field": action.payload["field"],
                            "value": row["value"],
                            "display": row["display"],
                            "ordernum": row.get("ordernum"),
                        },
                    )
                    n += 1
                results.append(Result(action, "created", f"{n} rows"))

            elif action.kind == "schema":
                # A type created in this run already carries its schema: v2
                # requires it in the CREATE body. PATCHing it again achieves
                # nothing and is how ermigrate came to report "10 failed" on a
                # run where everything had in fact worked -- the second call
                # could not find an id and said so, loudly, about a schema that
                # was already in place.
                if action.value in created_types:
                    results.append(
                        Result(action, "created", "written with the event type")
                    )
                    continue
                tid = ids.get(action.value)
                if not tid:
                    results.append(
                        Result(action, "failed", "no id for an existing event type")
                    )
                    break
                send(
                    "PATCH",
                    f"activity/eventtypes/{tid}/",
                    {"schema": action.payload["schema"]},
                )
                results.append(Result(action, "created", "schema replaced"))

            else:
                method, path = ENDPOINTS[action.kind]
                resp = send(method, path, _payload(action))
                new_id = _id_of(resp)
                if action.kind == "event_type":
                    created_types.add(action.value)
                    if new_id:
                        ids[action.value] = new_id
                results.append(Result(action, "created", ""))

        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            results.append(Result(action, "failed", f"{type(exc).__name__}: {exc}"))
            break

    return results


def _id_of(response: Any) -> str:
    """The id out of whatever shape the create came back as.

    ER answers a create with the object, or with the object under ``data``, or
    with a ``resource_url`` and no id at all -- which is why a missing id is
    not treated as a failure.
    """
    if isinstance(response, dict):
        if "id" in response:
            return str(response["id"])
        data = response.get("data")
        if isinstance(data, dict) and "id" in data:
            return str(data["id"])
    return ""
