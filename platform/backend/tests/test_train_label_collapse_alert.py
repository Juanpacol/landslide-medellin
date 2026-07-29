"""Regression test for the label-collapse Slack alert (specs/006-neural-estimators/spec.md
criterion 3): training used to abort silently when the positive class collapsed to <2 unique
values — exactly what happened in production per docs/research/audit-2026-07.md §3, and
nothing notified anyone. `_alert_label_collapse` is the fix; this test only covers the function
in isolation (no real network call, no real training run).
"""

from __future__ import annotations

from ml.train import _alert_label_collapse


def test_no_webhook_configured_is_a_silent_noop(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    # Must not raise even though there's nothing to post to.
    _alert_label_collapse(n_samples=100, n_positive=0)


def test_posts_to_webhook_when_configured(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.example/test")

    calls = []

    class _FakeResponse:
        status_code = 200

    def _fake_post(url, json, timeout):  # noqa: A002
        calls.append((url, json, timeout))
        return _FakeResponse()

    import requests

    monkeypatch.setattr(requests, "post", _fake_post)

    _alert_label_collapse(n_samples=8429, n_positive=0)

    assert len(calls) == 1
    url, payload, timeout = calls[0]
    assert url == "https://hooks.slack.example/test"
    assert "8429" in payload["text"]
    assert "n_positive=0" in payload["text"]


def test_never_raises_even_if_the_post_fails(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.example/test")

    import requests

    def _boom(*args, **kwargs):
        raise ConnectionError("network down")

    monkeypatch.setattr(requests, "post", _boom)

    # A failed notification must never fail the training run itself.
    _alert_label_collapse(n_samples=1, n_positive=0)
