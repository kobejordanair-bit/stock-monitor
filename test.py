import requests

URL = "https://jyfdtpswtzdjmrvbifes.supabase.co"
KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imp5ZmR0cHN3dHpkam1ydmJpZmVzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU3NTE0OTYsImV4cCI6MjA5MTMyNzQ5Nn0.VAdljkQxxshFQWxKbWyK132-cHmLFBcad2qMSJ8EuEw"

headers = {
    "apikey": KEY,
    "Authorization": f"Bearer {KEY}",
    "Content-Type": "application/json",
}

r = requests.post(f"{URL}/rest/v1/watchlist", headers=headers, json={"symbol": "TEST", "name": "測試"})
print(r.status_code)
print(r.text)