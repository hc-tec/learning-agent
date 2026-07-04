import types
import unittest
from unittest.mock import patch

from flask import Flask

from flaskr.api.langfuse import (
    MockClient,
    build_langfuse_observation_link,
    get_request_trace_id,
    resolve_langfuse_trace_id,
)
from flaskr.common.log import thread_local


class RequestTraceIdTests(unittest.TestCase):
    def tearDown(self):
        for attr in ("request_id",):
            if hasattr(thread_local, attr):
                delattr(thread_local, attr)

    def test_prefers_thread_local_request_id(self):
        app = Flask("langfuse-thread-local")
        thread_local.request_id = "thread-local-request-id"

        with app.test_request_context(headers={"X-Request-ID": "header-request-id"}):
            self.assertEqual(get_request_trace_id(), "thread-local-request-id")

    def test_falls_back_to_request_header(self):
        if hasattr(thread_local, "request_id"):
            delattr(thread_local, "request_id")
        fake_request = types.SimpleNamespace(
            headers={"X-Request-ID": "header-request-id"}
        )
        original_request = get_request_trace_id.__globals__["request"]
        get_request_trace_id.__globals__["request"] = fake_request
        try:
            self.assertEqual(get_request_trace_id(), "header-request-id")
        finally:
            get_request_trace_id.__globals__["request"] = original_request

    def test_generates_uuid_when_request_id_is_missing(self):
        fake_uuid = types.SimpleNamespace(hex="generated-request-id")

        with patch("flaskr.api.langfuse.uuid.uuid4", return_value=fake_uuid):
            self.assertEqual(get_request_trace_id(), "generated-request-id")


class ObservationLinkTests(unittest.TestCase):
    def test_mock_client_callable_attrs_do_not_leak_into_trace_ids(self):
        fake_uuid = types.SimpleNamespace(hex="generated-request-id")
        observation = MockClient()

        with patch("flaskr.api.langfuse.uuid.uuid4", return_value=fake_uuid):
            self.assertEqual(
                resolve_langfuse_trace_id(observation),
                "generated-request-id",
            )
            self.assertEqual(
                build_langfuse_observation_link(observation),
                {"trace_id": "generated-request-id"},
            )

    def test_observation_link_uses_real_observation_ids(self):
        observation = types.SimpleNamespace(
            trace_id="trace-123",
            id="span-456",
        )

        self.assertEqual(
            build_langfuse_observation_link(observation),
            {"trace_id": "trace-123", "parent_observation_id": "span-456"},
        )
