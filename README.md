# 🗺️ TrackR - Personal Route Tracker

Sistema de tracking de ubicación propio, inspirado en Google Timeline pero con control total sobre los datos.

## Arquitectura

```
┌──────────────────┐      HTTP POST      ┌──────────────────┐
│  iPhone          │ ────────────────────→│  Pi 5 (TrackR)   │
│  OwnTracks App   │                      │  Flask + SQLite   │
│                  │                      │  Puerto 5050      │
└──────────────────┘                      └────────┬─────────┘
                                                   │
                                           ┌───────┴───────┐
                                           │               │
                                    ┌──────▼──────┐ ┌──────▼──────┐
                                    │  Dashboard  │ │  API REST   │
                                    │  (Mapa web) │ │  (Consultas)│
                                    └─────────────┘ └─────────────┘
```

## Endpoints

### Recibir ubicación (OwnTracks)

```
POST /owntracks
Content-Type: application/json

{
  "_type": "location",
  "lat": 19.0535,
  "lon": -98.1727,
  "tst": 1234567890,
  "tid": "AB",
  "acc": 20,
  "batt": 85,
  "vel": 5
}
```

### Consultar ubicaciones

```
GET /api/locations              # Todas (limit=5000)
GET /api/locations?device=AB    # Filtrar por dispositivo
GET /api/locations?start=UNIX&end=UNIX  # Por rango de tiempo
GET /api/locations/today        # Hoy
GET /api/locations/recent?minutes=60   # Última hora
```

### Dispositivos

```
GET /api/devices    # Lista de dispositivos que han reportado
GET /api/stats      # Estadísticas generales
```

### Rutas (resúmenes)

```
GET /api/routes?date=2026-07-30   # Rutas de un día
POST /api/route/summary           # Guardar resumen de ruta
```

### Dashboard

```
GET /    # Mapa web interactivo
GET /health  # Health check
```

## Setup iPhone (OwnTracks)

### 1. Instalar OwnTracks
- App Store → buscar "OwnTracks" → instalar (gratis)

### 2. Configurar permisos
- **Ubicación**: Siempre (no "Al usar la app")
- **Notificaciones**: Activar

### 3. Configurar servidor
1. Abrir OwnTracks → Settings (engranaje)
2. **Connection** → Selection: HTTP
3. **HTTP** → URL: `http://YOUR_SERVER_IP:5050/owntracks`
4. **HTTP** → Method: POST
5. **HTTP** → Content-Type: application/json

### 4. Configurar tracking
1. Settings → **Location** → Tracking mode: **Significant**
2. Settings → **Location** → Distance filter: 50 metros
3. Settings → **Location** → Watch interval: 120 segundos

### 5. Modos de monitoreo

| Modo | Uso | Batería |
|------|-----|---------|
| **Significant** (default) | Solo cuando te mueves ~500m | ✅ Baja |
| **Move mode** | Actualización continua | ⚠️ Media |
| **Manual** | Solo cuando abres la app | ✅ Muy baja |

### 6. Activar/Desactivar tracking
- **Para activar**: Abrir OwnTracks → tocar el botón de modo → "Move" o "Significant"
- **Para desactivar**: Cambiar modo a "Manual" o cerrar la app
- **Geofences**: Configurar regiones para automatizaciones (ej: "al llegar a casa, desactivar")

## Dashboard

Accede al mapa desde:
```
http://YOUR_SERVER_IP:5050/
```

### Funciones:
- 📅 Ver ubicaciones de hoy
- ⏱️ Última hora / últimas 6 horas
- 🌐 Ver todo el historial
- 🔄 Auto-refresh cada 30 segundos
- 📍 Filtrar por dispositivo
- 📅 Seleccionar fecha específica
- 📊 Estadísticas en tiempo real

## Uso con Aserrin

El agente Aserrin puede consultar las rutas via API:

```bash
# Ver ubicaciones de hoy
curl http://YOUR_SERVER_IP:5050/api/locations/today

# Ver rutas de un día específico
curl http://YOUR_SERVER_IP:5050/api/routes?date=2026-07-30

# Guardar resumen de ruta
curl -X POST http://YOUR_SERVER_IP:5050/api/route/summary \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "AB",
    "date": "2026-07-30",
    "start_time": "09:00:00",
    "end_time": "10:30:00",
    "start_lat": 19.05,
    "start_lon": -98.17,
    "end_lat": 19.10,
    "end_lon": -98.20,
    "total_distance_km": 12.5,
    "total_duration_min": 90,
    "point_count": 45,
    "purpose": "Entrega CNC",
    "notes": "Ruta por libramiento"
  }'
```

## Archivos

```
trackr/
├── app.py              # Flask endpoint principal
├── models.py           # Modelos de base de datos
├── config.py           # Configuración
├── requirements.txt    # Dependencias
├── trackr.service      # Servicio systemd
├── README.md           # Esta documentación
├── data/
│   └── trackr.db       # Base de datos SQLite
├── templates/
│   └── dashboard.html  # Dashboard web con mapa
└── static/             # Assets estáticos
```

## Instalación en Pi 5

```bash
cd ~/trackr
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Probar
python app.py

# Instalar servicio
sudo cp trackr.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable trackr
sudo systemctl start trackr
```

## Seguridad (TODO)

- [ ] Agregar autenticación al endpoint
- [ ] HTTPS con Let's Encrypt o certificado auto-firmado
- [ ] Rate limiting
- [ ] API key para consultas externas (Aserrin)

---

**Creado:** 30 julio 2026
**Autor:** BeStackDevelopment / subfire
