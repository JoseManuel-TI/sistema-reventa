import config


def test_whatsapp_usa_fallback_si_placeholder(monkeypatch):
    monkeypatch.delenv("TIENDA_WA", raising=False)
    assert config.whatsapp() == config.WHATSAPP_FALLBACK


def test_whatsapp_respeta_valor_configurado(monkeypatch):
    monkeypatch.delenv("TIENDA_WA", raising=False)
    monkeypatch.setattr(config, "_load", lambda: {"TIENDA_WA": "https://wa.me/123"})
    assert config.whatsapp() == "https://wa.me/123"


def test_env_tiene_prioridad_sobre_config(monkeypatch):
    monkeypatch.setenv("BANCO", "Banco Test")
    assert config.get("BANCO") == "Banco Test"
