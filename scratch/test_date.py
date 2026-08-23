from datetime import datetime

try:
    dt = datetime.strptime("Jan 3, 2023", "%b %d, %Y")
    print("SUCCESS", dt.strftime("%Y-%m-%d"))
except Exception as e:
    print("ERROR", str(e))
