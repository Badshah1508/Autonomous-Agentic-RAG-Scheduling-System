import os
import requests
from datetime import timedelta
from dateutil import parser
from dotenv import load_dotenv

load_dotenv()

# ==============================
# CONFIG
# ==============================

CALENDLY_TOKEN = os.getenv("CALENDLY_TOKEN", "")

def get_headers():
    token = os.getenv("CALENDLY_TOKEN", CALENDLY_TOKEN)
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

# ==============================
# STEP 1: CHECK AVAILABILITY
# ==============================

def is_time_available(event_type_uri: str, start_time: str, duration_minutes: int):
    token = os.getenv("CALENDLY_TOKEN", CALENDLY_TOKEN)
    if not token:
        return False, "CALENDLY_TOKEN not configured"

    try:
        start_dt = parser.isoparse(start_time)
        end_dt = start_dt + timedelta(minutes=duration_minutes)

        url = "https://api.calendly.com/event_type_available_times"
        params = {
            "event_type": event_type_uri,
            "start_time": start_dt.isoformat(),
            "end_time": end_dt.isoformat()
        }

        response = requests.get(url, headers=get_headers(), params=params)

        if response.status_code != 200:
            return False, response.text

        data = response.json()
        return len(data.get("collection", [])) > 0, data
    except Exception as e:
        return False, str(e)

# ==============================
# STEP 2: CREATE INVITEE
# ==============================

def create_invitee(
    event_type_uri: str,
    name: str,
    email: str,
    start_time: str,
    timezone: str = "Asia/Kolkata"
):
    token = os.getenv("CALENDLY_TOKEN", CALENDLY_TOKEN)
    if not token:
        return {"success": False, "error": "CALENDLY_TOKEN not configured"}

    payload = {
        "event_type": event_type_uri,
        "start_time": start_time,
        "invitee": {
            "name": name,
            "email": email,
            "timezone": timezone
        },
        "location": {
            "kind": "google_conference"
        }
    }

    url = "https://api.calendly.com/invitees"
    try:
        response = requests.post(url, headers=get_headers(), json=payload)
        if response.status_code in (200, 201):
            return {"success": True, "data": response.json()}
        return {"success": False, "error": response.text}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ==============================
# STEP 3: MAIN WRAPPER
# ==============================

def schedule_calendly_meeting(
    event_type_uri: str,
    name: str,
    email: str,
    start_time: str,
    duration_minutes: int = 30
):
    print("Scheduling Calendly meeting...\n")
    token = os.getenv("CALENDLY_TOKEN", CALENDLY_TOKEN)
    if not token:
        return {
            "success": False,
            "message": "Calendly token not configured in .env. Please set CALENDLY_TOKEN to schedule meetings."
        }

    available, info = is_time_available(
        event_type_uri,
        start_time,
        duration_minutes
    )

    if not available:
        return {
            "success": False,
            "message": "Selected time slot is not available or Calendly is not reachable"
        }

    return create_invitee(
        event_type_uri=event_type_uri,
        name=name,
        email=email,
        start_time=start_time
    )

# ==============================
# EXAMPLE RUN
# ==============================

if __name__ == "__main__":
    EVENT_TYPE_URI = os.getenv("CALENDLY_EVENT_TYPE_URI", "https://api.calendly.com/event_types/3677b0d0-1e8d-458e-98ea-575bb00c1cb0")

    result = schedule_calendly_meeting(
        event_type_uri=EVENT_TYPE_URI,
        name="Badshah",
        email="badshahkumar1508@gmail.com",
        start_time="2026-02-04T09:30:00Z"
    )

    print(result)
