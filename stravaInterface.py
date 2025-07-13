import webbrowser
import threading
import time
from flask import Flask, request
import requests
from stravalib.client import Client
import json
from datetime import datetime

# ==== LOAD CLIENT CONFIG ====
with open('client.json', 'r') as f:
    client_config = json.load(f)
CLIENT_ID = client_config['client_id']
CLIENT_SECRET = client_config['client_secret']
REDIRECT_URI = 'http://localhost:5000/authorized'

# ==== LOAD USERS ====
with open('users.json', 'r') as f:
    users = json.load(f)

index = 0  # Select user to run with
selected_user = users[index]

# ==== GLOBALS ====
auth_code = None
auth_code_event = threading.Event()
app = Flask(__name__)
access_token = None

@app.route('/authorized')
def authorized():
    global auth_code
    error = request.args.get('error')
    if error:
        return f"Error: {error}"

    auth_code = request.args.get('code')
    auth_code_event.set()
    return "Authorization successful! You can close this window now."

def run_server():
    app.run(port=5000)

def get_auth_url():
    scope = 'activity:read_all'
    return (
        f"https://www.strava.com/oauth/authorize"
        f"?client_id={CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={REDIRECT_URI}"
        f"&approval_prompt=auto"
        f"&scope={scope}"
    )

def exchange_code_for_token(code):
    response = requests.post(
        'https://www.strava.com/oauth/token',
        data={
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'code': code,
            'grant_type': 'authorization_code',
        }
    )
    return response.json()

def refresh_token(refresh_token_val):
    response = requests.post(
        'https://www.strava.com/oauth/token',
        data={
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token_val,
        }
    )
    return response.json()

def save_user_data():
    users[index] = selected_user
    with open('users.json', 'w') as f:
        json.dump(users, f, indent=2)

def do_full_oauth_flow():
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    auth_url = get_auth_url()
    print("Opening browser to authenticate with Strava...")
    webbrowser.open(auth_url)

    print("Waiting for authorization...", end="", flush=True)
    auth_code_event.wait()

    print("\nGot authorization code. Exchanging for token...")
    token_data = exchange_code_for_token(auth_code)
    if 'access_token' not in token_data:
        raise Exception(f"Failed to exchange token: {token_data}")

    selected_user['access_token'] = token_data['access_token']
    selected_user['refresh_token'] = token_data['refresh_token']
    selected_user['expires_at'] = token_data['expires_at']
    save_user_data()

def ensure_valid_token():
    global access_token
    if 'access_token' in selected_user and 'expires_at' in selected_user:
        if selected_user['expires_at'] > time.time():
            access_token = selected_user['access_token']
            return

        print("Access token expired. Refreshing...")
        token_data = refresh_token(selected_user['refresh_token'])
        if 'access_token' not in token_data:
            raise Exception(f"Token refresh failed: {token_data}")

        selected_user['access_token'] = token_data['access_token']
        selected_user['refresh_token'] = token_data['refresh_token']
        selected_user['expires_at'] = token_data['expires_at']
        save_user_data()
        access_token = token_data['access_token']
    else:
        print("No valid token found. Starting full OAuth flow...")
        do_full_oauth_flow()
        access_token = selected_user['access_token']

def print_last_5_activities(client):
    print("\nFetching last 5 activities...")
    try:
        activities = client.get_activities(limit=5)
        for a in activities:
            print(f"- {a.name} ({a.id}) at {a.start_date_local}")
    except Exception as e:
        print("Failed to fetch activities:", e)

def get_activities_since(client, since_date_str):
    print(f"\nFetching activities since {since_date_str}...")
    since_dt = datetime.strptime(since_date_str, "%Y-%m-%d")
    activities = []

    try:
        for activity in client.get_activities(after=since_dt):
            activities.append(activity)
            print(f"- {activity.name} ({activity.distance} m) on {activity.start_date_local}")
    except Exception as e:
        print("Failed to fetch activities:", e)

    print(f"Found {len(activities)} activities since {since_date_str}")
    return activities

def fetch_detailed_activity_raw(activity_id, access_token):
    url = f"https://www.strava.com/api/v3/activities/{activity_id}?include_all_efforts=false"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"HTTP {response.status_code}: {response.text}")

def sum_calories(activities, access_token):
    total_calories = 0.0
    missing_calories = 0

    for activity in activities:
        try:
            detailed = fetch_detailed_activity_raw(activity.id, access_token)
            calories = detailed.get('calories')
            if calories is not None:
                total_calories += calories
            else:
                missing_calories += 1
        except Exception as e:
            print(f"⚠️ Error fetching activity {activity.id}: {e}")
            missing_calories += 1

    print(f"✔️ Total activities: {len(activities)} | Missing calorie data: {missing_calories}")
    return total_calories


def main_loop():
    ensure_valid_token()
    client = Client(access_token=access_token)

    # Save athlete name once
    athlete = client.get_athlete()
    print(f"Authenticated as: {athlete.firstname} {athlete.lastname}")
    if 'name' not in selected_user:
        selected_user['name'] = f"{athlete.firstname} {athlete.lastname}"
        save_user_data()

    while True:
        ensure_valid_token()
        client = Client(access_token=access_token)
        date = "2025-06-01"
        activities = get_activities_since(client, since_date_str="2025-06-01")  # or any date you choose

        total_calories = sum_calories(activities, access_token)
        print(f"{total_calories} Calories burned since {date}")

        print("Sleeping for 3 hours...\n")
        time.sleep(3 * 3600)

if __name__ == '__main__':
    try:
        main_loop()
    except KeyboardInterrupt:
        print("\nStopped by user.")