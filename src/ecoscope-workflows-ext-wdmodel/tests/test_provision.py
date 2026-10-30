"""Tests for the planning logic.

No network. The instance is represented by the three lists the task reads --
categories, event types, choice fields -- so every shape a real instance can
present is a fixture here.
"""

import pytest
from ecoscope_workflows_ext_wdmodel import model, provision, source

ALL = model.category_values()


def plan(**kw):
    base = dict(
        selected_categories=ALL,
        existing_categories=[],
        existing_types=[],
        existing_choice_fields=[],
    )
    base.update(kw)
    return provision.plan(**base)


# --------------------------------------------------------------- the model ---


def test_four_categories():
    assert ALL == ["animal_health", "field_monitoring", "hwc", "rangeland_monitoring"]


def test_the_form_choices_match_the_model():
    """The Literal cannot be built from the model, so pin them together.

    `Category` has to list its members statically for rjsf to render choices.
    Add a category to the model file and forget this one and the form simply
    will not offer it -- silently, because an unoffered option looks like a
    design decision rather than a bug.
    """
    from typing import get_args

    assert sorted(get_args(model.Category)) == sorted(ALL)


def test_every_type_belongs_to_a_known_category():
    assert {t["category"] for t in model.event_types()} <= set(ALL)


def test_twenty_seven_types():
    assert len(model.event_types()) == 27


def test_every_referenced_list_has_rows():
    """A $ref with no rows behind it is an empty dropdown in the field."""
    for f in model.lists_for(model.event_types()):
        assert model.choices_for([f]), f"{f} is referenced but has no rows"


# ------------------------------------------------------------------ order ---


def test_creation_order_is_categories_choices_types_schemas():
    actions, _ = plan()
    seen = [a.kind for a in actions]
    first = {k: seen.index(k) for k in provision.KINDS if k in seen}
    assert first["category"] < first["choice"] < first["event_type"]
    assert first["event_type"] <= first["schema"]


def test_choice_lists_come_before_the_schemas_that_use_them():
    """The rule the whole package exists to enforce."""
    actions, _ = plan()
    last_choice = max(i for i, a in enumerate(actions) if a.kind == "choice")
    first_schema = min(i for i, a in enumerate(actions) if a.kind == "schema")
    assert last_choice < first_schema


# ------------------------------------------------------------- selection ---


def test_selecting_one_category_does_not_drag_in_the_others():
    ah = model.lists_for(model.event_types(["animal_health"]))
    everything = model.lists_for(model.event_types())
    assert ah < everything
    actions, _ = plan(selected_categories=["animal_health"])
    assert provision.summarise(actions)["event_type"] == 2


def test_unknown_category_is_refused():
    with pytest.raises(ValueError, match="not categories"):
        plan(selected_categories=["rangelands"])


def test_no_categories_selected_is_refused_by_the_task_not_here():
    actions, _ = plan(selected_categories=[])
    assert actions == []


# ----------------------------------------------------------- idempotency ---


def test_rerun_against_a_finished_instance_does_nothing():
    types = model.event_types(["animal_health"])
    actions, _ = plan(
        selected_categories=["animal_health"],
        existing_categories=[{"value": "animal_health"}],
        existing_types=[{"value": t["value"]} for t in types],
        existing_choice_fields=model.lists_for(types),
    )
    assert actions == []


def test_partial_instance_only_fills_the_gaps():
    types = model.event_types(["animal_health"])
    actions, _ = plan(
        selected_categories=["animal_health"],
        existing_categories=[{"value": "animal_health"}],
        existing_types=[{"value": types[0]["value"]}],
        existing_choice_fields=model.lists_for(types),
    )
    created = [a.value for a in actions if a.kind == "event_type"]
    assert created == [types[1]["value"]]


def test_existing_type_is_skipped_unless_replace_schema():
    types = model.event_types(["animal_health"])
    existing = [{"value": t["value"]} for t in types]
    actions, _ = plan(
        selected_categories=["animal_health"],
        existing_types=existing,
        replace_schema=True,
    )
    assert {a.kind for a in actions} >= {"schema"}
    assert not [a for a in actions if a.kind == "event_type"]


# --------------------------------------------------------------- prefix ---


def test_prefix_applies_to_event_types():
    actions, _ = plan(selected_categories=["animal_health"], prefix="trw_")
    assert all(a.value.startswith("trw_") for a in actions if a.kind == "event_type")


def test_prefix_does_not_apply_to_choice_lists():
    """Lists are shared across types; prefixing them would fork the model."""
    actions, _ = plan(selected_categories=["animal_health"], prefix="trw_")
    assert not any(a.value.startswith("trw_") for a in actions if a.kind == "choice")


