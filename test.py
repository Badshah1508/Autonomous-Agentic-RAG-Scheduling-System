import os
import requests
from dotenv import load_dotenv

load_dotenv()

CALENDLY_TOKEN = os.getenv("CALENDLY_TOKEN", "")

def get_event_type_uris():
    if not CALENDLY_TOKEN:
        print("Error: CALENDLY_TOKEN is not set in environment or .env file.")
        print("Please add your Calendly Personal Access Token to .env as CALENDLY_TOKEN=your_token")
        return

    headers = {
        "Authorization": f"Bearer {CALENDLY_TOKEN}",
        "Content-Type": "application/json"
    }

    # Step 1: Get your "User URI" (Required to filter event types)
    user_resp = requests.get("https://api.calendly.com/users/me", headers=headers)
    if user_resp.status_code != 200:
        print(f"Error getting user: {user_resp.text}")
        return

    user_uri = user_resp.json()['resource']['uri']
    print(f"Found User: {user_uri}")

    # Step 2: Get Event Types using that User URI
    params = {"user": user_uri, "active": "true"}
    events_resp = requests.get("https://api.calendly.com/event_types", headers=headers, params=params)

    if events_resp.status_code == 200:
        events = events_resp.json().get('collection', [])
        print(f"\nFound {len(events)} active event types:\n")
        
        for event in events:
            print(f"Name: {event['name']}")
            print(f"URI:  {event['uri']}") # <--- THIS IS YOUR EVENT TYPE URI
            print("-" * 40)
    else:
        print(f"Error getting events: {events_resp.text}")

if __name__ == "__main__":
    get_event_type_uris()
