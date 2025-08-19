from flask import Flask, request, jsonify, send_file
from datetime import datetime
import requests
import os
import sqlite3

# ======
# Config
# ======
WHATSAPP_TOKEN = os.environ.get('WHATSAPP_TOKEN', '1108560464540992')
PHONE_NUMBER_ID = os.environ.get('PHONE_NUMBER_ID', '595748270299355')
PORT = 8080
app = Flask(__name__)

# ======
# SQLite: Store only message logs (no user info)
# ======
DB_PATH = "/data/chatbot.db" if os.path.exists("/data") else "chatbot.db"

def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            direction TEXT,           -- incoming / outgoing
            message_text TEXT,
            timestamp TEXT
        )
    """)
    conn.commit()
    return conn

conn = init_db()
cursor = conn.cursor()

def log_message(direction, message_text, timestamp):
    cursor.execute("""
        INSERT INTO messages (direction, message_text, timestamp)
        VALUES (?, ?, ?)
    """, (direction, message_text, timestamp))
    conn.commit()

# ======
# Session State (in-memory only, not stored in DB)
# ======
sessions = {}

def get_state(phone):
    return sessions.get(phone)

def set_state(phone, state):
    sessions[phone] = state

# ======
# WhatsApp API Helpers
# ======
WA_API_URL = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"

def send_text(phone, text):
    headers = {
        'Authorization': f'Bearer {WHATSAPP_TOKEN}',
        'Content-Type': 'application/json'
    }
    payload = {
        'messaging_product': 'whatsapp',
        'to': phone,
        'type': 'text',
        'text': {'body': text}
    }
    requests.post(WA_API_URL, json=payload, headers=headers)
    # Log outgoing response only
    log_message('outgoing', text, datetime.utcnow().isoformat())

def send_buttons(phone, header_text, body_text, buttons):
    headers = {
        'Authorization': f'Bearer {WHATSAPP_TOKEN}',
        'Content-Type': 'application/json'
    }
    button_list = [{'type': 'reply', 'reply': {'id': btn_id, 'title': btn_title}} for btn_id, btn_title in buttons]
    payload = {
        'messaging_product': 'whatsapp',
        'to': phone,
        'type': 'interactive',
        'interactive': {
            'type': 'button',
            'header': {'type': 'text', 'text': header_text},
            'body': {'text': body_text},
            'action': {'buttons': button_list}
        }
    }
    requests.post(WA_API_URL, json=payload, headers=headers)
    # Log button response sent
    log_message('outgoing', f"[BUTTONS] {header_text} - {body_text}", datetime.utcnow().isoformat())

# ======
# Webhook Endpoints
# ======
@app.route('/webhook', methods=['GET'])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == os.environ.get('gitam_chatbot_configuration_A&D'):
        return challenge, 200
    else:
        return "Verification failed", 403

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if data.get('object') == 'whatsapp_business_account':
        for entry in data['entry']:
            for change in entry['changes']:
                value = change.get('value', {})
                messages = value.get('messages', [])
                for msg in messages:
                    phone = msg['from']
                    timestamp = int(msg['timestamp'])
                    text_body = msg.get('text', {}).get('body') or ''
                    mtype = msg['type']

                    # ✅ Log incoming messages only (no user info)
                    log_message('incoming', text_body, datetime.utcfromtimestamp(timestamp).isoformat())

                    # Session-based state machine (in-memory)
                    state = get_state(phone)

                    if state is None:
                        send_text(phone, "Welcome to GITAM DEMO ChatBot")
                        set_state(phone, 'step_2')
                    elif state == 'step_2':
                        send_text(phone, "INS KALINGA Help Desk.\nPlease select a category.")
                        set_state(phone, 'step_3')
                    elif state == 'step_3':
                        if mtype == 'text':
                            buttons = [
                                ('3a', 'Accommodation'),
                                ('3b', 'Facilities'),
                                ('3c', 'Institutes'),
                                ('3d', 'Complaints & Emergencies'),
                                ('3e', 'Medical'),
                                ('3f', 'Educational'),
                                ('3g', 'Daily Essentials')
                            ]
                            send_buttons(phone, 'INS KALINGA Help Desk', 'Please select:', buttons)
                        elif mtype == 'interactive':
                            button_reply = msg['interactive']['button_reply']['id']
                            if button_reply.startswith('3'):
                                send_submenu(phone, button_reply)
                                set_state(phone, button_reply)
                            else:
                                send_text(phone, "Invalid selection, please try again.")
                    else:
                        send_text(phone, "Thank you for your response. Type 'menu' to restart.")
                        if text_body.lower() == 'menu':
                            set_state(phone, 'step_3')
    return jsonify({'status': 'success'}), 200

# ======
# Submenu (unchanged)
# ======
def send_submenu(phone, submenu_id):
    submenus = {
        '3a': ('Accommodation Query', [
            ('niar_cottage', 'Niar cottage'),
            ('ward_room', 'Ward room'),
            ('transit', 'Transit'),
            ('sma', 'SMA')
        ]),
        '3b': ('Facilities Queries', [
            ('gym', 'GYM'),
            ('swimming_pool', 'Swimming Pool'),
            ('canteen', 'Canteen')
        ]),
        # Add others as before...
    }
    submenu = submenus.get(submenu_id)
    if not submenu:
        send_text(phone, "Invalid option.")
        return
    header, buttons = submenu
    send_buttons(phone, header, "Please select:", buttons)

# ======
# Admin Endpoints
# ======
@app.route('/logs', methods=['GET'])
def view_logs():
    cursor.execute("SELECT * FROM messages ORDER BY id DESC LIMIT 50")
    rows = cursor.fetchall()
    return jsonify(rows)

@app.route('/download_db', methods=['GET'])
def download_db():
    return send_file(DB_PATH, as_attachment=True)

# ======
# Run App
# ======
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)



