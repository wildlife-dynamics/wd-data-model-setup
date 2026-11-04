"""The species choice on a copy run.

A copied form points at whatever the source called its species list. Giving
the operator a choice means a rename AND a $ref rewrite, together -- the half
that gets forgotten is the $refs, and forgetting it binds the form to
whichever list happens to carry the old name on the target. That is the
failure these pin down, because it does not error: the dropdown just comes up
empty, or worse, full of somebody else's values.
"""

import pytest
from ecoscope_workflows_ext_wdmodel import model, source
from ecoscope_workflows_ext_wdmodel.source import apply_species_choice


def _ref(name):
    return {"$ref": f"#/choices?field={name}&foo=1"}


def _src(list_name="wildlifesightingrep_species", extra=()):
    t = {
        "value": "wildlife_sighting",
        "display": "Wildlife Sighting",
        "category": {"value": "field_monitoring"},
        "schema": {"properties": {"species": _ref(list_name)}},
    }
    for i, n in enumerate(extra):
        t["schema"]["properties"][f"x{i}"] = _ref(n)
    rows = [{"field": list_name, "value": "lion", "display": "Lion"}]
    for n in extra:
        rows.append({"field": n, "value": "cow", "display": "Cow"})
    return source.Source(categories=[], event_types=[t], choices=rows)


def _refs_of(src):
    return model.refs_in(src.event_types[0]["schema"])


# ---------------------------------------------------------------- source ---


def test_source_mode_changes_nothing():
    src = _src()
    assert apply_species_choice(src, src.event_types, "source", []) == []
    assert _refs_of(src) == {"wildlifesightingrep_species"}


# -------------------------------------------------------------- standard ---


def test_standard_moves_the_rows_and_the_refs_together():
    src = _src()
    notes = apply_species_choice(src, src.event_types, "standard", [])

    assert _refs_of(src) == {model.SPECIES_LIST}, "the $ref did not move"
    fields = {c["field"] for c in src.choices}
    assert model.SPECIES_LIST in fields
    assert "wildlifesightingrep_species" not in fields, "the old list survived"
    assert any("repointed" in n for n in notes)


def test_standard_uses_the_shipped_rows_not_the_sources():
    src = _src()
    apply_species_choice(src, src.event_types, "standard", [])
    values = {c["value"] for c in src.choices if c["field"] == model.SPECIES_LIST}
    assert "lion" not in values or len(values) > 1
    assert values == {
        c["value"] for c in model.choices_for([model.SPECIES_LIST])
    }, "the standard list should replace the source's rows outright"


# ------------------------------------------------------------------- csv ---


def test_csv_rows_win_over_the_standard_list():
    src = _src()
    rows = [{"value": "grevys_zebra", "display": "Grevy's Zebra"}]
    apply_species_choice(src, src.event_types, "csv", rows)

    got = [c for c in src.choices if c["field"] == model.SPECIES_LIST]
    assert [c["value"] for c in got] == ["grevys_zebra"]
    assert _refs_of(src) == {model.SPECIES_LIST}


# ------------------------------------------------------- what is left alone ---


def test_purpose_specific_species_lists_are_not_merged_in():
    """Livestock species is not the species list. Merging it would put
    elephants in a livestock dropdown and cattle in a sightings one."""
    src = _src(extra=["livestock_species", "species_of_vulture_at_carcass"])
    notes = apply_species_choice(src, src.event_types, "standard", [])

    refs = _refs_of(src)
    assert "livestock_species" in refs
    assert "species_of_vulture_at_carcass" in refs
    assert model.SPECIES_LIST in refs
    declined = [n for n in notes if "purpose-specific" in n]
    assert len(declined) == 2, "both should be reported, not silently skipped"


def test_nothing_to_repoint_is_reported_rather_than_silent():
    src = source.Source(
        categories=[],
        event_types=[{"value": "arrest", "schema": {"properties": {}}}],
        choices=[],
    )
    notes = apply_species_choice(src, src.event_types, "standard", [])
    assert any("none of the copied forms reference" in n for n in notes)


def test_merging_two_species_lists_warns():
    src = _src(extra=["species_2"])
    notes = apply_species_choice(src, src.event_types, "standard", [])
    assert _refs_of(src) == {model.SPECIES_LIST}
    assert any("merged" in n for n in notes)


# -------------------------------------------------------------- detection ---


@pytest.mark.parametrize(
    "name,is_general",
    [
        ("species", True),
        ("species_2", True),
        ("wildlifesightingrep_species", True),
        ("livestock_species", False),
        ("livestock_species_2", False),
        ("species_of_vulture_at_carcass", False),
        ("alien_plant_species", False),
        ("hwc_species", False),
        ("action_taken", False),
    ],
)
def test_general_species_detection(name, is_general):
    assert (name in model.general_species_lists([name])) is is_general
