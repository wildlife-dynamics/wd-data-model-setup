"""Create the model on the target instance.

The only task in this package that writes. Dry run is on by default and has to
be turned off deliberately, because EarthRanger has no undo: a category cannot
be safely deleted, an event type that has taken a single record cannot be
removed, and a choice row written in error has to be found and deactivated by
hand.
"""

from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Any, Literal, Union

import pandas as pd
from ecoscope.platform import connections
from ecoscope.platform.annotations import AdvancedField, AnyDataFrame
from ecoscope.platform.connections import EarthRangerClient
from ecoscope.platform.tasks.io._set_connection import EarthRangerConnection
from pydantic import BaseModel, ConfigDict, Field
from wt_registry import register

from ... import model, provision, source

# ---------------------------------------------------------------- the modes
#
# A Union of models, not an enum. RJSF renders a Union of BaseModels as a
# oneOf with a picker, and shows ONLY the selected branch's fields -- so the
# copy fields genuinely disappear on a standard run. `model_config`'s title
# is what the picker displays.
#
# This replaces an earlier `mode` enum whose fields were all visible at once,
# and an attempt before that to hide them with an RJSF `dependencies` block,
# which broke the event-type picker. The pattern is lifted from
# save-the-elephants' select_map_overlay, where it is in production.


class StandardModel(BaseModel):
    """Create the WD standard model from the categories chosen here."""

    model_config = ConfigDict(title="Set up the WD standard model")

    categories: Annotated[
        list[model.Category],
        Field(
            default_factory=lambda: list(model.category_values()),
            title=" ",
            description=(
                "Which parts of the standard model to set up. Leave all "
                "selected for the whole thing; Rangeland Monitoring is the "
                "one most sites leave out."
            ),
            json_schema_extra={"uniqueItems": True},
        ),
    ]
    species_list: Annotated[
        str,
        Field(
            default="",
            title="Use a species list already on this instance",
            description=(
                "Leave empty to create the standard 66-entry species list. To "
                "use a list this instance already has, name it here and every "
                "species field is repointed at it instead of a second list "
                "being created."
            ),
        ),
    ] = ""
    species_csv: Annotated[
        str,
        Field(
            default="",
            title="Or load species from a CSV file",
            description=(
                "Path to a CSV of species to create instead of the standard "
                "list. Needs a header row and the columns value,display with "
                "an optional ordernum -- for example: "
                "grevys_zebra,Grevy's Zebra,10 . 'value' is stored on every "
                "record and is matched by the form's conditionals, so it must "
                "be lowercase letters, digits and underscores, and it can "
                "never be changed once data exists. The whole file is checked "
                "before anything is written."
            ),
        ),
    ] = ""


class CopyFromInstance(BaseModel):
    """Bring event types across from another EarthRanger instance."""

    model_config = ConfigDict(title="Copy event types from another instance")

    source: Annotated[
        EarthRangerConnection,
        Field(
            title="Instance to copy from",
            description=(
                "The instance the event types are read from. Only ever "
                "read, never written to."
            ),
        ),
    ]
    from_categories: Annotated[
        list[str],
        Field(
            default_factory=list,
            title="Categories to copy (type one value per row)",
            description=(
                "Event CATEGORY values as they are on the source, e.g. "
                "'field_monitoring' -- not the display names. Every v2 event "
                "type in them comes across, with its choice lists. "
                "Categories rather than individual types because a whole "
                "model is two or three values rather than twenty-seven. "
                "There is no dropdown: Desktop cannot list options from a "
                "connection that sits inside a choice like this one. A dry "
                "run checks each value against the source and names the near "
                "misses for anything it cannot find, so run one first."
            ),
            json_schema_extra={"uniqueItems": True},
        ),
    ]
    species: Annotated[
        Literal["source", "standard", "csv"],
        Field(
            default="source",
            title="Species list for the copied forms",
            description=(
                "'source' keeps whatever species list the copied forms "
                "already use. 'standard' repoints them at the WD standard "
                "66-entry list. 'csv' repoints them at a list built from a "
                "file of your own. Only the GENERAL species list is moved -- "
                "purpose-specific ones such as livestock or vulture species "
                "are left alone, and every list picked or declined is "
                "reported as a row."
            ),
        ),
    ] = "source"
    species_csv: Annotated[
        str,
        Field(
            default="",
            title="Species CSV (only read when 'csv' is chosen above)",
            description=(
                "Path to a CSV with value, display and an optional ordernum "
                "column. Validated in full before anything is written."
            ),
        ),
    ] = ""
    into_category: Annotated[
        str,
        Field(
            default="",
            title="Put them all in this category (blank = keep the source's)",
            description=(
                "Leave empty to keep each type in the category it has on the "
                "source. Set it to file everything under one category "
                "instead. Lowercase letters, digits and underscores; it is "
                "created if it is not already there."
            ),
        ),
    ] = ""
    collision_prefix: Annotated[
        str,
        Field(
            default="",
            title="Prefix for clashing choice lists (e.g. fm_)",
            description=(
                "If a choice list arriving from the source has the same name "
                "as one already on the target but different options, give the "
                "incoming one this prefix. Only clashing lists are renamed; "
                "ones that already match are shared. Leave empty to skip them "
                "instead, in which case the forms bind to the target's "
                "version and any rule keyed on a missing value silently never "
                "fires."
            ),
        ),
    ] = ""


