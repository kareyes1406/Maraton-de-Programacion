import os
import sys
import tempfile
from pathlib import Path

# Aislar pruebas: base de datos y llaves temporales, sin tocar los datos de la demo.
# En el build de Render existen las variables de produccion (ENTORNO, contrasenas, URLs): se retiran para que
# las pruebas sean deterministas; test_produccion.py las activa explicitamente cuando las necesita.
for _k in list(os.environ):
    if _k.startswith(("AUTH_PASSWORD_", "AUTH_SECRET_", "AUTH_PRIVATE_KEY")) or _k in (
            "ENTORNO", "DATABASE_URL", "FRONTEND_URL", "ALLOWED_ORIGINS", "PUBLIC_URL", "RENDER_EXTERNAL_URL"):
        del os.environ[_k]
_TMP = Path(tempfile.mkdtemp(prefix="rutas_test_"))
os.environ["RUTAS_DB"] = str(_TMP / "test.db")
os.environ["AUTH_KEYS_DIR"] = str(_TMP / "keys")
os.environ["AUTH_URL"] = "http://auth.test"
os.environ["AUTH_ISSUER"] = "http://auth.test"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
