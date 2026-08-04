import os
import csv
import glob
from datetime import datetime
from app.db.database import get_db

def parse_date(date_str: str) -> str:
    """Parse Youtube date format (e.g. 'Jan 3, 2023') to ISO 8601 (YYYY-MM-DD)"""
    if not date_str:
        return ""
    try:
        dt = datetime.strptime(date_str.strip(), "%b %d, %Y")
        return dt.strftime("%Y-%m-%d")
    except ValueError as e:
        return f"ERR:{str(e)}:{date_str}"

def parse_duration(duration_str: str) -> int:
    """Parse duration from various formats into seconds"""
    if not duration_str:
        return 0
    try:
        if ':' in duration_str:
            parts = duration_str.split(':')
            if len(parts) == 3: # HH:MM:SS
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            elif len(parts) == 2: # MM:SS
                return int(parts[0]) * 60 + int(parts[1])
        return int(float(duration_str))
    except ValueError:
        return 0

def import_youtube_data():
    """
    Scans the data/Youtube folder for CSV files, parses them, 
    and inserts/updates the SQLite database.
    """
    base_dir = "./data/Youtube"
    if not os.path.exists(base_dir):
        return {"status": "error", "message": "Youtube data directory not found"}

    conn = get_db()
    cursor = conn.cursor()

    content_videos_upserted = 0
    traffic_sources_upserted = 0

    # 1. Import Content data (youtube_published_videos)
    content_dirs = glob.glob(os.path.join(base_dir, "Content*"))
    for cdir in content_dirs:
        csv_file = os.path.join(cdir, "Table data.csv")
        if not os.path.exists(csv_file):
            continue

        with open(csv_file, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                video_id = row.get("Content")
                if not video_id or video_id == "Total":
                    continue

                title = row.get("Video title", "")
                publish_time = parse_date(row.get("Video publish time", ""))
                
                duration_raw = row.get("Duration", "0")
                duration_seconds = parse_duration(duration_raw)
                
                views = int(row.get("Views", 0)) if row.get("Views") else 0
                watch_time = float(row.get("Watch time (hours)", 0.0)) if row.get("Watch time (hours)") else 0.0
                subscribers = int(row.get("Subscribers", 0)) if row.get("Subscribers") else 0
                impressions = int(row.get("Impressions", 0)) if row.get("Impressions") else 0
                
                ctr_raw = row.get("Impressions click-through rate (%)")
                impressions_ctr = float(ctr_raw) if ctr_raw else 0.0

                # Upsert into youtube_published_videos
                # We use REPLACE or INSERT ... ON CONFLICT (SQLite 3.24+)
                # Assuming video_id is PRIMARY KEY
                cursor.execute("""
                    INSERT INTO youtube_published_videos (
                        video_id, title, publish_time, duration_seconds, views,
                        watch_time_hours, subscribers, impressions, impressions_ctr
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(video_id) DO UPDATE SET
                        title=excluded.title,
                        publish_time=COALESCE(excluded.publish_time, youtube_published_videos.publish_time),
                        duration_seconds=COALESCE(excluded.duration_seconds, youtube_published_videos.duration_seconds),
                        views=MAX(youtube_published_videos.views, excluded.views),
                        watch_time_hours=MAX(youtube_published_videos.watch_time_hours, excluded.watch_time_hours),
                        subscribers=MAX(youtube_published_videos.subscribers, excluded.subscribers),
                        impressions=MAX(youtube_published_videos.impressions, excluded.impressions),
                        impressions_ctr=MAX(youtube_published_videos.impressions_ctr, excluded.impressions_ctr),
                        imported_at=datetime('now')
                """, (video_id, title, publish_time, duration_seconds, views, 
                      watch_time, subscribers, impressions, impressions_ctr))
                content_videos_upserted += 1

    # 2. Import Traffic Source data (youtube_traffic_sources)
    traffic_dirs = glob.glob(os.path.join(base_dir, "Traffic source*"))
    for tdir in traffic_dirs:
        csv_file = os.path.join(tdir, "Table data.csv")
        if not os.path.exists(csv_file):
            continue

        with open(csv_file, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                source = row.get("Traffic source")
                if not source or source == "Total":
                    continue

                views = int(row.get("Views", 0)) if row.get("Views") else 0
                watch_time = float(row.get("Watch time (hours)", 0.0)) if row.get("Watch time (hours)") else 0.0
                avg_view_duration = row.get("Average view duration", "")
                impressions = int(row.get("Impressions", 0)) if row.get("Impressions") else 0
                
                ctr_raw = row.get("Impressions click-through rate (%)")
                impressions_ctr = float(ctr_raw) if ctr_raw else 0.0

                cursor.execute("""
                    INSERT INTO youtube_traffic_sources (
                        traffic_source, views, watch_time_hours, avg_view_duration, 
                        impressions, impressions_ctr
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(traffic_source) DO UPDATE SET
                        views=MAX(youtube_traffic_sources.views, excluded.views),
                        watch_time_hours=MAX(youtube_traffic_sources.watch_time_hours, excluded.watch_time_hours),
                        avg_view_duration=COALESCE(excluded.avg_view_duration, youtube_traffic_sources.avg_view_duration),
                        impressions=MAX(youtube_traffic_sources.impressions, excluded.impressions),
                        impressions_ctr=MAX(youtube_traffic_sources.impressions_ctr, excluded.impressions_ctr),
                        imported_at=datetime('now')
                """, (source, views, watch_time, avg_view_duration, impressions, impressions_ctr))
                traffic_sources_upserted += 1

    conn.commit()
    
    return {
        "status": "success",
        "videos_imported": content_videos_upserted,
        "traffic_sources_imported": traffic_sources_upserted
    }
