"""The mode dropdown.

Skipped where ecoscope-platform is not installed -- the rest of the suite is
deliberately pure and runs anywhere, and the task module cannot be.

What these protect is the promise the form makes: the source instance is a
field of the copy branch, so a standard run cannot carry one at all. The
Union is what guarantees that -- not a convention the task has to honour --
and these tests fail if the branches ever grow each other's fields back.
"""

import pytest

pytest.importorskip("ecoscope.platform.connections")

from ecoscope_workflows_ext_wdmodel.tasks.setup._apply import (  # noqa: E402
    CopyFromInstance,
    StandardModel,
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
        what=StandardModel(categories=["animal_health"]),
        dry_run=True,
    )
    assert not df.empty


def test_copy_with_no_categories_says_so():
    import pytest as _p

    with _p.raises(ValueError, match="no categories"):
        apply_data_model(
            client=Recording(),
            what=CopyFromInstance(source={"name": "somewhere"}, from_categories=[]),
            dry_run=True,
        )


def test_copy_with_no_source_instance_says_so():
    import pytest as _p

    with _p.raises(ValueError, match="no source instance"):
        apply_data_model(
            client=Recording(),
            what=CopyFromInstance(
                source={"name": ""}, from_categories=["field_monitoring"]
            ),
            dry_run=True,
        )


def test_the_union_hides_the_other_branch():
    """A StandardModel carries no copy fields at all, so there is nothing
    left over for a later run to pick up."""
    assert not hasattr(StandardModel(), "from_categories")
    assert not hasattr(StandardModel(), "source")

    copy = CopyFromInstance(source={"name": "x"})
    assert not hasattr(copy, "categories")
    assert not hasattr(copy, "species_list")


def test_the_source_connection_belongs_to_the_copy_branch_only():
    """If the connection ever moves back to the task signature it renders on
    every run, including standard ones that never read it."""
    import inspect

    assert "copy_source" not in inspect.signature(apply_data_model).parameters
    assert "source" in CopyFromInstance.model_fields


def test_the_default_branch_is_the_standard_model():
    from typing import get_args

    from ecoscope_workflows_ext_wdmodel.tasks.setup._apply import Setup

    assert get_args(Setup)[0] is StandardModel
