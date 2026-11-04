# Rutas de atención en salud rural — Cundinamarca

Microservicio que sugiere el **orden de visita de un equipo de salud a 5 veredas** en una jornada, combinando la
necesidad de atención (índice de vulnerabilidad **simulado**) y la distancia real por carretera.
Ciclo de Investigación — Maratón de Programación con Impacto Social LCUP/CCPL 2026, Universidad de Cundinamarca.

## Requisitos
- Windows con Python 3.11 o superior
- Conexión a internet (APIs de veredas, OSRM y mapa base; después funciona con caché)

## Ejecución
```bat
iniciar.bat
```
El script crea el entorno virtual (la primera vez), inicia los dos servicios y abre http://localhost:8000.
No cierre las dos ventanas de consola mientras use la aplicación.

Ejecución manual:
```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn auth_service.main:app --port 8001
.venv\Scripts\python -m uvicorn rutas_service.main:app --port 8000
```

## Usuarios de prueba
Definidos en `auth_service/seed_demo.json` (solo para la demostración local):

| Usuario | Rol | Puede |
|---|---|---|
| `medico.demo` | médico | generar rutas |
| `coordinador.demo` | coordinador | generar rutas y ver auditoría |
| `auditor.demo` | auditor | ver, verificar y reproducir la auditoría |

Cliente máquina a máquina: `integracion-secretaria` (client credentials).

## Uso
1. Ingresar con OAuth 2.0 (botón "Ingresar con cuenta institucional").
2. Elegir el municipio, revisar las 5–15 veredas candidatas y ajustar los parámetros.
3. "Generar ruta priorizada": mapa con la ruta por carretera, orden de visita, km, duración y la razón de cada elección.
4. Pestaña **Auditoría**: verificar la integridad de la cadena y reproducir cualquier ruta.

Documentación interactiva de la API: http://localhost:8000/docs

## Pruebas
```bash
.venv\Scripts\python -m pytest -q
```

## Estructura
```
auth_service/        servidor OAuth 2.0 (PKCE, client credentials, JWT RS256, JWKS)
rutas_service/       API de rutas: optimizador, fuentes externas, auditoría, caché
  data/              índice de vulnerabilidad simulado (JSON) y base SQLite
  db/                esquema PostgreSQL para producción
frontend/            interfaz web (Leaflet)
tests/               20 pruebas automatizadas
docs/                documentos IEEE (arquitectura y uso de IA) y diagramas
scripts/             generación del JSON de vulnerabilidad
.github/workflows/   pipeline de CI
```

## Despliegue en la nube (Render)
El archivo `render.yaml` define los dos microservicios con HTTPS automático.

1. En https://render.com iniciar sesión con GitHub → **New → Blueprint** → elegir este repositorio.
2. Render pedirá las contraseñas de producción (`AUTH_PASSWORD_MEDICO_DEMO`, `AUTH_PASSWORD_COORDINADOR_DEMO`,
   `AUTH_PASSWORD_AUDITOR_DEMO`, mínimo 12 caracteres). El secreto del cliente de integración se genera solo.
3. Al terminar, verificar que las URLs asignadas coincidan con `FRONTEND_URL` (auth) y `AUTH_URL` (api);
   si Render agregó un sufijo, corregirlas en *Environment* y redesplegar.
4. Abrir `https://maraton-rutas-api.onrender.com`.

Seguridad en producción (`ENTORNO=produccion`):
- HTTPS obligatorio (el servicio no arranca con URLs `http://`) y cabecera HSTS.
- Las credenciales de demostración del repositorio quedan **deshabilitadas**: solo funcionan las contraseñas y
  secretos definidos como variables de entorno en Render (nunca en el código).
- Llave RSA generada al iniciar (o fija con `AUTH_PRIVATE_KEY_PEM`); el rutas-service recarga el JWKS al cambiar.
- Tokens JWT RS256 de 15 min, PKCE obligatorio, CORS y redirect URIs limitados a la URL pública del frontend.

Limitación de la capa gratuita: el disco es efímero (la auditoría SQLite se reinicia con cada despliegue) y los
servicios se suspenden tras 15 min sin uso (la primera petición tarda ~1 min). Para producción real: PostgreSQL
(`rutas_service/db/schema_postgres.sql`) y plan pago.

## Fuentes de datos
- Veredas de Colombia — Esri Colombia Datos Abiertos (base DANE/POT)
- Mapa Veredal de Cundinamarca — Gobernación de Cundinamarca (centros poblados)
- OSRM / OpenStreetMap — distancias, rutas y mapa base

> El índice de vulnerabilidad es simulado y no representa la realidad de ninguna comunidad.
> La ruta es una sugerencia: la decisión final corresponde al equipo de salud.