# -------------------------------------------------------------- species ---


def test_species_repoint_skips_creating_the_standard_list():
    actions, _ = plan(
        selected_categories=["field_monitoring"],
        existing_choice_fields=["site_species"],
        species_list="site_species",
    )
    assert "species" not in [a.value for a in actions if a.kind == "choice"]


def test_species_repoint_warns_when_the_target_list_is_absent():
    _, warnings = plan(
        selected_categories=["field_monitoring"], species_list="not_there"
    )
    assert any("not a choice list on this instance" in w for w in warnings)


def test_repoint_does_not_mutate_the_cached_model():
    """The cache is process-wide; a leak makes one run change every later one."""
    before = model.lists_for(model.event_types(["field_monitoring"]))
    plan(
        selected_categories=["field_monitoring"],
        existing_choice_fields=["site_species"],
        species_list="site_species",
    )
    assert model.lists_for(model.event_types(["field_monitoring"])) == before


# -------------------------------------------------------------- activate ---


def test_inactive_by_default_and_says_so():
    actions, warnings = plan(selected_categories=["animal_health"])
    assert all(
        a.payload["is_active"] is False for a in actions if a.kind == "event_type"
    )
    assert any("invisible" in w for w in warnings)


def test_activate_sets_the_flag_and_drops_the_warning():
    actions, warnings = plan(selected_categories=["animal_health"], activate=True)
    assert all(
        a.payload["is_active"] is True for a in actions if a.kind == "event_type"
    )
    assert not any("invisible" in w for w in warnings)


# ----------------------------------------------------------------- traps ---


def test_no_choice_list_name_exceeds_the_column_width():
    """ER's choices.field is varchar(40); longer names fail with a 500."""
    long = [
        f for f in model.lists_for(model.event_types()) if len(f) > model.MAX_LIST_NAME
    ]
    assert not long, f"too long for varchar({model.MAX_LIST_NAME}): {long}"


# ------------------------------------------------------------ species CSV ---

GOOD_CSV = (
    "value,display,ordernum\n"
    "grevys_zebra,Grevy's Zebra,10\n"
    "reticulated_giraffe,Reticulated Giraffe,20\n"
)


def test_csv_parses():
    rows = model.parse_species_csv(GOOD_CSV)
    assert [r["value"] for r in rows] == ["grevys_zebra", "reticulated_giraffe"]
    assert rows[0]["display"] == "Grevy's Zebra"
    assert rows[0]["ordernum"] == 10


def test_csv_ordernum_is_optional():
    rows = model.parse_species_csv("value,display\nzebra,Zebra\n")
    assert rows[0]["ordernum"] is None


@pytest.mark.parametrize(
    "text,fragment",
    [
        ("value\nzebra\n", "missing required column"),
        ("value,display\n,Zebra\n", "'value' is empty"),
        ("value,display\nzebra,\n", "'display' is empty"),
        ("value,display\nGrevys Zebra,Zebra\n", "lowercase letters"),
        ("value,display\nzebra,Zebra\nzebra,Again\n", "duplicate value"),
        ("value,display,ordernum\nzebra,Zebra,ten\n", "not a whole number"),
        ("value,display\n", "no rows"),
    ],
)
def test_csv_is_refused_before_anything_is_written(text, fragment):
    """Validate the whole file first.

    A list half created because line 80 was malformed has to be found and
    cleaned up by hand -- choice rows have no transaction around them.
    """
    with pytest.raises(ValueError, match=fragment):
        model.parse_species_csv(text)


def test_csv_reports_the_line_number():
    with pytest.raises(ValueError, match="line 3"):
        model.parse_species_csv("value,display\nok,Fine\nBAD VALUE,Nope\n")


# ----------------------------------------------------------------- apply ---


def fake_send(log):
    def send(method, path, payload):
        log.append((method, path, payload.get("value") or payload.get("field")))
        return {"data": {"id": f"id{len(log)}"}}

    return send


def test_dry_run_writes_nothing():
    actions, _ = plan(selected_categories=["animal_health"])
    log = []
    results = provision.apply(actions, fake_send(log), dry_run=True)
    assert log == []
    assert {r.outcome for r in results} == {"planned"}


def test_apply_writes_in_dependency_order():
    actions, _ = plan(selected_categories=["animal_health"])
    log = []
    provision.apply(actions, fake_send(log), dry_run=False)
    paths = [p for _, p, _ in log]
    first_choice = min(i for i, p in enumerate(paths) if p == "choices")
    first_type = min(i for i, p in enumerate(paths) if "eventtypes" in p)
    assert first_choice < first_type, "choice lists must exist before the schemas"


