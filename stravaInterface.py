import webbrowser
import threading
import time
from flask import Flask, request
import requests
from stravalib.client import Client
import json
from datetime import datetime
import qrcode
import socket

# ==== LOAD CONFIG ====
with open('client.json', 'r') as f:
    client_config = json.load(f)
CLIENT_ID = client_config['client_id']
CLIENT_SECRET = client_config['client_secret']

# ==== GET LOCAL IP ====
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

LOCAL_IP = get_local_ip()
REDIRECT_URI = f'http://{LOCAL_IP}:5000/authorized/'



# ==== GLOBALS ====
app = Flask(__name__)

# ==== FLASK ROUTE ====
@app.route('/authorized')
def authorized():
    error = request.args.get('error')
    if error:
        return f"Error: {error}"

    code = request.args.get('code')
    token_data = exchange_code_for_token(code)
    if 'access_token' not in token_data:
        return f"Token exchange failed: {token_data}"

    access_token = token_data['access_token']
    client = Client(access_token=access_token)
    athlete = client.get_athlete()

    new_user = {
        "name": f"{athlete.firstname} {athlete.lastname}",
        "id": athlete.id,
        "access_token": access_token,
        "refresh_token": token_data['refresh_token'],
        "expires_at": token_data['expires_at']
    }

    try:
        with open("users.json", "r") as f:
            users = json.load(f)
    except FileNotFoundError:
        users = []

    if not any(u.get("id") == athlete.id for u in users):
        users.append(new_user)
        with open("users.json", "w") as f:
            json.dump(users, f, indent=2)
        print(f"✅ Added new user: {new_user['name']}")
        return f"Authorization successful! Welcome, {new_user['name']}! You can close this window."
    else:
        return f"{new_user['name']} is already authorized. You can close this window."

# ==== AUTH ====
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

# ==== QR CODE ====
def generate_qr():
    url = get_auth_url()
    qr = qrcode.make(url)
    qr.save("strava_auth_qr.png")
    print("✅ QR code saved as strava_auth_qr.png")
    print(f"📱 Open this link on your phone or scan the QR: {url}")

# ==== CALORIES ====
def fetch_detailed_activity_raw(activity_id, access_token):
    url = f"https://www.strava.com/api/v3/activities/{activity_id}?include_all_efforts=false"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"HTTP {response.status_code}: {response.text}")

def get_activities_since(client, since_date_str):
    since_dt = datetime.strptime(since_date_str, "%Y-%m-%d")
    activities = []
    try:
        for activity in client.get_activities(after=since_dt):
            activities.append(activity)
    except Exception as e:
        print("Failed to fetch activities:", e)
    return activities

def sum_calories(activities, access_token):
    total_calories = 0.0
    for activity in activities:
        try:
            detailed = fetch_detailed_activity_raw(activity.id, access_token)
            calories = detailed.get('calories')
            if calories is not None:
                total_calories += calories
        except Exception as e:
            print(f"⚠️ Error fetching activity {activity.id}: {e}")
    return total_calories

# ==== LEADERBOARD ====
def run_leaderboard():
    try:
        with open("users.json", "r") as f:
            users = json.load(f)
    except FileNotFoundError:
        print("No users found.")
        return

    results = []
    since = "2025-06-01"

    for user in users:
        try:
            if user['expires_at'] < time.time():
                token_data = refresh_token(user['refresh_token'])
                user['access_token'] = token_data['access_token']
                user['refresh_token'] = token_data['refresh_token']
                user['expires_at'] = token_data['expires_at']
                with open("users.json", "w") as f:
                    json.dump(users, f, indent=2)

            client = Client(access_token=user['access_token'])
            activities = get_activities_since(client, since)
            total = sum_calories(activities, user['access_token'])
            results.append((user['name'], total))
        except Exception as e:
            print(f"Error with user {user.get('name', '?')}: {e}")

    results.sort(key=lambda x: x[1], reverse=True)
    print("\n===== Calories Leaderboard =====")
    for name, cal in results:
        print(f"{name}: {cal:.2f} kcal")
    print("================================\n")

# ==== SERVER START ====
def start_server():
    print(f"🚀 Starting server at http://{LOCAL_IP}:5000")
    app.run(host='0.0.0.0', port=5000)

# ==== MAIN ====
def main():
    threading.Thread(target=start_server, daemon=True).start()
    generate_qr()

    try:
        while True:
            run_leaderboard()
            print("Sleeping for 3 hours...\n")
            time.sleep(3 * 3600)
    except KeyboardInterrupt:
        print("\nStopped by user.")

if __name__ == '__main__':
    main()