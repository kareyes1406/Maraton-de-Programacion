import os
import sys
import tempfile
from pathlib import Path

# Aislar pruebas: base de datos y llaves temporales, sin tocar los datos de la demo.
_TMP = Path(tempfile.mkdtemp(prefix="rutas_test_"))
os.environ["RUTAS_DB"] = str(_TMP / "test.db")
os.environ["AUTH_KEYS_DIR"] = str(_TMP / "keys")
os.environ["AUTH_URL"] = "http://auth.test"
os.environ["AUTH_ISSUER"] = "http://auth.test"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