def test_a_new_type_is_not_patched_twice():
    """v2 requires the schema in the CREATE body, so a follow-up PATCH is noise.

    ermigrate reported '10 failed' on a run where everything worked, because
    the redundant second call could not find an id.
    """
    actions, _ = plan(selected_categories=["animal_health"])
    log = []
    results = provision.apply(actions, fake_send(log), dry_run=False)
    assert not [m for m, _, _ in log if m == "PATCH"]
    assert all(r.outcome == "created" for r in results)


def _fake_instance():
    ref = "/api/v2.0/schemas/choices.json?field=%s"
    data = {
        "activity/events/categories": [
            {"value": "rhino_mgmt", "display": "Rhino Monitoring", "ordernum": 1}
        ],
        "activity/eventtypes": [
            {
                "value": "rhino_sighting",
                "display": "Rhino Sighting",
                "category": {"value": "rhino_mgmt"},
                "geometry_type": "Point",
                "schema": {
                    "json": {
                        "properties": {
                            "horn": {"anyOf": [{"$ref": ref % "horn_status"}]}
                        }
                    },
                    "ui": {},
                },
            }
        ],
        "activity/events/eventtypes": [
            {"value": "legacy_form", "category": {"value": "rhino_mgmt"}}
        ],
        "choices": [
            {"field": "horn_status", "value": "both"},
            {"field": "horn_status", "value": "one"},
        ],
    }

    def read(path, params=None):
        if path == "choices":
            f = (params or {}).get("field")
            return [r for r in data["choices"] if r["field"] == f]
        return data[path]

    return read


def test_copy_reads_only_the_selected_categories():
    src, _ = source.export_from(_fake_instance(), ["rhino_mgmt"], "src")
    assert src.category_values() == ["rhino_mgmt"]
    assert [t["value"] for t in src.event_types] == ["rhino_sighting"]


def test_copy_normalises_category_to_the_shipped_shape():
    """ER nests it; the shipped file does not. The planner must not care."""
    src, _ = source.export_from(_fake_instance(), ["rhino_mgmt"], "src")
    assert src.event_types[0]["category"] == "rhino_mgmt"


def test_copy_reports_v1_only_types_rather_than_dropping_them():
    _, warnings = source.export_from(_fake_instance(), ["rhino_mgmt"], "src")
    assert any("v1 only" in w and "legacy_form" in w for w in warnings)


def test_copy_refuses_a_category_the_source_lacks():
    with pytest.raises(ValueError, match="not categories on the source"):
        source.export_from(_fake_instance(), ["nope"], "src")


def test_copied_model_plans_like_the_shipped_one():
    src, _ = source.export_from(_fake_instance(), ["rhino_mgmt"], "src")
    actions, _ = provision.plan(
        src=src,
        selected_categories=src.category_values(),
        existing_categories=[],
        existing_types=[],
        existing_choice_fields=[],
        existing_choice_rows=[],
    )
    assert [a.kind for a in actions] == ["category", "choice", "event_type", "schema"]


def test_a_same_named_list_with_different_options_is_flagged():
    """The Left Tusk failure. Skipping is right; saying nothing is not."""
    src, _ = source.export_from(_fake_instance(), ["rhino_mgmt"], "src")
    _, warnings = provision.plan(
        src=src,
        selected_categories=src.category_values(),
        existing_categories=[],
        existing_types=[],
        existing_choice_fields=["horn_status"],
        existing_choice_rows=[{"field": "horn_status", "value": "intact"}],
    )
    assert any("different options" in w for w in warnings)


def test_copied_types_inherit_their_source_category_by_default():
    src, _ = source.export_from(_fake_instance(), ["rhino_mgmt"], "src")
    chosen = src.types_named(["rhino_sighting"])
    assert src.categories_of(chosen) == ["rhino_mgmt"]


def test_recategorise_reproduces_the_westgate_to_mmnr_move():
    """Westgate's types lived in field_monitoring_2 and became field_monitoring.

    That name is an accident of Westgate's own permissions history. Inheriting
    it would have carried the accident into every instance built from it.
    """
    src, _ = source.export_from(_fake_instance(), ["rhino_mgmt"], "src")
    chosen = src.types_named(["rhino_sighting"])
    src.event_types = chosen
    src.recategorise(chosen, "field_monitoring")

    assert {t["category"] for t in chosen} == {"field_monitoring"}
    assert src.categories_of(chosen) == ["field_monitoring"]
    assert src.display_of("field_monitoring") == "Field Monitoring"

    actions, _ = provision.plan(
        src=src,
        selected_categories=src.categories_of(chosen),
        existing_categories=[],
        existing_types=[],
        existing_choice_fields=[],
        existing_choice_rows=[],
    )
    created = [a.value for a in actions if a.kind == "category"]
    assert created == ["field_monitoring"]
    assert "rhino_mgmt" not in created