Setup = Union[StandardModel, CopyFromInstance]


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
    what: Annotated[
        Setup,
        Field(
            title="What this run should do",
            description=(
                "Create the WD standard model, or copy event types from "
                "another instance. The fields shown change with the choice, "
                "and only those are read."
            ),
        ),
    ],
    dry_run: Annotated[
        bool,
        Field(
            default=True,
            title="Dry run - create nothing",
            description=(
                "Leave ON to create nothing and just list what is missing. "
                "Turn it off to write. There is no undo in EarthRanger: a "
                "category cannot be safely deleted and an event type that has "
                "taken one record cannot be removed."
            ),
        ),
    ] = True,
    activate: Annotated[
        bool,
        Field(
            default=False,
            title="Activate the event types immediately",
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
    prefix: Annotated[
        str,
        AdvancedField(
            default="",
            title="Event type prefix (blank for a real build)",
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
            title="Replace schemas that already exist",
            description=(
                "Also rewrite the schema of event types that already exist. "
                "Off by default: it would replace a live form, possibly one "
                "somebody else built."
            ),
        ),
    ] = False,
) -> Annotated[AnyDataFrame, Field(description="One row per write.")]:
    """Create the selected categories, choice lists, event types and schemas."""
    # Two sources, one planner: the model shipped in this package, or one read
    # off another instance. Which branch of the Union arrived decides it, and
    # nothing else -- not whether the copy fields happen to be filled.
    export_warnings: list[str] = []
    copying = isinstance(what, CopyFromInstance)

    # A StandardModel has no copy fields and no source connection at all, so
    # there is nothing a stray earlier selection could leave behind.
    if copying:
        wanted_cats = [c.strip() for c in (what.from_categories or []) if c.strip()]
        copy_into_category = what.into_category
        collision_prefix = what.collision_prefix
        categories, species_list = [], ""
        species_mode, species_csv = what.species, what.species_csv
    else:
        wanted_cats, copy_into_category, collision_prefix = [], "", ""
        categories = list(what.categories or [])
        species_mode = "source"
        species_list, species_csv = what.species_list, what.species_csv

    if species_list and species_csv:
        raise ValueError(
            "choose one species source: either name a list already on the "
            "instance, or supply a CSV -- not both."
        )
    if species_mode == "csv" and not species_csv:
        raise ValueError(
            "the species list was set to 'csv' but no CSV was given. Supply "
            "a path, or set it back to 'source' or 'standard'."
        )
    if copying and species_mode != "csv" and species_csv:
        raise ValueError(
            f"a species CSV was given but the species list is set to "
            f"{species_mode!r}, so it would be ignored. Set it to 'csv', or "
            "clear the path."
        )

    # Parse the CSV before reading the instance, so a malformed file costs
    # nothing and fails with a line number rather than part way through.
    csv_rows: list[dict[str, Any]] = []
    if species_csv:
        path = Path(species_csv).expanduser()
        if not path.is_file():
            raise ValueError(f"no species CSV at {path}")
        csv_rows = model.parse_species_csv(path.read_text())

    if copying:
        source_name = (getattr(what.source, "name", "") or "").strip()
        if not source_name:
            raise ValueError(
                "copying was chosen but no source instance was given. Pick "
                "one under 'Instance to copy from'."
            )
        if not wanted_cats:
            raise ValueError(
                "copying was chosen but no categories were. Type at least "
                "one of the source's event category values under 'Categories "
                "to copy'."
            )
        # The connection NAME is what the form hands over; the credentials
        # come from the environment Desktop sets up. This $ref lives inside
        # $defs/CopyFromInstance, below the two-level scan in
        # metadata.get_data_connection_property_names() -- but that is not
        # what registers a connection. Desktop's form layer recurses through
        # $ref, properties, items and anyOf/oneOf, so a nested one is found.
        # See the note in spec.yaml.
        try:
            copy_from = connections.EarthRangerConnection.client_from_named_connection(
                source_name
            )
        except Exception as exc:  # noqa: BLE001 - surface the cause, do not mask it
            raise ValueError(
                f"could not open the source instance {source_name!r}: {exc}. "
                "Check it is saved under Data Sources and the credentials "
                "are right."
            ) from exc

        read = lambda path, params=None: _read(copy_from, path, params)  # noqa: E731
        read_one = lambda path, params=None: _read_one(copy_from, path, params)  # noqa: E731
        src, export_warnings = source.export_everything(read, "the source instance")
        chosen = src.types_in(wanted_cats)
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
        export_warnings += source.apply_species_choice(
            src, chosen, species_mode, csv_rows
        )
    else:
        src = source.Source.shipped()
        selected = list(categories or [])
        if not selected:
            raise ValueError(
                "no categories selected. Choose at least one of: "
                + ", ".join(model.category_values())
            )

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
    if copying and collision_prefix:
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
    if csv_rows and not copying:
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
