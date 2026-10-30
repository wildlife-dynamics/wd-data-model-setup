"""Which API root each call goes to.

This is the bug that cost a run. Event types are a v2 resource under
/api/v2.0; categories and choice lists are v1. erclient is built with the
v1.0 root and joins relative paths onto it, so `activity/eventtypes` reached
/api/v1.0/activity/eventtypes, the server said 404, and erclient raised a
bare `ERClientNotFound('')` with no path in the message. Nothing in the
traceback named the URL.

So the routing is asserted directly, on recorded URLs.
"""

import pytest

pytest.importorskip("ecoscope.platform.connections")

from ecoscope_workflows_ext_wdmodel.tasks.setup import _apply  # noqa: E402


class FakeClient:
    """Records the URL each call would actually reach."""

    def __init__(self, root="https://example.pamdas.org/api/v1.0"):
        self.service_root = root
        self.urls = []

    def _url(self, path):
        return "/".join((self.service_root, path))

    def _get(self, path, params=None):
        self.urls.append(("GET", self._url(path)))
        return []

    def _post(self, path, payload):
        self.urls.append(("POST", self._url(path)))
        return {"id": "x"}

    def _patch(self, path, payload):
        self.urls.append(("PATCH", self._url(path)))
        return {"id": "x"}


def test_event_types_go_to_v2():
    c = FakeClient()
    _apply._read(c, "activity/eventtypes", {"include_inactive": "true"})
    assert c.urls == [
        ("GET", "https://example.pamdas.org/api/v2.0/activity/eventtypes")
    ]


def test_event_type_detail_goes_to_v2():
    c = FakeClient()
    _apply._read(c, "activity/eventtypes/abc/", {"include_schema": "true"})
    assert "/api/v2.0/activity/eventtypes/abc/" in c.urls[0][1]


def test_categories_and_choices_stay_on_v1():
    c = FakeClient()
    _apply._read(c, "activity/events/categories")
    _apply._read(c, "choices")
    assert all("/api/v1.0/" in u for _, u in c.urls), c.urls


def test_writes_are_routed_too():
    """_post and _patch always join through _er_url, so a full URL is not an
    escape hatch -- the root has to be swapped for the call."""
    c = FakeClient()
    send = _apply._sender(c)
    send("POST", "activity/eventtypes", {})
    send("PATCH", "activity/eventtypes/abc/", {})
    send("POST", "choices", {})
    send("POST", "activity/events/categories", {})
    roots = [u.split("/activity")[0].split("/choices")[0] for _, u in c.urls]
    assert roots == [
        "https://example.pamdas.org/api/v2.0",
        "https://example.pamdas.org/api/v2.0",
        "https://example.pamdas.org/api/v1.0",
        "https://example.pamdas.org/api/v1.0",
    ]


def test_the_root_is_restored_after_every_call():
    """A swap that leaked would send every later v1 call to v2."""
    c = FakeClient()
    _apply._read(c, "activity/eventtypes")
    assert c.service_root == "https://example.pamdas.org/api/v1.0"


def test_the_root_is_restored_even_when_the_call_raises():
    class Boom(FakeClient):
        def _get(self, path, params=None):
            raise RuntimeError("500")

    c = Boom()
    with pytest.raises(RuntimeError):
        _apply._read(c, "activity/eventtypes")
    assert c.service_root == "https://example.pamdas.org/api/v1.0"


def test_an_unexpected_root_is_left_alone():
    """Better to send the call and get a legible 404 than to rewrite a root
    this code does not recognise."""
    c = FakeClient(root="https://example.pamdas.org/api/v3.0")
    _apply._read(c, "activity/eventtypes")
    assert "/api/v3.0/" in c.urls[0][1]
