"""Regression guard for slowapi-decorated routes.

When a limiter has ``headers_enabled=True``, slowapi injects the rate-limit
headers into the endpoint's ``response`` argument after the handler runs. A
decorated endpoint missing a ``request``/``response`` parameter raises at runtime
("parameter `response` must be an instance of ...") — but only when the limiter
is enabled, so the suite (which disables it) would not catch it. We inspect the
decorated endpoint signatures directly instead.
"""

import inspect

import pytest

from app.modules.ai.presentation.router import ask
from app.modules.auth.presentation.router import login, register
from app.modules.documents.presentation.router import upload_document
from app.modules.teaching_plans.presentation.router import create_plan

# Every endpoint decorated with a per-route slowapi limit.
_RATE_LIMITED_ENDPOINTS = {
    "auth.login": login,
    "auth.register": register,
    "ai.ask": ask,
    "documents.upload_document": upload_document,
    "plans.create_plan": create_plan,
}


@pytest.mark.parametrize("name", sorted(_RATE_LIMITED_ENDPOINTS))
def test_rate_limited_endpoint_accepts_request_and_response(name):
    params = inspect.signature(_RATE_LIMITED_ENDPOINTS[name]).parameters
    assert "request" in params, f"{name} is missing a `request` parameter"
    assert "response" in params, f"{name} is missing a `response` parameter"
