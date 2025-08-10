from flask import Flask, request, jsonify, send_from_directory, redirect
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, Guest
import random
import string
import os
import logging
import requests
from datetime import datetime

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv
    load_dotenv('development.env')
    logger.info("✅ Loaded environment variables from development.env")
except ImportError:
    logger.warning("⚠️ python-dotenv not installed.")

app = Flask(__name__)

engine = create_engine('sqlite:///database.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

WHATSAPP_PROVIDER = os.getenv('WHATSAPP_PROVIDER', 'authkey')
LOGIN_LINK = os.getenv('WEDDING_LOGIN_URL', 'https://wedding-invitation.adkinsfamily.co.za/')

PROVIDERS = {
    'authkey': {
        'api_key': os.getenv('AUTHKEY_API_KEY'),
        'api_url': 'https://api.authkey.io/request',
        'sender_id': os.getenv('AUTHKEY_SENDER_ID', '91XXXXXXXXXX')
    },
    'wasender': {
        'api_key': os.getenv('WASENDER_API_KEY'),
        'api_url': 'https://www.wasenderapi.com/api/send-message'
    },
    'twilio': {
        'account_sid': os.getenv('TWILIO_ACCOUNT_SID'),
        'api_key': os.getenv('TWILIO_API_KEY_SID'),
        'api_secret': os.getenv('TWILIO_API_KEY_SECRET'),
        'whatsapp_number': 'whatsapp:+14155238886'
    }
}

def generate_password(length=8):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

# ---------------- WhatsApp Senders ----------------
def send_whatsapp_message(phone, message):
    provider = WHATSAPP_PROVIDER.lower()
    if provider == 'authkey':
        return send_authkey_message(phone, message)
    elif provider == 'wasender':
        return send_wasender_message(phone, message)
    elif provider == 'twilio':
        return send_twilio_message(phone, message)
    return False

def send_authkey_message(phone, message):
    try:
        config = PROVIDERS['authkey']
        if not config['api_key']:
            return False
        if not phone.startswith('+'):
            phone = '+' + phone
        payload = {
            "authkey": config['api_key'],
            "mobiles": phone,
            "message": message,
            "sender": config['sender_id'],
            "route": "4",
            "country": "0"
        }
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        r = requests.post(config['api_url'], data=payload, headers=headers)
        if r.status_code == 200 and r.json().get('Status') == 'success':
            return True
    except Exception as e:
        logger.error(f"Authkey send error: {e}")
    return False

def send_wasender_message(phone, message):
    try:
        config = PROVIDERS['wasender']
        if not config['api_key']:
            return False
        clean_phone = phone.replace('+', '').replace('-', '').replace(' ', '')
        payload = {"to": clean_phone, "text": message}
        headers = {
            'Authorization': f'Bearer {config["api_key"]}',
            'Content-Type': 'application/json'
        }
        r = requests.post(config['api_url'], json=payload, headers=headers)
        if r.status_code == 200:
            return True
    except Exception as e:
        logger.error(f"Wasender send error: {e}")
    return False

def send_twilio_message(phone, message):
    try:
        from twilio.rest import Client
        config = PROVIDERS['twilio']
        client = Client(config['api_key'], config['api_secret'], config['account_sid'])
        if not phone.startswith('+'):
            phone = '+' + phone
        client.messages.create(
            body=message,
            from_=config['whatsapp_number'],
            to=f'whatsapp:{phone}'
        )
        return True
    except Exception as e:
        logger.error(f"Twilio send error: {e}")
    return False

# ---------------- Routes ----------------
@app.route("/")
def index():
    return send_from_directory('.', 'index.html')

@app.route("/admin.html")
def admin_html_redirect():
    return redirect("/admin", code=302)

@app.route("/admin")
def admin():
    return send_from_directory('.', 'admin.html')

@app.route("/api/test_whatsapp")
def test_whatsapp():
    provider = WHATSAPP_PROVIDER.lower()
    config = PROVIDERS.get(provider, {})
    if not config:
        return jsonify({"error": "Invalid provider"}), 400
    return jsonify({
        "status": "OK",
        "provider": provider,
        "api_key": config.get('api_key', 'Not set')
    })

@app.route("/api/guests")
def get_guests():
    session = Session()
    guests = session.query(Guest).all()
    session.close()
    return jsonify([{
        "id": g.id,
        "name": g.name,
        "phone": g.phone,
        "password": g.password,
        "invite_sent": g.invite_sent,
        "rsvp_status": g.rsvp_status
    } for g in guests])

@app.route("/api/add_guest", methods=["POST"])
def add_guest():
    data = request.get_json()
    name = data.get("name")
    phone = data.get("phone")
    session = Session()
    if not name or not phone:
        return jsonify({"error": "Name and phone are required"}), 400
    if session.query(Guest).filter_by(phone=phone).first():
        session.close()
        return jsonify({"error": "Guest already exists"}), 409
    password = generate_password()
    guest = Guest(name=name, phone=phone, password=password)
    session.add(guest)
    session.commit()
    session.close()
    return jsonify({"message": "Guest added", "password": password})

@app.route("/api/send_invite/<int:guest_id>", methods=["POST"])
def send_invite(guest_id):
    session = Session()
    guest = session.query(Guest).get(guest_id)
    if not guest:
        return jsonify({"error": "Guest not found"}), 404
    message = f"""Hi {guest.name}, RSVP here: {LOGIN_LINK} Password: {guest.password}"""
    if send_whatsapp_message(guest.phone, message):
        guest.invite_sent = True
        session.commit()
        session.close()
        return jsonify({"message": "Invite sent"})
    session.close()
    return jsonify({"error": "Failed to send"}), 500

@app.route("/api/send_all_invites", methods=["POST"])
def send_all_invites():
    session = Session()
    unsent = session.query(Guest).filter_by(invite_sent=False).all()
    results = {"sent": [], "failed": []}
    for guest in unsent:
        message = f"""Hi {guest.name}, RSVP here: {LOGIN_LINK} Password: {guest.password}"""
        if send_whatsapp_message(guest.phone, message):
            guest.invite_sent = True
            results["sent"].append(guest.name)
        else:
            results["failed"].append(guest.name)
    session.commit()
    session.close()
    return jsonify({"message": "Bulk send complete", "results": results})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
