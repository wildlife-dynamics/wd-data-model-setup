"""Create the model on the target instance.

The only task in this package that writes. Dry run is on by default and has to
be turned off deliberately, because EarthRanger has no undo: a category cannot
be safely deleted, an event type that has taken a single record cannot be
removed, and a choice row written in error has to be found and deactivated by
hand.
"""

from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Any, Literal

import pandas as pd
from ecoscope.platform.annotations import AdvancedField, AnyDataFrame
from ecoscope.platform.connections import EarthRangerClient
from pydantic import Field
from wt_registry import register

from ... import model, provision, source

# The two modes, spelled as the dropdown should read them. A Literal of
# human sentences rather than "standard"/"copy" because RJSF renders enum
# VALUES in the select -- there is no reliable way to give an enum member a
# separate display label through rjsf-overrides, so the value has to be the
# label.
STANDARD = "Set up the WD standard model"
COPY = "Copy event types from another instance"
Mode = Literal[
    "Set up the WD standard model",
    "Copy event types from another instance",
]


# Event types are a v2 resource and live under a DIFFERENT API root from
# everything else here. Categories and choice lists are v1:
#
#   https://host/api/v1.0/activity/events/categories
#   https://host/api/v1.0/choices
#   https://host/api/v2.0/activity/eventtypes/        <- not v1.0
#
# erclient is constructed with the v1.0 root and joins every relative path
# onto it, so `activity/eventtypes` reaches /api/v1.0/activity/eventtypes,
# which does not exist. The server answers 404 and erclient turns that into a
# bare ERClientNotFound(''), with no path in the message -- which is how this
# stayed invisible until a copy run hit it.
#
# Passing a full URL is not a way out either: _get accepts one, but _post and
# _patch always join through _er_url. So the root is swapped for the duration
# of the call instead.
V2_PREFIX = "activity/eventtypes"


@contextmanager
def _rooted_for(client: Any, path: str):
    """Point the client at the API root that owns `path`, just for this call."""
    root = getattr(client, "service_root", None)
    if not path.startswith(V2_PREFIX) or not root or "/api/v1.0" not in root:
        yield
        return
    client.service_root = root.replace("/api/v1.0", "/api/v2.0")
    try:
        yield
    finally:
        client.service_root = root


def _sender(client: Any):
    """POST and PATCH over the erclient session."""

    def send(method: str, path: str, payload: dict):
        with _rooted_for(client, path):
            if method == "PATCH":
                return client._patch(path, payload)
            return client._post(path, payload)

    return send


def _unwrap(client: Any, path: str, params: dict | None) -> Any:
    with _rooted_for(client, path):
        payload = client._get(path, params=params or {})
    # erclient already returns payload["data"] for most responses, but not
    # all of them, so unwrap again if it is still wrapped.
    if isinstance(payload, dict) and ("data" in payload or "results" in payload):
        payload = payload.get("data", payload.get("results"))
    return payload


def _read(client: Any, path: str, params: dict | None = None) -> list[dict]:
    """A LIST endpoint. Always returns a list of records."""
    payload = _unwrap(client, path, params)
    # A detail route reaches this by mistake sooner or later, and `list()` on
    # a dict yields its KEYS -- a list of strings that looks enough like
    # records to travel a long way before failing. One line to make that
    # impossible.
    if isinstance(payload, dict):
        return [payload]
    return list(payload or [])


def _read_one(client: Any, path: str, params: dict | None = None) -> dict:
    """A DETAIL endpoint. Always returns one record, or {}."""
    payload = _unwrap(client, path, params)
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return payload[0]
    return {}


