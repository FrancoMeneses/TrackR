"""TrackR Database Models - SQLite (v2)"""
import sqlite3
import math
from datetime import datetime
from config import DB_PATH


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            lat REAL NOT NULL,
            lon REAL NOT NULL,
            timestamp_unix INTEGER NOT NULL,
            timestamp_local TEXT NOT NULL,
            accuracy REAL,
            battery INTEGER,
            speed REAL,
            altitude REAL,
            tag TEXT DEFAULT 'personal',
            route_id INTEGER,
            user_agent TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS routes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            tag TEXT NOT NULL DEFAULT 'personal',
            date TEXT NOT NULL,
            start_time TEXT,
            end_time TEXT,
            start_lat REAL,
            start_lon REAL,
            end_lat REAL,
            end_lon REAL,
            total_distance_km REAL,
            total_duration_min INTEGER,
            point_count INTEGER,
            purpose TEXT,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS moto_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            is_active INTEGER DEFAULT 0,
            started_at TEXT,
            route_id INTEGER,
            points_collected INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_locations_device_ts ON locations(device_id, timestamp_unix);
        CREATE INDEX IF NOT EXISTS idx_locations_tag ON locations(tag);
        CREATE INDEX IF NOT EXISTS idx_routes_tag ON routes(tag);
        INSERT OR IGNORE INTO moto_state (id, is_active) VALUES (1, 0);
    """)
    conn.commit()
    conn.close()


def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dLat, dLon = math.radians(lat2-lat1), math.radians(lon2-lon1)
    a = math.sin(dLat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dLon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def insert_location(data):
    conn = get_db()

    # Deduplicate: skip if last point is within 120s AND 50m
    last = conn.execute(
        "SELECT lat, lon, timestamp_unix FROM locations WHERE device_id=? ORDER BY timestamp_unix DESC LIMIT 1",
        (data.get("device_id", "unknown"),)
    ).fetchone()

    if last:
        dt = data["timestamp_unix"] - last["timestamp_unix"]
        dist = haversine(last["lat"], last["lon"], data["lat"], data["lon"])
        if dt < 120 and dist < 0.05:
            # Update last point's timestamp to keep accurate timing
            conn.execute(
                "UPDATE locations SET timestamp_unix=?, timestamp_local=? WHERE id=?",
                (data["timestamp_unix"], data["timestamp_local"], last["id"])
            )
            conn.commit()
            conn.close()
            return None, "duplicate"

    # Check moto mode
    moto = conn.execute("SELECT is_active FROM moto_state WHERE id=1").fetchone()
    tag = "moto" if moto and moto["is_active"] else "personal"
    route_id = None
    if tag == "moto":
        state = conn.execute("SELECT route_id FROM moto_state WHERE id=1").fetchone()
        route_id = state["route_id"] if state else None

    conn.execute("""
        INSERT INTO locations (device_id, lat, lon, timestamp_unix, timestamp_local,
            accuracy, battery, speed, altitude, tag, route_id, user_agent)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (data.get("device_id", "unknown"), data["lat"], data["lon"],
          data["timestamp_unix"], data["timestamp_local"], data.get("accuracy"),
          data.get("battery"), data.get("speed"), data.get("altitude"),
          tag, route_id, data.get("user_agent", "")))

    if tag == "moto":
        conn.execute("UPDATE moto_state SET points_collected = points_collected + 1 WHERE id=1")

    conn.commit()
    lid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return lid, tag


def get_locations(device_id=None, start_ts=None, end_ts=None, tag=None, limit=5000):
    conn = get_db()
    q, p = "SELECT * FROM locations WHERE 1=1", []
    if device_id: q += " AND device_id=?"; p.append(device_id)
    if start_ts: q += " AND timestamp_unix>=?"; p.append(start_ts)
    if end_ts: q += " AND timestamp_unix<=?"; p.append(end_ts)
    if tag: q += " AND tag=?"; p.append(tag)
    q += " ORDER BY timestamp_unix ASC LIMIT ?"; p.append(limit)
    rows = conn.execute(q, p).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_location_count():
    conn = get_db()
    c = conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0]
    conn.close()
    return c


