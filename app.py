"""TrackR - Personal Route Tracker (v2 - Moto Mode)
Flask endpoint for OwnTracks location data.
"""
import json
import math
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify, render_template
from models import (
    init_db, insert_location, get_locations, get_location_count,
    get_devices, get_today_locations, get_recent_locations,
    get_routes, get_moto_state, start_moto_mode, stop_moto_mode
)
from stays import process_locations, get_processed_visits, get_processed_routes
from config import HOST, PORT, TIMEZONE

app = Flask(__name__)

# ─────────────────────────────────────────────
# OWNTRACKS HTTP ENDPOINT
# ─────────────────────────────────────────────

@app.route("/owntracks", methods=["POST"])
def owntracks_receive():
    """Receive location data from OwnTracks (HTTP mode)."""
    try:
        payload = request.get_json(force=True)
        _type = payload.get("_type", "")

        if _type == "location":
            tz = timezone(timedelta(hours=-6))  # CST
            ts = payload.get("tst", 0)
            dt = datetime.fromtimestamp(ts, tz=tz)

            data = {
                "device_id": payload.get("tid", payload.get("_id", "unknown")),
                "lat": payload.get("lat", 0),
                "lon": payload.get("lon", 0),
                "timestamp_unix": ts,
                "timestamp_local": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "accuracy": payload.get("acc"),
                "battery": payload.get("batt"),
                "speed": payload.get("vel"),
                "altitude": payload.get("alt"),
                "user_agent": request.headers.get("User-Agent", "")
            }

            loc_id, tag = insert_location(data)

            if tag == "duplicate":
                return app.response_class(response='[]', status=200, mimetype='application/json')

            # OwnTracks expects empty JSON array on success
            return app.response_class(
                response='[]',
                status=200,
                mimetype='application/json'
            )

        elif _type == "transition":
            return app.response_class(response='[]', status=200, mimetype='application/json')
        elif _type == "ping":
            return app.response_class(response='[]', status=200, mimetype='application/json')
        else:
            return app.response_class(response='[]', status=200, mimetype='application/json')

    except Exception as e:
        return app.response_class(response='[]', status=200, mimetype='application/json')


# ─────────────────────────────────────────────
# MOTO MODE ENDPOINTS
# ─────────────────────────────────────────────

@app.route("/api/moto/status", methods=["GET"])
def api_moto_status():
    """Get current moto mode status."""
    state = get_moto_state()
    return jsonify({
        "active": bool(state.get("is_active", 0)),
        "started_at": state.get("started_at"),
        "route_id": state.get("route_id"),
        "points_collected": state.get("points_collected", 0)
    })


@app.route("/api/moto/start", methods=["POST"])
def api_moto_start():
    """Activate moto mode."""
    device_id = request.args.get("device", "FM")
    route_id, msg = start_moto_mode(device_id)
    if route_id:
        return jsonify({
            "status": "ok",
            "message": msg,
            "route_id": route_id
        }), 200
    else:
        return jsonify({"status": "error", "message": msg}), 409


@app.route("/api/moto/stop", methods=["POST"])
def api_moto_stop():
    """Deactivate moto mode and finalize route."""
    route_id, msg = stop_moto_mode()
    if route_id:
        routes = get_routes(limit=1)
        route = routes[0] if routes else {}
        return jsonify({
            "status": "ok",
            "message": msg,
            "route_id": route_id,
            "route": route
        }), 200
    else:
        return jsonify({"status": "error", "message": msg}), 409


# ─────────────────────────────────────────────
# API ENDPOINTS
# ─────────────────────────────────────────────

@app.route("/api/locations", methods=["GET"])
def api_locations():
    """Get locations with optional filters."""
    device_id = request.args.get("device")
    start = request.args.get("start")
    end = request.args.get("end")
    tag = request.args.get("tag")
    limit = int(request.args.get("limit", 5000))

    locations = get_locations(
        device_id=device_id,
        start_ts=int(start) if start else None,
        end_ts=int(end) if end else None,
        tag=tag,
        limit=limit
    )

    return jsonify({"count": len(locations), "locations": locations})


@app.route("/api/locations/today", methods=["GET"])
def api_today():
    """Get today's locations."""
    device_id = request.args.get("device")
    tag = request.args.get("tag")
    locations = get_today_locations(device_id=device_id, tag=tag)
    return jsonify({"count": len(locations), "locations": locations})


@app.route("/api/locations/recent", methods=["GET"])
def api_recent():
    """Get recent locations (last N minutes)."""
    minutes = int(request.args.get("minutes", 60))
    device_id = request.args.get("device")
    tag = request.args.get("tag")
    locations = get_recent_locations(minutes=minutes, device_id=device_id, tag=tag)
    return jsonify({"count": len(locations), "locations": locations})


