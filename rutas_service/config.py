import os
from pathlib import Path

BASE = Path(__file__).parent
DATA_DIR = BASE / "data"
DB_PATH = Path(os.getenv("RUTAS_DB", DATA_DIR / "rutas.db"))
VULN_FILE = Path(os.getenv("RUTAS_VULN_FILE", DATA_DIR / "vulnerabilidad_simulada.json"))

ENTORNO = os.getenv("ENTORNO", "desarrollo")  # "produccion" en la nube
# URL publica de este servicio (Render la expone como RENDER_EXTERNAL_URL)
URL_PUBLICA = os.getenv("PUBLIC_URL", os.getenv("RENDER_EXTERNAL_URL", "http://localhost:8000")).rstrip("/")
AUTH_URL = os.getenv("AUTH_URL", "http://localhost:8001").rstrip("/")
AUTH_ISSUER = os.getenv("AUTH_ISSUER", AUTH_URL)
AUDIENCE = "rutas-api"
_origenes = os.getenv("ALLOWED_ORIGINS", "" if ENTORNO == "produccion" else "http://localhost:8000,http://127.0.0.1:8000").split(",")
ALLOWED_ORIGINS = sorted({o.strip().rstrip("/") for o in _origenes + [URL_PUBLICA] if o.strip()})

if ENTORNO == "produccion" and not AUTH_URL.startswith("https://"):
    raise RuntimeError("En produccion AUTH_URL debe usar HTTPS")

# Fuentes externas (APIs publicas)
ARCGIS_VEREDAS = os.getenv(
    "ARCGIS_VEREDAS",
    "https://ags.esri.co/arcgis/rest/services/DatosAbiertos/VEREDAS_2016/MapServer/0/query",
)
ARCGIS_CENTROS_POBLADOS = os.getenv(
    "ARCGIS_CENTROS_POBLADOS",
    "https://services7.arcgis.com/lsxbLWF2l19Rmhqj/arcgis/rest/services/Mapa_Veredal_de_Cundinamarca/FeatureServer/0/query",
)
OSRM_URL = os.getenv("OSRM_URL", "https://router.project-osrm.org")
COD_DPTO = "25"  # Cundinamarca

HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "20"))
CACHE_TTL_GEO = 7 * 24 * 3600      # limites veredales cambian poco
CACHE_TTL_OSRM = 7 * 24 * 3600

# Parametros del modelo
FACTOR_SINUOSIDAD = 1.4     # distancia vial ~ 1.4 x linea recta en zona andina (fallback)
VELOCIDAD_RURAL_KMH = 25    # velocidad media en via terciaria (fallback)
JORNADA_MIN = 8 * 60
RATE_LIMIT_POR_MIN = 30