def get_devices():
    conn = get_db()
    rows = conn.execute("SELECT device_id, COUNT(*) as points, MIN(timestamp_local) as first_seen, MAX(timestamp_local) as last_seen FROM locations GROUP BY device_id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_today_locations(device_id=None, tag=None):
    today = datetime.now().strftime("%Y-%m-%d")
    start = int(datetime.strptime(today, "%Y-%m-%d").timestamp())
    return get_locations(device_id=device_id, start_ts=start, end_ts=start+86400, tag=tag)


def get_recent_locations(minutes=60, device_id=None, tag=None):
    start = int(datetime.now().timestamp()) - minutes*60
    return get_locations(device_id=device_id, start_ts=start, tag=tag)


def get_moto_state():
    conn = get_db()
    s = conn.execute("SELECT * FROM moto_state WHERE id=1").fetchone()
    conn.close()
    return dict(s) if s else {"is_active": 0}


def start_moto_mode(device_id="FM"):
    conn = get_db()
    state = conn.execute("SELECT is_active FROM moto_state WHERE id=1").fetchone()
    if state and state["is_active"]:
        conn.close()
        return None, "Already active"
    now = datetime.now()
    conn.execute("INSERT INTO routes (device_id, tag, date, start_time, purpose) VALUES (?, 'moto', ?, ?, 'moto_ruta')",
                 (device_id, now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S")))
    rid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute("UPDATE moto_state SET is_active=1, started_at=?, route_id=?, points_collected=0 WHERE id=1", (now.isoformat(), rid))
    conn.commit()
    conn.close()
    return rid, "OK"


def stop_moto_mode():
    conn = get_db()
    state = conn.execute("SELECT * FROM moto_state WHERE id=1").fetchone()
    if not state or not state["is_active"]:
        conn.close()
        return None, "Not active"
    rid = state["route_id"]
    now = datetime.now()

    first = conn.execute("SELECT lat, lon FROM locations WHERE route_id=? ORDER BY timestamp_unix ASC LIMIT 1", (rid,)).fetchone()
    last = conn.execute("SELECT lat, lon FROM locations WHERE route_id=? ORDER BY timestamp_unix DESC LIMIT 1", (rid,)).fetchone()
    count = conn.execute("SELECT COUNT(*) FROM locations WHERE route_id=?", (rid,)).fetchone()[0]

    dist = 0
    pts = conn.execute("SELECT lat, lon FROM locations WHERE route_id=? ORDER BY timestamp_unix ASC", (rid,)).fetchall()
    for i in range(1, len(pts)):
        dist += haversine(pts[i-1]["lat"], pts[i-1]["lon"], pts[i]["lat"], pts[i]["lon"])

    dur = 0
    if first and last:
        f = conn.execute("SELECT timestamp_unix FROM locations WHERE route_id=? ORDER BY timestamp_unix ASC LIMIT 1", (rid,)).fetchone()
        l = conn.execute("SELECT timestamp_unix FROM locations WHERE route_id=? ORDER BY timestamp_unix DESC LIMIT 1", (rid,)).fetchone()
        if f and l: dur = (l["timestamp_unix"] - f["timestamp_unix"]) // 60

    conn.execute("""UPDATE routes SET end_time=?, start_lat=?, start_lon=?, end_lat=?, end_lon=?,
        total_distance_km=?, total_duration_min=?, point_count=? WHERE id=?""",
        (now.strftime("%H:%M:%S"), first["lat"] if first else None, first["lon"] if first else None,
         last["lat"] if last else None, last["lon"] if last else None, round(dist,3), dur, count, rid))

    conn.execute("UPDATE moto_state SET is_active=0, started_at=NULL, route_id=NULL, points_collected=0 WHERE id=1")
    conn.commit()
    conn.close()
    return rid, "OK"


def get_routes(device_id=None, tag=None, date=None, limit=50):
    conn = get_db()
    q, p = "SELECT * FROM routes WHERE 1=1", []
    if device_id: q += " AND device_id=?"; p.append(device_id)
    if tag: q += " AND tag=?"; p.append(tag)
    if date: q += " AND date=?"; p.append(date)
    q += " ORDER BY date DESC, start_time DESC LIMIT ?"; p.append(limit)
    rows = conn.execute(q, p).fetchall()
    conn.close()
    return [dict(r) for r in rows]
