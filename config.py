"""TrackR Configuration"""
import os

# Database
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "trackr.db")

# Server
HOST = "0.0.0.0"
PORT = 5050

# OwnTracks
OWNTRACKS_SECRET = os.environ.get("OWNTRACKS_SECRET", "")  # Optional encryption key

# Timezone (CST for Mexico)
TIMEZONE = "America/Mexico_City"