def test_recategorise_into_a_category_the_target_already_has():
    src, _ = source.export_from(_fake_instance(), ["rhino_mgmt"], "src")
    chosen = src.types_named(["rhino_sighting"])
    src.event_types = chosen
    src.recategorise(chosen, "field_monitoring")
    actions, _ = provision.plan(
        src=src,
        selected_categories=src.categories_of(chosen),
        existing_categories=[{"value": "field_monitoring"}],
        existing_types=[],
        existing_choice_fields=[],
        existing_choice_rows=[],
    )
    assert not [a for a in actions if a.kind == "category"]


def _clashing_target():
    """A target where one list differs and one matches."""
    return [{"field": "horn_status", "value": "intact"}]


def test_only_clashing_lists_are_renamed():
    """A matching list is shared. Renaming everything would give each
    instance a private vocabulary and defeat the comparability the whole
    standard model exists for."""
    src, _ = source.export_from(_fake_instance(), ["rhino_mgmt"], "src")
    needed = src.lists_for(src.event_types)
    same = [{"field": "horn_status", "value": v} for v in ("both", "one")]
    mapping, _ = source.plan_renames(src, needed, same, "fm_")
    assert mapping == {}


def test_a_clashing_list_is_renamed_and_its_refs_move_with_it():
    src, _ = source.export_from(_fake_instance(), ["rhino_mgmt"], "src")
    needed = src.lists_for(src.event_types)
    mapping, _ = source.plan_renames(src, needed, _clashing_target(), "fm_")
    assert mapping == {"horn_status": "fm_horn_status"}

    src.rename_lists(mapping)
    # both halves: the schema refs AND the rows
    assert src.lists_for(src.event_types) == {"fm_horn_status"}
    assert {c["field"] for c in src.choices} == {"fm_horn_status"}


def test_renaming_resolves_the_collision_warning():
    src, _ = source.export_from(_fake_instance(), ["rhino_mgmt"], "src")
    target = _clashing_target()
    mapping, _ = source.plan_renames(src, src.lists_for(src.event_types), target, "fm_")
    src.rename_lists(mapping)
    _, warnings = provision.plan(
        src=src,
        selected_categories=src.category_values(),
        existing_categories=[],
        existing_types=[],
        existing_choice_fields={r["field"] for r in target},
        existing_choice_rows=target,
    )
    assert not [w for w in warnings if "different options" in w]


def test_rename_is_refused_when_the_new_name_is_also_taken():
    """Half a rename is worse than none: the schema would point one way and
    the rows be written another."""
    src, _ = source.export_from(_fake_instance(), ["rhino_mgmt"], "src")
    target = _clashing_target() + [{"field": "fm_horn_status", "value": "x"}]
    mapping, warnings = source.plan_renames(
        src, src.lists_for(src.event_types), target, "fm_"
    )
    assert mapping == {}
    assert any("already taken" in w for w in warnings)


def test_rename_is_refused_when_it_would_exceed_the_column_width():
    src, _ = source.export_from(_fake_instance(), ["rhino_mgmt"], "src")
    mapping, warnings = source.plan_renames(
        src, src.lists_for(src.event_types), _clashing_target(), "x" * 40 + "_"
    )
    assert mapping == {}
    assert any("varchar" in w for w in warnings)


def test_rename_prefix_charset_is_enforced():
    src, _ = source.export_from(_fake_instance(), ["rhino_mgmt"], "src")
    with pytest.raises(ValueError, match="lowercase"):
        source.plan_renames(
            src, src.lists_for(src.event_types), _clashing_target(), "FM-"
        )


def test_an_identical_list_is_not_flagged():
    src, _ = source.export_from(_fake_instance(), ["rhino_mgmt"], "src")
    same = [{"field": "horn_status", "value": v} for v in ("both", "one")]
    _, warnings = provision.plan(
        src=src,
        selected_categories=src.category_values(),
        existing_categories=[],
        existing_types=[],
        existing_choice_fields=["horn_status"],
        existing_choice_rows=same,
    )
    assert not [w for w in warnings if "different options" in w]


def test_apply_stops_at_the_first_failure():
    """Carrying on would report 'created' for things whose deps never landed."""
    actions, _ = plan(selected_categories=["animal_health"])
    calls = {"n": 0}

    def flaky(method, path, payload):
        calls["n"] += 1
        if calls["n"] == 5:
            raise RuntimeError("500 duplicate key")
        return {"id": "x"}

    results = provision.apply(actions, flaky, dry_run=False)
    assert results[-1].outcome == "failed"
    assert len(results) < len(actions)
    assert "500 duplicate key" in results[-1].detail
