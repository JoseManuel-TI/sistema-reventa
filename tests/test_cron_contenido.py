"""Tests del cliente del scheduler (`cron_contenido.py`)."""

import urllib.error

import cron_contenido


class _Resp:
    def __init__(self, body=b'{"ok": true}'):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_sin_token_falla(monkeypatch, capsys):
    monkeypatch.delenv("CRON_TOKEN", raising=False)
    assert cron_contenido.main() == 1
    assert "CRON_TOKEN" in capsys.readouterr().err


def test_envia_token_y_url(monkeypatch):
    monkeypatch.setenv("CRON_TOKEN", "secreto")
    monkeypatch.setenv("PUBLIC_URL", "https://clickya.net/")
    capturado = {}

    def fake_urlopen(req, timeout=None):
        capturado["url"] = req.full_url
        capturado["method"] = req.get_method()
        capturado["token"] = req.get_header("X-cron-token")
        return _Resp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert cron_contenido.main() == 0
    assert capturado["url"] == "https://clickya.net/contenido/cron"
    assert capturado["method"] == "POST"
    assert capturado["token"] == "secreto"


class _FP:
    def read(self, *args):
        return b"error"

    def close(self):
        pass


def test_error_http_devuelve_1(monkeypatch):
    monkeypatch.setenv("CRON_TOKEN", "secreto")

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, _FP())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert cron_contenido.main() == 1
