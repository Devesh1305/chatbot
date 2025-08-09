from flask import Flask, request, jsonify
from pymongo import MongoClient
from datetime import datetime
import requests
import os

# Environment variables (set these securely on your host/Render dashboard)
WHATSAPP_TOKEN = os.environ.get('WHATSAPP_TOKEN', 'YOUR_WHATSAPP_TOKEN')
PHONE_NUMBER_ID = os.environ.get('PHONE_NUMBER_ID', 'YOUR_PHONE_NUMBER_ID')
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN', 'YOUR_VERIFY_TOKEN')
MONGODB_URI = os.environ.get('MONGODB_URI', 'mongodb+srv://user:pass@cluster/dbname')
PORT = int(os.environ.get('PORT', 8080))

app = Flask(__name__)

# Setup MongoDB connection
mongo_client = MongoClient(MONGODB_URI)
db = mongo_client['whatsapp_chatbot']
conversations = db['conversations']

WA_API_URL = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"

# Helper to send text messages
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

# Helper to send interactive button messages
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

# Retrieve last conversation state for a user
def get_state(phone):
    record = conversations.find_one({'customer_number': phone}, sort=[('timestamp', -1)])
    if record and 'state' in record:
        return record['state']
    return None

# Save conversation state
def set_state(phone, state):
    conversations.insert_one({
        'customer_number': phone,
        'timestamp': datetime.utcnow(),
        'state': state,
        'direction': 'state_update'
    })

# Webhook verification endpoint
@app.route('/webhook', methods=['GET'])
def verify():
    if request.args.get('hub.verify_token') == VERIFY_TOKEN:
        return request.args.get('hub.challenge'), 200
    return "Verification failed", 403

# Webhook message handler
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
                    msg_id = msg['id']

                    # Save incoming message
                    conversations.insert_one({
                        'customer_number': phone,
                        'message_id': msg_id,
                        'message_text': msg.get('text', {}).get('body') or '',
                        'timestamp': datetime.utcfromtimestamp(timestamp),
                        'direction': 'incoming',
                        'state': get_state(phone)
                    })

                    # Determine conversation state and type of message
                    state = get_state(phone)
                    mtype = msg['type']

                    # Handle flow by state and input type
                    if state is None:
                        # Start conversation, send welcome with free text prompt (step 1)
                        send_text(phone, "Welcome to GITAM DEMO ChatBot")
                        set_state(phone, 'step_2')
                    elif state == 'step_2':
                        # Step 2 expects free text greeting/acknowledgement but we proceed to main menu
                        send_text(phone, "INS KALINGA Help Desk.\n\nHello Sir/Ma'am,\n\nGreetings of the day\n\nWelcome to the INS KALINGA Help Desk.\n\nPlease select one of the following questions as per your query.")
                        set_state(phone, 'step_3')
                    elif state == 'step_3':
                        # Expect user to select one from main menu buttons (so send menu buttons if text received)
                        if mtype == 'text':
                            # Send buttons menu for main categories
                            buttons = [
                                ('3a', 'Accommodation'),
                                ('3b', 'Facilities'),
                                ('3c', 'Institutes'),
                                ('3d', 'Complaints & Emergencies'),
                                ('3e', 'Medical'),
                                ('3f', 'Educational'),
                                ('3g', 'Daily Essentials')
                            ]
                            send_buttons(phone, 'INS KALINGA Help Desk', 'Please select one of the following questions as per your query.', buttons)
                        elif mtype == 'interactive':
                            # Handle button press selecting submenu
                            button_reply = msg['interactive']['button_reply']['id']
                            if button_reply.startswith('3'):
                                # Save selection and send submenu accordingly
                                send_submenu(phone, button_reply)
                                set_state(phone, button_reply)
                            else:
                                send_text(phone, "Invalid selection, please try again.")
                    elif state in ['3a', '3b', '3c', '3d', '3e', '3f', '3g']:
                        # Submenus expect button replies or final free-text input (step 100)
                        if mtype == 'text':
                            # Received free text at this point, potentially step 100, handle or acknowledge
                            send_text(phone, "Thank you for your input. We will get back to you shortly.")
                            set_state(phone, 'complete')
                        elif mtype == 'interactive':
                            button_reply = msg['interactive']['button_reply']['id']
                            # Validate button reply for submenu
                            send_text(phone, f"You selected: {button_reply}. Please provide further details or type your message.")
                            set_state(phone, 'step_100')
                    elif state == 'step_100' or state == 'complete':
                        # Catch-all state for free text after submenu selection
                        send_text(phone, "Thank you for your response. If you need further assistance, type 'menu' to return to the main menu.")
                        if msg.get('text', {}).get('body', '').lower() == 'menu':
                            set_state(phone, 'step_3')
                            # resend main menu buttons
                            buttons = [
                                ('3a', 'Accommodation'),
                                ('3b', 'Facilities'),
                                ('3c', 'Institutes'),
                                ('3d', 'Complaints & Emergencies'),
                                ('3e', 'Medical'),
                                ('3f', 'Educational'),
                                ('3g', 'Daily Essentials')
                            ]
                            send_buttons(phone, 'INS KALINGA Help Desk', 'Please select one of the following questions as per your query.', buttons)
                    else:
                        # Unknown state fallback
                        send_text(phone, "Sorry, something went wrong. Let's start over. Welcome to GITAM DEMO ChatBot")
                        set_state(phone, None)

    return jsonify({'status': 'success'}), 200

def send_submenu(phone, submenu_id):
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)