@register()
def apply_data_model(
    client: EarthRangerClient,
    # Bound from a second set_er_connection task. The Desktop collects
    # connections in their own wizard step, derived from the spec's connection
    # tasks, so this one is asked for on every run whatever the mode says --
    # the form cannot withdraw it. `mode` is what makes it harmless: on a
    # standard run this client is never touched, and the connection is there
    # for the copy run only.
    copy_from: EarthRangerClient | None = None,
    # --- which of the two things this run is doing. First on the form,
    # --- because every field below belongs to one mode or the other and this
    # --- is what says which ones are live.
    mode: Annotated[
        Mode,
        Field(
            default=STANDARD,
            description=(
                "Set up the standard model: creates the WD standard model "
                "from the categories below, and IGNORES the copy fields and "
                "the second data source entirely. Copy event types: brings "
                "types across from the instance chosen as the second data "
                "source, and ignores the categories and species fields "
                "instead. The second data source is asked for either way -- "
                "that is the app, not this workflow -- but on a standard run "
                "nothing reads it, so point it anywhere."
            ),
        ),
    ] = STANDARD,
    # --- the standard model. Live only in standard mode.
    categories: Annotated[
        list[model.Category],
        Field(
            default_factory=lambda: list(model.category_values()),
            description=(
                "Which parts of the standard model to set up. Leave all four "
                "selected for the whole thing."
            ),
            json_schema_extra={"uniqueItems": True},
        ),
    ] = None,  # type: ignore[assignment]
    dry_run: Annotated[
        bool,
        Field(
            default=True,
            description=(
                "Leave ON to create nothing and just list what is missing. "
                "Turn it off to write. There is no undo in EarthRanger: a "
                "category cannot be safely deleted and an event type that has "
                "taken one record cannot be removed."
            ),
        ),
    ] = True,
    species_list: Annotated[
        str,
        Field(
            default="",
            description=(
                "Leave empty to create the standard 66-entry species list. To "
                "use a list this instance already has, name it here and every "
                "species field is repointed at it instead of a second list "
                "being created."
            ),
        ),
    ] = "",
    species_csv: Annotated[
        str,
        Field(
            default="",
            description=(
                "Path to a CSV of species to create instead of the standard "
                "list. Needs a header row and the columns value,display with "
                "an optional ordernum -- for example: "
                "grevys_zebra,Grevy's Zebra,10 . 'value' is stored on every "
                "record and is matched by the form's conditionals, so it must "
                "be lowercase letters, digits and underscores, and it can "
                "never be changed once data exists. 'display' is what the "
                "ranger sees. 'ordernum' sets the order in the dropdown and "
                "defaults to alphabetical. The whole file is checked before "
                "anything is written."
            ),
        ),
    ] = "",
    activate: Annotated[
        bool,
        Field(
            default=False,
            description=(
                "Create the event types ACTIVE. A category with no active "
                "types is invisible in EarthRanger to everyone, superusers "
                "included -- so with this off you will see nothing until you "
                "activate them. Note that a new category's permissions start "
                "with only the account running this, so nobody else can see "
                "it either way."
            ),
        ),
    ] = False,
    # --- the copy path. Everything below is ignored unless event types are
    # --- picked, which in turn needs a source instance above.
    copy_event_types: Annotated[
        list[str],
        Field(
            default_factory=list,
            description=(
                "LEAVE EMPTY to set up the WD standard model chosen above -- "
                "this field is what decides between the two. Fill it in only "
                "to copy instead: the list shows the event types on whatever "
                "instance is selected under 'Copy from', and each type you "
                "pick brings its category and its choice lists with it."
            ),
            json_schema_extra={"uniqueItems": True},
        ),
    ] = None,  # type: ignore[assignment]
    copy_into_category: Annotated[
        str,
        Field(
            default="",
            description=(
                "Only used when copying. Leave empty to keep each type in the "
                "category it has on the source. Set it to put all the copied "
                "types into one category on the target instead -- this is how "
                "Westgate's field_monitoring_2 types were written into MMNR "
                "as plain field_monitoring. Lowercase letters, digits and "
                "underscores; it is created if it is not already there."
            ),
        ),
    ] = "",
    collision_prefix: Annotated[
        str,
        Field(
            default="",
            description=(
                "Only used when copying. If a choice list arriving from the "
                "source has the same name as one already on the target but "
                "different options, give the incoming one this prefix -- e.g. "
                "'fm_' turns tusk_status into fm_tusk_status. Only clashing "
                "lists are renamed; ones that already match are shared. Leave "
                "empty to skip them instead, in which case the forms bind to "
                "the target's version and any rule keyed on a missing value "
                "silently never fires."
            ),
        ),
    ] = "",
    prefix: Annotated[
        str,
        AdvancedField(
            default="",
            description=(
                "Prefix every event type value, e.g. 'trw_' for a rehearsal. "
                "Values are unique per instance, so an unprefixed test build "
                "takes the name the real one needs later."
            ),
        ),
    ] = "",
    replace_schema: Annotated[
        bool,
        AdvancedField(
            default=False,
            description=(
                "Also rewrite the schema of event types that already exist. "
                "Off by default: it would replace a live form, possibly one "
                "somebody else built."
            ),
        ),
    ] = False,
) -> Annotated[AnyDataFrame, Field(description="One row per write.")]:
    """Create the selected categories, choice lists, event types and schemas."""
    # Two sources, one planner. Either the model shipped in this package, or
    # one read off another instance. `mode` decides which, explicitly --
    # NOT whether copy_event_types happens to be empty.
    #
    # The difference matters because the app asks for the second data source
    # on every run, so a standard run always arrives here holding a live
    # client for some instance. Inferring intent from the fields would make a
    # stray selection, or a value left behind from an earlier run, silently
    # turn a standard setup into a copy. The dropdown is the only input that
    # decides it, and in standard mode the copy arguments are not read at all.
    export_warnings: list[str] = []
    copying = mode == COPY
    wanted_types = (
        [t.strip() for t in (copy_event_types or []) if t.strip()] if copying else []
    )
    if copying:
        if copy_from is None:
            raise ValueError(
                f"mode is {COPY!r} but no source instance was given. Choose "
                "the instance to copy from under Data Sources."
            )
        if not wanted_types:
            raise ValueError(
                f"mode is {COPY!r} but no event types were chosen. Pick the "
                "source instance first -- the list fills from it -- then "
                "choose what to bring across. To create the standard model "
                f"instead, set mode to {STANDARD!r}."
            )
        read = lambda path, params=None: _read(copy_from, path, params)  # noqa: E731
        read_one = lambda path, params=None: _read_one(copy_from, path, params)  # noqa: E731
        src, export_warnings = source.export_everything(read, "the source instance")
        chosen = src.types_named(wanted_types)
        # Schemas come one at a time from the v2 detail route, so they are
        # read only for what was actually picked. A type whose schema cannot
        # be read is dropped here rather than written as a form-less event
        # type -- it is named in the warnings either way.
        export_warnings += source.fetch_schemas(read_one, chosen)
        chosen = [t for t in chosen if t.get("schema")]
        if not chosen:
            # The per-type warnings say what came back for each one, which is
            # what tells a v1 type apart from a read that went wrong.
            raise ValueError(
                "none of the chosen event types returned a v2 schema, so "
                "there is nothing to copy. Per type: "
                + " | ".join(export_warnings[-10:])
            )
        # Narrow the source to just what was picked, so the plan, the choice
        # lists and the collision check all see the same slice.
        src.event_types = chosen
        if copy_into_category:
            if not model.VALUE_RE.match(copy_into_category):
                raise ValueError(
                    f"category value {copy_into_category!r} must be lowercase "
                    "letters, digits and underscores"
                )
            src.recategorise(chosen, copy_into_category)
        selected = src.categories_of(chosen)
        export_warnings += source.fetch_rows(read, src, src.lists_for(chosen))
    else:
        src = source.Source.shipped()
        selected = list(categories or [])
        if not selected:
            raise ValueError(
                "no categories selected. Choose at least one of: "
                + ", ".join(model.category_values())
            )

    # The species fields belong to the standard model and are dropped in copy
    # mode rather than applied quietly. A copied form's species field points
    # at whatever list the SOURCE gave it, and repointing that at a list
    # chosen for the standard model would change what the copy means without
    # saying so.
    if copying and (species_list or species_csv):
        export_warnings.append(
            "a species list was given but the mode is "
            f"{COPY!r}, so it was ignored. Copied forms keep the species "
            "list they reference on the source instance."
        )
        species_list, species_csv = "", ""

    if species_list and species_csv:
        raise ValueError(
            "choose one species source: either name a list already on the "
            "instance, or supply a CSV -- not both."
        )

    # Parse the CSV before reading the instance, so a malformed file costs
    # nothing and fails with a line number rather than part way through.
    csv_rows: list[dict[str, Any]] = []
    if species_csv:
        path = Path(species_csv).expanduser()
        if not path.is_file():
            raise ValueError(f"no species CSV at {path}")
        csv_rows = model.parse_species_csv(path.read_text())

    # include_inactive everywhere. ER hides deactivated categories, types and
    # choice lists by default, and an inactive CATEGORY hides its active types
    # too -- plan against that partial view and the run tries to create things
    # that are already there.
    # v2, the same namespace the writes go to. Reading the v1 list here would
    # miss every v2 type on the instance and the run would try to create
    # types that are already there.
    existing_types = _read(
        client, "activity/eventtypes", {"include_inactive": "true", "page_size": 1000}
    )
    existing_categories = _read(
        client, "activity/events/categories", {"include_inactive": "true"}
    )
    existing_choices = _read(
        client, "choices", {"include_inactive": "true", "page_size": 5000}
    )
    existing_fields = {c.get("field") for c in existing_choices if c.get("field")}

    # Rename clashing lists before planning, so the plan, the $refs and the
    # rows written all agree. Needs the target's rows, which is why it happens
    # here rather than up with the export.
    if wanted_types and collision_prefix:
        renames, rename_warnings = source.plan_renames(
            src,
            src.lists_for(src.event_types),
            existing_choices,
            collision_prefix,
        )
        src.rename_lists(renames)
        export_warnings += rename_warnings

    actions, warnings = provision.plan(
        src=src,
        existing_choice_rows=existing_choices,
        selected_categories=selected,
        existing_categories=existing_categories,
        existing_types=existing_types,
        existing_choice_fields=existing_fields,
        prefix=prefix,
        species_list=species_list,
        activate=activate,
        replace_schema=replace_schema,
    )

    warnings = export_warnings + warnings

    # A supplied CSV replaces the rows of the standard list, keeping its name
    # so no $ref has to move.
    if csv_rows:
        for a in actions:
            if a.kind == "choice" and a.value == model.SPECIES_LIST:
                a.payload["rows"] = csv_rows
                break
        else:
            warnings.append(
                f"a species CSV was supplied but '{model.SPECIES_LIST}' is "
                "already on this instance, so it was not rewritten. Rename or "
                "deactivate the existing list first."
            )

    results = provision.apply(
        actions,
        _sender(client),
        dry_run=dry_run,
        existing_ids={
            str(t.get("value")): str(t.get("id")) for t in existing_types if t.get("id")
        },
    )

    rows = [
        {
            "WHAT": r.action.kind.replace("_", " "),
            "NAME": r.action.name,
            "VALUE": r.action.value,
            "STATE": r.outcome,
            "DETAIL": r.detail or r.action.detail,
        }
        for r in results
    ]

    if not rows:
        rows.append(
            {
                "WHAT": "nothing to do",
                "NAME": "",
                "VALUE": "",
                "STATE": "ok",
                "DETAIL": "every selected category, list and type is already present",
            }
        )

    # A stopped run is the normal response to a failure, not a crash -- say so
    # where the operator is looking, because the table alone just stops.
    if any(r.outcome == "failed" for r in results):
        done = sum(1 for r in results if r.outcome == "created")
        warnings.insert(
            0,
            (
                f"STOPPED after a failure. {done} of {len(actions)} writes "
                "completed. Nothing was rolled back -- fix the cause and run "
                "again; the plan is recomputed against what is now there, so "
                "completed work is skipped."
            ),
        )

    rows += [
        {"WHAT": "warning", "NAME": "", "VALUE": "", "STATE": "", "DETAIL": w}
        for w in warnings
    ]
    return pd.DataFrame(rows)
