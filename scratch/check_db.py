import sqlite3
from app.db.database import get_db

conn = sqlite3.connect("wings.db")
cursor = conn.cursor()
cursor.execute("SELECT video_id, title, publish_time FROM youtube_published_videos LIMIT 10")
rows = cursor.fetchall()
for r in rows:
    print(r)
