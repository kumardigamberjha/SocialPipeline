import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.services.youtube_import import import_youtube_data

if __name__ == "__main__":
    result = import_youtube_data()
    print("Import result:", result)
