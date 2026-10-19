import os
import zipfile

import backup


def test_crear_backup_incluye_db_y_config(tmp_path):
    info = backup.crear_backup(destino=str(tmp_path))
    assert os.path.exists(info["path"])
    assert info["bytes"] > 0
    with zipfile.ZipFile(info["path"]) as z:
        nombres = z.namelist()
    assert "productos.db" in nombres
    assert "LEEME.txt" in nombres


def test_crear_backup_incluye_imagenes(tmp_path):
    import db

    db.init_db()
    prov = db.add_proveedor("Prov Backup")
    pid = db.add_producto("Prod Backup", "", prov, 100, "", 1, publicar=1)
    db.update_producto(pid, precio_venta=150)

    images_dir = os.environ["IMAGES_DIR"]
    os.makedirs(os.path.join(images_dir, "proveedores"), exist_ok=True)
    with open(os.path.join(images_dir, "proveedores", "foto.txt"), "w") as f:
        f.write("x")

    info = backup.crear_backup(destino=str(tmp_path))
    with zipfile.ZipFile(info["path"]) as z:
        nombres = z.namelist()
    assert any(n.startswith("imagenes/") for n in nombres)


def test_crear_backup_sin_imagenes(tmp_path):
    os.makedirs(os.environ["IMAGES_DIR"], exist_ok=True)
    with open(os.path.join(os.environ["IMAGES_DIR"], "foto.txt"), "w") as f:
        f.write("x")
    info = backup.crear_backup(destino=str(tmp_path), incluir_imagenes=False)
    with zipfile.ZipFile(info["path"]) as z:
        nombres = z.namelist()
    assert not any(n.startswith("imagenes/") for n in nombres)


def test_ejecutar_reintenta_sin_imagenes_si_supera_limite(tmp_path, monkeypatch):
    os.makedirs(os.environ["IMAGES_DIR"], exist_ok=True)
    with open(os.path.join(os.environ["IMAGES_DIR"], "foto.txt"), "w") as f:
        f.write("x")
    monkeypatch.setattr(backup, "TELEGRAM_MAX_BYTES", 0)
    info = backup.ejecutar(destino=str(tmp_path))
    assert info["incluye_imagenes"] is False
    assert info["motivo_sin_imagenes"]
