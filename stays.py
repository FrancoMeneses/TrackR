"""TrackR - Stay Detection v2 (Google Timeline-style)"""
import math
from datetime import datetime
from models import get_db, haversine

# ── CONFIG ──
STAY_RADIUS_M = 100          # Radio para misma estancia (metros)
STAY_MIN_DURATION_MIN = 3    # Mínimo para considerar estancia
MOVE_THRESHOLD_M = 200       # Distancia para considerar movimiento


def process_locations(device_id="FM"):
    """Procesa puntos GPS crudos en estancias y rutas."""
    conn = get_db()

    points = conn.execute("""
        SELECT id, lat, lon, timestamp_unix, timestamp_local, tag
        FROM locations WHERE device_id=? ORDER BY timestamp_unix
    """, (device_id,)).fetchall()

    if len(points) < 2:
        conn.close()
        return {"visits": 0, "routes": 0}

    # ── FASE 1: Clustering — agrupar puntos cercanos ──
    clusters = []  # [{points: [...], center_lat, center_lon}]
    current_cluster = {"points": [dict(points[0])]}

    for i in range(1, len(points)):
        p = dict(points[i])

        # Centro del cluster actual
        pts = current_cluster["points"]
        c_lat = sum(x["lat"] for x in pts) / len(pts)
        c_lon = sum(x["lon"] for x in pts) / len(pts)

        dist_m = haversine(c_lat, c_lon, p["lat"], p["lon"]) * 1000

        if dist_m < STAY_RADIUS_M:
            current_cluster["points"].append(p)
        else:
            # Cerrar cluster actual
            current_cluster["center_lat"] = c_lat
            current_cluster["center_lon"] = c_lon
            clusters.append(current_cluster)
            # Abrir nuevo cluster CON el punto nuevo
            current_cluster = {"points": [p]}

    # Cerrar último cluster
    pts = current_cluster["points"]
    current_cluster["center_lat"] = sum(x["lat"] for x in pts) / len(pts)
    current_cluster["center_lon"] = sum(x["lon"] for x in pts) / len(pts)
    clusters.append(current_cluster)

    # ── FASE 2: Filtrar estancias por duración ──
    visits = []
    for cl in clusters:
        pts = cl["points"]
        duration = (pts[-1]["timestamp_unix"] - pts[0]["timestamp_unix"]) / 60
        if duration >= STAY_MIN_DURATION_MIN or len(pts) >= 2:
            visits.append({
                "lat": cl["center_lat"],
                "lon": cl["center_lon"],
                "start_ts": pts[0]["timestamp_unix"],
                "end_ts": pts[-1]["timestamp_unix"],
                "duration_min": int(duration),
                "point_count": len(pts),
                "tag": pts[0].get("tag", "personal")
            })

    # ── FASE 3: Crear rutas entre estancias ──
    # Get raw points for distance calculation
    all_pts = conn.execute("""
        SELECT lat, lon, timestamp_unix FROM locations
        WHERE device_id=? ORDER BY timestamp_unix
    """, (device_id,)).fetchall()

    routes = []
    for i in range(1, len(visits)):
        prev, curr = visits[i-1], visits[i]
        dur = int((curr["start_ts"] - prev["end_ts"]) / 60)

        # Find raw points between these two visits
        route_pts = [p for p in all_pts
                     if prev["end_ts"] <= p["timestamp_unix"] <= curr["start_ts"]]

        # Calculate distance from raw points
        dist = 0
        if len(route_pts) >= 2:
            for j in range(1, len(route_pts)):
                dist += haversine(route_pts[j-1]["lat"], route_pts[j-1]["lon"],
                                  route_pts[j]["lat"], route_pts[j]["lon"])
        else:
            # Fallback: straight line between visit centers
            dist = haversine(prev["lat"], prev["lon"], curr["lat"], curr["lon"])

        if dist * 1000 > MOVE_THRESHOLD_M or dur > 10:
            routes.append({
                "from_lat": prev["lat"], "from_lon": prev["lon"],
                "to_lat": curr["lat"], "to_lon": curr["lon"],
                "start_ts": prev["end_ts"], "end_ts": curr["start_ts"],
                "distance_km": round(dist, 3),
                "duration_min": dur,
                "tag": curr["tag"]
            })

    # ── FASE 4: Guardar en DB ──
    conn.execute("DELETE FROM processed_visits WHERE device_id=?", (device_id,))
    conn.execute("DELETE FROM processed_routes WHERE device_id=?", (device_id,))

    for v in visits:
        conn.execute("""
            INSERT INTO processed_visits (device_id, lat, lon, start_ts, end_ts,
                start_local, end_local, duration_min, point_count, tag)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (device_id, v["lat"], v["lon"], v["start_ts"], v["end_ts"],
              datetime.fromtimestamp(v["start_ts"]).strftime("%Y-%m-%d %H:%M:%S"),
              datetime.fromtimestamp(v["end_ts"]).strftime("%Y-%m-%d %H:%M:%S"),
              v["duration_min"], v["point_count"], v["tag"]))

    for r in routes:
        conn.execute("""
            INSERT INTO processed_routes (device_id, from_lat, from_lon,
                to_lat, to_lon, start_ts, end_ts, distance_km, duration_min, tag)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (device_id, r["from_lat"], r["from_lon"], r["to_lat"], r["to_lon"],
              r["start_ts"], r["end_ts"], r["distance_km"], r["duration_min"], r["tag"]))

    conn.commit()
    conn.close()
    return {"visits": len(visits), "routes": len(routes)}


def get_processed_visits(device_id=None, date=None, tag=None):
    conn = get_db()
    q, p = "SELECT * FROM processed_visits WHERE 1=1", []
    if device_id: q += " AND device_id=?"; p.append(device_id)
    if date: q += " AND start_local LIKE ?"; p.append(f"{date}%")
    if tag: q += " AND tag=?"; p.append(tag)
    q += " ORDER BY start_ts ASC"
    rows = conn.execute(q, p).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_processed_routes(device_id=None, date=None, tag=None):
    conn = get_db()
    q, p = "SELECT * FROM processed_routes WHERE 1=1", []
    if device_id: q += " AND device_id=?"; p.append(device_id)
    if date:
        start = int(__import__("datetime").datetime.strptime(date, "%Y-%m-%d").timestamp())
        q += " AND start_ts>=? AND start_ts<?"; p.append(start); p.append(start+86400)
    if tag: q += " AND tag=?"; p.append(tag)
    q += " ORDER BY start_ts ASC"
    rows = conn.execute(q, p).fetchall()
    conn.close()
    return [dict(r) for r in rows]
