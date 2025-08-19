from flask import Flask, request, jsonify
from datetime import datetime
import requests
import os

# Required environment variables
WHATSAPP_TOKEN = os.environ.get('WHATSAPP_TOKEN')  # Cloud API access token
PHONE_NUMBER_ID = os.environ.get('PHONE_NUMBER_ID')  # WhatsApp phone number ID
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN')  # Your chosen webhook verify token

# Fixed port number (as per your request)
PORT = int(os.environ.get('PORT', 8080))

if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID or not VERIFY_TOKEN:
    raise RuntimeError("Missing required environment variables: WHATSAPP_TOKEN, PHONE_NUMBER_ID, VERIFY_TOKEN")

app = Flask(__name__)

WA_API_URL = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"

# ---- Messaging helpers ----
def send_text(phone: str, text: str):
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
    r = requests.post(WA_API_URL, json=payload, headers=headers, timeout=15)
    r.raise_for_status()

def send_buttons(phone: str, header_text: str, body_text: str, buttons):
    """
    buttons: list of tuples (btn_id, btn_title)
    """
    headers = {
        'Authorization': f'Bearer {WHATSAPP_TOKEN}',
        'Content-Type': 'application/json'
    }
    button_list = [
        {'type': 'reply', 'reply': {'id': btn_id, 'title': btn_title}}
        for btn_id, btn_title in buttons
    ]
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
    r = requests.post(WA_API_URL, json=payload, headers=headers, timeout=15)
    r.raise_for_status()

def send_main_menu(phone: str):
    buttons = [
        ('3a', 'Accommodation'),
        ('3b', 'Facilities'),
        ('3c', 'Institutes'),
        ('3d', 'Complaints & Emergencies'),
        ('3e', 'Medical'),
        ('3f', 'Educational'),
        ('3g', 'Daily Essentials')
    ]
    send_buttons(
        phone,
        header_text='INS KALINGA Help Desk',
        body_text='Please select one of the following questions as per your query.',
        buttons=buttons
    )

def send_submenu(phone: str, submenu_id: str):
    submenus = {
        '3a': ('ACCOMMODATION QUERY', [
            ('niar_cottage', 'Niar cottage'),
            ('ward_room', 'Ward room'),
            ('transit', 'Transit'),
            ('sma', 'SMA')
        ]),
        '3b': ('Facilities Queries', [
            ('gym', 'GYM (KLG/KM Ward room)'),
            ('swimming_pool', 'Swimming Pool'),
            ('canteen', 'Canteen'),
            ('sanghamitra', 'Sanghamitra'),
            ('icici_bank', 'ICICI Bank'),
            ('market_details', 'Market details'),
            ('post_office', 'Post Office')
        ]),
        '3c': ('Institutes Details', [
            ('courtyard', 'Courtyard'),
            ('sailor_institute', 'Sailor Institute'),
            ('dolphin_cove', 'Dolphin Cove'),
            ('sheet_bend', 'Sheet Bend'),
            ('ncb', 'NCB'),
            ('noi', 'NOI')
        ]),
        '3d': ('COMPLAINTS & EMERGENCY QUERY', [
            ('ward_room', 'Ward room'),
            ('sailor_institute', 'Sailor Institute'),
            ('nora', 'NORA'),
            ('sma', 'SMA'),
            ('ration_log', 'Ration/LOG'),
            ('nwwa', 'NWWA'),
            ('snake_catcher', 'Snake Catcher'),
            ('fire_brigade', 'Fire Brigade'),
            ('area_cleanliness', 'Area Cleanliness/tree pruning')
        ]),
        '3e': ('MEDICAL QUERY', [
            ('mi_room', 'MI room'),
            ('kalyani_opd', 'Kalyani OPD'),
            ('gitam_opds', 'GITAM OPDs')
        ]),
        '3f': ('EDUCATIONAL', [
            ('nsc', 'NSC'),
            ('kv', 'KV'),
            ('library', 'Library'),
            ('gitam', 'GITAM'),
            ('presidential', 'Presidential'),
            ('vignan', 'Vignan')
        ]),
        '3g': ('Daily Essentials', [
            ('grocery_shop', 'Grocery Shop'),
            ('milk_shop', 'Milk Shop'),
            ('tailor', 'Tailor'),
            ('stationary', 'Stationary'),
            ('saloon_barber', 'Saloon/Barber'),
            ('vegetables', 'Vegetables'),
            ('bike_repair_shop', 'Bike Repair Shop'),
            ('atm_services', 'ATM Services')
        ])
    }
    submenu = submenus.get(submenu_id)
    if not submenu:
        send_text(phone, "Invalid submenu choice.")
        return
    header, buttons = submenu
    send_buttons(phone, header, "Please select one of the following questions as per your query.", buttons)

# ---- Webhook verification (GET) ----
@app.route('/webhook', methods=['GET'])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Verification failed", 403

# ---- Webhook receiver (POST) ----
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json(silent=True) or {}

    # Only process WhatsApp Business Account updates
    if data.get('object') != 'whatsapp_business_account':
        return jsonify({'status': 'ignored'}), 200

    try:
        for entry in data.get('entry', []):
            for change in entry.get('changes', []):
                value = change.get('value', {})
                messages = value.get('messages', [])
                for msg in messages:
                    phone = msg.get('from')
                    mtype = msg.get('type')

                    # Stateless routing:
                    # - If user sends "menu" (text), show main menu
                    # - If text (anything else), send greeting + menu
                    # - If interactive button with id starting "3", show submenu
                    # - If interactive button within submenu, echo selection and ask for details

                    if not phone:
                        continue

                    if mtype == 'text':
                        body = (msg.get('text', {}) or {}).get('body', '')
                        if body.strip().lower() == 'menu':
                            send_main_menu(phone)
                        else:
                            send_text(phone, "INS KALINGA Help Desk.\n\nHello Sir/Ma'am,\n\nGreetings of the day.\n\nWelcome to the INS KALINGA Help Desk.\n\nPlease select one of the following questions as per your query.")
                            send_main_menu(phone)

                    elif mtype == 'interactive':
                        interactive = msg.get('interactive', {}) or {}

                        # Button replies
                        if 'button_reply' in interactive:
                            button_reply = interactive['button_reply'] or {}
                            btn_id = button_reply.get('id', '')

                            # Main menu buttons start with "3"
                            if btn_id.startswith('3'):
                                # Send submenu for that section
                                send_submenu(phone, btn_id)
                            else:
                                # Submenu item selected
                                send_text(phone, f"You selected: {btn_id}. Please provide further details or type 'menu' to return to the main menu.")

                        # List replies (if you later switch to list-type interactive)
                        elif 'list_reply' in interactive:
                            list_reply = interactive['list_reply'] or {}
                            sel_id = list_reply.get('id', '')
                            send_text(phone, f"You selected: {sel_id}. Please provide further details or type 'menu' to return to the main menu.")

                        else:
                            send_text(phone, "Unsupported interactive message. Type 'menu' to see options.")

                    else:
                        # Handle other message types gracefully
                        send_text(phone, "Message received. Type 'menu' to see available options.")
    except Exception as e:
        # Log server-side; respond 200 to avoid repeated delivery
        print("Error handling webhook:", e)
    return jsonify({'status': 'success'}), 200

if __name__ == '__main__':
    # Bind to 0.0.0.0 for deployment platforms
    app.run(host='0.0.0.0', port=PORT)
