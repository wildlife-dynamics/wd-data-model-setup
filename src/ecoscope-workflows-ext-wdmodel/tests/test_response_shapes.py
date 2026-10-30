"""List endpoints vs detail endpoints.

The bug these exist for: a detail route was read with the LIST reader, which
ends in `list(payload)`. On a dict that yields its KEYS -- a list of strings
that looks enough like records to travel a long way. The schema then came
back missing and a perfectly ordinary v2 event type was reported as "most
likely a v1 type", which is a wrong answer delivered confidently.

So both readers are pinned against every response shape erclient produces,
and `fetch_schemas` is checked against a reader of each kind.
"""

import pytest

pytest.importorskip("ecoscope.platform.connections")

from ecoscope_workflows_ext_wdmodel import source  # noqa: E402
from ecoscope_workflows_ext_wdmodel.tasks.setup import _apply  # noqa: E402

V2_SCHEMA = {"json": {"properties": {"a": {}}}, "ui": {}}


class Client:
    def __init__(self, payload):
        self.service_root = "https://x.pamdas.org/api/v1.0"
        self.payload = payload

    def _get(self, path, params=None):
        return self.payload


# erclient unwraps "data" for most responses but not all, so both arrive.
WRAPPED = {"data": {"id": "1", "value": "sick_injured_animal", "schema": V2_SCHEMA}}
BARE = WRAPPED["data"]
LIST_WRAPPED = {"data": [{"value": "a"}, {"value": "b"}]}
LIST_BARE = LIST_WRAPPED["data"]


@pytest.mark.parametrize("payload", [WRAPPED, BARE])
def test_read_one_returns_the_record(payload):
    got = _apply._read_one(Client(payload), "activity/eventtypes/1/")
    assert got["value"] == "sick_injured_animal"
    assert got["schema"] == V2_SCHEMA


@pytest.mark.parametrize("payload", [LIST_WRAPPED, LIST_BARE])
def test_read_returns_the_records(payload):
    got = _apply._read(Client(payload), "activity/eventtypes")
    assert [r["value"] for r in got] == ["a", "b"]


def test_read_never_returns_dict_keys():
    """The actual failure. A single record through the list reader used to
    come back as ['id', 'schema', 'value']."""
    got = _apply._read(Client(BARE), "activity/eventtypes/1/")
    assert got == [BARE]
    assert all(isinstance(r, dict) for r in got)


def test_read_one_survives_a_list():
    assert _apply._read_one(Client(LIST_BARE), "x")["value"] == "a"


def test_empty_responses():
    assert _apply._read(Client(None), "x") == []
    assert _apply._read_one(Client(None), "x") == {}


def test_fetch_schemas_fills_them_in():
    types = [{"id": "1", "value": "sick_injured_animal"}]
    warnings = source.fetch_schemas(lambda path, params=None: BARE, types)
    assert warnings == []
    assert types[0]["schema"] == V2_SCHEMA


def test_fetch_schemas_accepts_a_bare_json_document():
    """Some instances answer with the json document rather than the
    {json, ui} wrapper. Discarding that would drop a real schema."""
    types = [{"id": "1", "value": "x"}]
    source.fetch_schemas(
        lambda p, params=None: {"schema": {"properties": {"a": {}}}}, types
    )
    assert types[0]["schema"]["json"]["properties"] == {"a": {}}


def test_fetch_schemas_says_what_it_actually_got():
    """A warning that only says 'no v2 schema' cannot be told apart from a
    parsing mistake -- which is how the last one hid."""
    types = [{"id": "1", "value": "x"}]
    warnings = source.fetch_schemas(
        lambda p, params=None: {"id": "1", "value": "x"}, types
    )
    assert "keys" in warnings[0] and "value" in warnings[0]


def test_fetch_schemas_handles_a_type_with_no_id():
    types = [{"value": "x"}]
    warnings = source.fetch_schemas(lambda p, params=None: {}, types)
    assert "no id" in warnings[0]
    assert types[0]["schema"] == {}
