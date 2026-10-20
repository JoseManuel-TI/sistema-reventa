"""Tests de generación de Reels 9:16 y publicación como REELS."""

import os

import db
import instagram_api
import reels


def _producto_con_imagen(tmp_path, nombre="Perfume Árabe Lattafa Yara Moi 100 ml", precio=30000):
    from PIL import Image

    prov = db.get_proveedor_por_nombre("Test") or None
    prov_id = prov["id"] if prov else db.add_proveedor("Test")
    pid = db.add_producto(
        nombre=nombre, descripcion="", proveedor_id=prov_id,
        costo=precio / 1.35, categoria="Perfumes", stock=1, publicar=1,
    )
    db.update_producto(pid, precio_venta=precio)

    rel = os.path.join("proveedores", "Test", f"{pid}.jpg")
    destino = os.path.join(reels.IMAGENES_DIR, rel)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    Image.new("RGB", (800, 1000), (230, 230, 230)).save(destino, "JPEG")
    db.add_imagen(pid, f"imagenes/{rel}", es_principal=True)
    return db.get_producto(pid)


def test_componer_frame_es_9_16(tmp_path):
    from PIL import Image

    producto = _producto_con_imagen(tmp_path)
    origen = reels._fuente_archivo(db.get_imagenes(producto["id"])[0]["archivo"])
    salida = str(tmp_path / "frame.png")

    reels.componer_frame(producto, origen, salida)

    with Image.open(salida) as img:
        assert img.size == (1080, 1920)


def test_generar_reel_crea_mp4(tmp_path):
    if not reels.disponible():
        import pytest

        pytest.skip("ffmpeg/Pillow no disponibles")

    producto = _producto_con_imagen(tmp_path)
    ok, resultado = reels.generar_reel(producto, "https://clickya.net")

    assert ok, resultado
    assert resultado.endswith(".mp4")
    archivo = os.path.join(reels.REELS_DIR, os.path.basename(resultado))
    assert os.path.getsize(archivo) > 10000


def test_postear_producto_usa_reel(monkeypatch):
    monkeypatch.setattr(instagram_api, "_get_config", lambda: ("tok", "ig"))
    monkeypatch.setattr(reels, "disponible", lambda: True)
    monkeypatch.setattr(reels, "generar_reel", lambda p, base_url: (True, "https://x/reel.mp4"))

    llamadas = []

    def fake_api(method, endpoint, data=None, params=None):
        llamadas.append((method, endpoint))
        if endpoint.endswith("/media"):
            return {"id": "c1"}
        if endpoint == "c1":
            return {"status_code": "FINISHED"}
        return {"id": "m1"}

    monkeypatch.setattr(instagram_api, "_api_call", fake_api)
    monkeypatch.setattr(
        instagram_api, "postear_foto", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debe usar foto"))
    )

    producto = {
        "id": 1, "nombre": "Perfume", "precio_venta": 1000,
        "beneficios": "", "imagenes": [{"archivo": "imagenes/x.jpg"}],
    }
    import db as _db

    monkeypatch.setattr(_db, "get_producto", lambda pid: producto)
    monkeypatch.setattr(_db, "get_imagenes", lambda pid: [{"archivo": "imagenes/x.jpg"}])

    ok, msg = instagram_api.postear_producto(1, "https://clickya.net")

    assert ok
    assert msg.startswith("reel:")
    assert ("POST", "ig/media") in llamadas
    assert ("POST", "ig/media_publish") in llamadas


def test_postear_producto_cae_a_foto_si_falla_reel(monkeypatch):
    monkeypatch.setattr(instagram_api, "_get_config", lambda: ("tok", "ig"))
    monkeypatch.setattr(reels, "disponible", lambda: True)
    monkeypatch.setattr(reels, "generar_reel", lambda p, base_url: (False, "sin imagen"))
    monkeypatch.setattr(instagram_api, "postear_foto", lambda url, caption: (True, "foto1"))

    producto = {
        "id": 2, "nombre": "Celular", "precio_venta": 2000,
        "beneficios": "", "tipo_producto": "fisico_local",
    }
    import db as _db

    monkeypatch.setattr(_db, "get_producto", lambda pid: producto)
    monkeypatch.setattr(_db, "get_imagenes", lambda pid: [{"archivo": "imagenes/x.jpg"}])

    ok, msg = instagram_api.postear_producto(2, "https://clickya.net")

    assert ok
    assert msg == "foto1"


def test_colaboradores_parsea_usuarios(monkeypatch):
    monkeypatch.setattr(
        instagram_api.config,
        "get",
        lambda clave: "@esposa, amigo ," if clave == "IG_COLLABORATORS" else None,
    )
    assert instagram_api._colaboradores() == ["esposa", "amigo"]


def test_reel_incluye_colaboradores(monkeypatch):
    monkeypatch.setattr(instagram_api, "_get_config", lambda: ("tok", "ig"))
    monkeypatch.setattr(instagram_api, "_colaboradores", lambda: ["esposa"])
    monkeypatch.setattr(instagram_api.reels, "generar_reel", lambda p, b: (True, "https://x/r.mp4"))

    capturado = {}

    def fake_api(method, endpoint, data=None, params=None):
        if endpoint.endswith("/media"):
            capturado.update(data)
            return {"id": "c1"}
        if endpoint == "c1":
            return {"status_code": "FINISHED"}
        return {"id": "m1"}

    monkeypatch.setattr(instagram_api, "_api_call", fake_api)

    ok, _ = instagram_api.postear_reel({"id": 1, "nombre": "x", "precio_venta": 1}, "cap", "https://clickya.net")

    assert ok
    assert capturado["collaborators"] == ["esposa"]


def test_limpiar_texto_quita_emoji_y_conserva_guion():
    assert reels._limpiar_texto("⌚ APPLE WATCH SE 3 – 40MM") == "APPLE WATCH SE 3 – 40MM"
    assert reels._limpiar_texto("📦 Combo  🎧 Auriculares") == "Combo Auriculares"