@app.route("/api/devices", methods=["GET"])
def api_devices():
    """Get list of devices."""
    devices = get_devices()
    return jsonify({"devices": devices})


@app.route("/api/stats", methods=["GET"])
def api_stats():
    """Get basic stats."""
    conn = __import__("models").get_db()
    personal = conn.execute("SELECT COUNT(*) FROM locations WHERE tag='personal'").fetchone()[0]
    moto = conn.execute("SELECT COUNT(*) FROM locations WHERE tag='moto'").fetchone()[0]
    routes = conn.execute("SELECT COUNT(*) FROM routes WHERE tag='moto'").fetchone()[0]
    conn.close()

    return jsonify({
        "total_locations": get_location_count(),
        "personal_locations": personal,
        "ruta_locations": moto,
        "ruta_routes": routes,
        "devices": get_devices(),
        "moto_mode": get_moto_state(),
        "server_time": datetime.now().isoformat()
    })


@app.route("/api/routes", methods=["GET"])
def api_routes():
    """Get route summaries."""
    device_id = request.args.get("device")
    tag = request.args.get("tag")
    date = request.args.get("date")
    routes = get_routes(device_id=device_id, tag=tag, date=date)
    return jsonify({"routes": routes})


@app.route("/api/route/<int:route_id>/locations", methods=["GET"])
def api_route_locations(route_id):
    """Get all locations for a specific route."""
    conn = __import__("models").get_db()
    rows = conn.execute("""
        SELECT * FROM locations WHERE route_id=? ORDER BY timestamp_unix ASC
    """, (route_id,)).fetchall()
    conn.close()
    return jsonify({"count": len(rows), "locations": [dict(r) for r in rows]})


# ─────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────
# PROCESSED VISITS & ROUTES
# ─────────────────────────────────────────────

@app.route("/api/visits", methods=["GET"])
def api_visits():
    """Get processed visits (Google Timeline-style)."""
    device_id = request.args.get("device")
    date = request.args.get("date")
    tag = request.args.get("tag")
    visits = get_processed_visits(device_id=device_id, date=date, tag=tag)
    return jsonify({"count": len(visits), "visits": visits})


@app.route("/api/timeline", methods=["GET"])
def api_timeline():
    """Get full timeline: visits + routes combined, sorted by time."""
    device_id = request.args.get("device")
    date = request.args.get("date")
    tag = request.args.get("tag")
    visits = get_processed_visits(device_id=device_id, date=date, tag=tag)
    routes = get_processed_routes(device_id=device_id, date=date, tag=tag)

    # Merge and sort by start_ts
    events = []
    for v in visits:
        events.append({"type": "visit", "lat": v["lat"], "lon": v["lon"],
                       "start": v["start_local"], "end": v["end_local"],
                       "duration_min": v["duration_min"], "points": v["point_count"],
                       "tag": v["tag"]})
    for r in routes:
        events.append({"type": "route", "from_lat": r["from_lat"], "from_lon": r["from_lon"],
                       "to_lat": r["to_lat"], "to_lon": r["to_lon"],
                       "km": r["distance_km"], "min": r["duration_min"],
                       "tag": r["tag"]})

    return jsonify({"count": len(events), "events": events})


@app.route("/api/process", methods=["POST"])
def api_process():
    """Trigger stay detection processing."""
    result = process_locations()
    return jsonify(result)


# ─────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────
# ─────────────────────────────────────────────

@app.route("/")
def dashboard():
    """Web dashboard with map."""
    return render_template("dashboard.html")


@app.route("/health")
def health():
    """Health check."""
    return jsonify({
        "status": "healthy",
        "service": "TrackR",
        "version": "2.0.0",
        "locations": get_location_count(),
        "moto_mode": get_moto_state()["is_active"]
    })


# ─────────────────────────────────────────────
# STARTUP
# ─────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    import ssl
    cert_path = os.path.join(BASE_DIR, "data", "cert.pem")
    key_path = os.path.join(BASE_DIR, "data", "key.pem")
    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_ctx.load_cert_chain(cert_path, key_path)
    ssl_ctx.set_ciphers("DEFAULT:@SECLEVEL=0")
    print(f"\n🗺️  TrackR v2.0 running on https://{HOST}:{PORT}")
    print(f"📍 OwnTracks endpoint: https://{HOST}:{PORT}/owntracks")
    print(f"🏍️  Moto mode API: https://{HOST}:{PORT}/api/moto/status")
    print(f"📊 Dashboard: https://{HOST}:{PORT}/\n")
    app.run(host=HOST, port=PORT, debug=False, ssl_context=ssl_ctx)
