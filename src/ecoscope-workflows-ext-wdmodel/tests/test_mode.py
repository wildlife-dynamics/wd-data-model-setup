"""The mode dropdown.

Skipped where ecoscope-platform is not installed -- the rest of the suite is
deliberately pure and runs anywhere, and the task module cannot be.

What these protect is the promise the form makes: on a standard run the
second data source is cosmetic. The app asks for it every time, so a standard
run always arrives holding a live client for some instance. If anything in
the task read that client, or inferred intent from the copy fields, a stray
selection would silently turn a setup into a copy -- against an instance the
operator only picked to get past the wizard.
"""

import pytest

pytest.importorskip("ecoscope.platform.connections")

from ecoscope_workflows_ext_wdmodel.tasks.setup._apply import (  # noqa: E402
    COPY,
    STANDARD,
    apply_data_model,
)


class Exploding:
    """A copy source that fails the test if it is touched at all."""

    def __getattr__(self, name):
        raise AssertionError(
            f"the copy source was read ({name!r}) on a standard-model run"
        )


class Recording:
    """Target double: answers the three reads the planner makes, records writes."""

    def __init__(self):
        self.writes = []

    def _get(self, path, params=None):
        return []

    def _post(self, path, payload):
        self.writes.append(("POST", path))
        return {"id": "x"}

    def _patch(self, path, payload):
        self.writes.append(("PATCH", path))
        return {"id": "x"}


def test_standard_mode_never_touches_the_source():
    df = apply_data_model(
        client=Recording(),
        copy_from=Exploding(),
        mode=STANDARD,
        categories=["animal_health"],
        dry_run=True,
    )
    assert not df.empty


def test_standard_mode_ignores_copy_fields_that_were_filled_in():
    """Left over from an earlier run, or clicked by mistake. Either way the
    dropdown decides, not the fields."""
    df = apply_data_model(
        client=Recording(),
        copy_from=Exploding(),
        mode=STANDARD,
        categories=["animal_health"],
        copy_event_types=["wildlife_sighting"],
        copy_into_category="field_monitoring",
        collision_prefix="fm_",
        dry_run=True,
    )
    assert set(df["WHAT"]) <= {"category", "choice", "event type", "schema", "warning"}
    assert "wildlife_sighting" not in set(df["VALUE"])


def test_copy_mode_with_no_event_types_says_so():
    with pytest.raises(ValueError, match="no event types were chosen"):
        apply_data_model(
            client=Recording(),
            copy_from=Recording(),
            mode=COPY,
            dry_run=True,
        )


def test_copy_mode_with_no_source_says_so():
    with pytest.raises(ValueError, match="no source instance"):
        apply_data_model(
            client=Recording(),
            copy_from=None,
            mode=COPY,
            copy_event_types=["wildlife_sighting"],
            dry_run=True,
        )


def test_copy_mode_drops_the_species_fields_and_says_it_did():
    """Repointing a copied form's species field at a list chosen for the
    standard model would change what the copy means without saying so."""
    df = apply_data_model(
        client=Recording(),
        copy_from=Recording(),
        mode=COPY,
        copy_event_types=["anything"],
        species_list="wildlifesightingrep_species",
        dry_run=True,
    )
    assert any("was ignored" in d for d in df["DETAIL"])


def test_the_default_is_the_standard_model():
    """Submitting the untouched form must not copy."""
    import inspect

    assert inspect.signature(apply_data_model).parameters["mode"].default == STANDARD
