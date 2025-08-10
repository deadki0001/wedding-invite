from flask import Flask, request, jsonify, send_from_directory
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, Guest
import random
import string
import os
import logging
import requests
import json
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load environment variables - try multiple files
env_files = ['production.env', 'development.env', '.env']
env_loaded = False

try:
    from dotenv import load_dotenv
    for env_file in env_files:
        if os.path.exists(env_file):
            load_dotenv(env_file)
            logger.info(f"✅ Loaded environment variables from {env_file}")
            env_loaded = True
            break
    if not env_loaded:
        logger.warning(f"⚠️ No environment file found. Checked: {env_files}")
except ImportError:
    logger.warning("⚠️ python-dotenv not installed. Using system environment variables.")

app = Flask(__name__)

# Database setup
engine = create_engine('sqlite:///database.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

# Multi-provider WhatsApp configuration
WHATSAPP_PROVIDER = os.getenv('WHATSAPP_PROVIDER', 'wasender').lower()  # Default to wasender
LOGIN_LINK = os.getenv('WEDDING_LOGIN_URL', "https://wedding-invitation.adkinsfamily.co.za/")

logger.info(f"🔧 Environment check:")
logger.info(f"   WHATSAPP_PROVIDER = {WHATSAPP_PROVIDER}")
logger.info(f"   WASENDER_API_KEY = {'SET' if os.getenv('WASENDER_API_KEY') else 'NOT SET'}")
logger.info(f"   AUTHKEY_API_KEY = {'SET' if os.getenv('AUTHKEY_API_KEY') else 'NOT SET'}")

# Provider configurations
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

# Phone normalization helper
def normalize_phone(phone: str) -> str:
    """Ensure phone number includes country code (+27 for SA if missing)."""
    if not phone:
        return phone
    phone = phone.strip().replace(" ", "").replace("-", "")
    if phone.startswith("0"):
        return "+27" + phone[1:]
    elif not phone.startswith("+"):
        return "+27" + phone
    return phone

def generate_password(length=8):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def send_whatsapp_message(phone, message):
    """Multi-provider WhatsApp message sender"""
    provider = WHATSAPP_PROVIDER.lower()
    logger.info(f"🔧 Using provider: {provider}")
    
    if provider == 'authkey':
        return send_authkey_message(phone, message)
    elif provider == 'wasender':
        return send_wasender_message(phone, message)
    elif provider == 'twilio':
        return send_twilio_message(phone, message)
    else:
        logger.error(f"❌ Unknown provider: {provider}")
        return False

def send_authkey_message(phone, message):
    """Send via Authkey API (1000 free messages/month)"""
    try:
        config = PROVIDERS['authkey']
        if not config['api_key']:
            logger.warning("⚠️ Authkey API key not configured")
            return False

        phone = normalize_phone(phone)
        payload = {
            "authkey": config['api_key'],
            "mobiles": phone,
            "message": message,
            "sender": config['sender_id'],
            "route": "4",  # WhatsApp route
            "country": "0"
        }
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        logger.info(f"📱 Sending via Authkey to {phone}")
        response = requests.post(config['api_url'], data=payload, headers=headers)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('Status') == 'success':
                logger.info(f"✅ Authkey message sent: {result}")
                return True
            else:
                logger.error(f"❌ Authkey error: {result}")
                return False
        else:
            logger.error(f"❌ Authkey HTTP error: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"❌ Authkey exception: {e}", exc_info=True)
        return False

def send_wasender_message(phone, message):
    """Send via WasenderAPI"""
    try:
        config = PROVIDERS['wasender']
        api_key = config['api_key']
        if not api_key:
            logger.warning("⚠️ WasenderAPI API key not configured")
            return False

        clean_phone = normalize_phone(phone).replace('+', '')
        payload = {"to": clean_phone, "text": message}
        headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
        api_url = config['api_url']
        
        logger.info(f"📱 Sending via WasenderAPI to {clean_phone}")
        response = requests.post(api_url, json=payload, headers=headers)
        logger.info(f"📊 Response status: {response.status_code}")
        logger.info(f"📊 Response body: {response.text}")
        
        if response.status_code == 200:
            try:
                result = response.json()
                logger.info(f"✅ WasenderAPI message sent: {result}")
                return True
            except json.JSONDecodeError:
                if 'success' in response.text.lower():
                    logger.info(f"✅ WasenderAPI message sent (plain text)")
                    return True
                else:
                    logger.error(f"❌ WasenderAPI unexpected response: {response.text}")
                    return False
        else:
            logger.error(f"❌ WasenderAPI HTTP error: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"❌ WasenderAPI exception: {e}", exc_info=True)
        return False

def send_twilio_message(phone, message):
    """Send via Twilio (fallback)"""
    try:
        from twilio.rest import Client
        config = PROVIDERS['twilio']
        if not all([config['account_sid'], config['api_key'], config['api_secret']]):
            logger.warning("⚠️ Twilio not configured")
            return False
        client = Client(config['api_key'], config['api_secret'], config['account_sid'])
        phone = normalize_phone(phone)
        to_whatsapp = f'whatsapp:{phone}'
        message_obj = client.messages.create(
            body=message,
            from_=config['whatsapp_number'],
            to=to_whatsapp
        )
        logger.info(f"✅ Twilio message sent: SID = {message_obj.sid}")
        return True
    except Exception as e:
        logger.error(f"❌ Twilio exception: {e}", exc_info=True)
        return False

# Routes
@app.route("/")
def index():
    return send_from_directory('.', 'index.html')

@app.route("/admin")
def admin():
    return send_from_directory('.', 'admin.html')

@app.route("/admin.html")
def admin_html():
    return send_from_directory('.', 'admin.html')

@app.route("/main.html")
def main():
    return send_from_directory('.', 'main.html')

@app.route("/api/add_guest", methods=["POST"])
def add_guest():
    data = request.get_json()
    session = Session()
    name = data.get("name")
    phone = normalize_phone(data.get("phone"))
    logger.info(f"🆕 Adding guest: {name} - {phone}")

    if not name or not phone:
        session.close()
        return jsonify({"error": "Name and phone are required"}), 400
    if session.query(Guest).filter_by(phone=phone).first():
        session.close()
        return jsonify({"error": "Guest already exists"}), 409

    password = generate_password()
    guest = Guest(name=name, phone=phone, password=password)
    session.add(guest)
    session.commit()
    session.close()
    logger.info(f"✅ Guest added: {name} - Password: {password}")
    return jsonify({"message": f"Guest {name} added successfully", "password": password, "phone": phone})

@app.route("/api/guests", methods=["GET"])
def get_guests():
    session = Session()
    guests = session.query(Guest).all()
    data = [{
        "id": g.id,
        "name": g.name,
        "phone": g.phone,
        "password": g.password,
        "invite_sent": g.invite_sent,
        "rsvp_status": g.rsvp_status
    } for g in guests]
    session.close()
    logger.info(f"📋 Retrieved {len(data)} guests")
    return jsonify(data)

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    phone = normalize_phone(data.get("phone"))
    password = data.get("password")
    logger.info(f"🔐 Login attempt: {phone}")

    if not phone or not password:
        return jsonify({"success": False, "error": "Phone and password required"}), 400

    session = Session()
    guest = session.query(Guest).filter_by(phone=phone, password=password).first()
    session.close()
    if guest:
        logger.info(f"✅ Login successful: {guest.name}")
        return jsonify({"success": True, "guest": {"name": guest.name, "phone": guest.phone, "rsvp_status": guest.rsvp_status}})
    logger.warning(f"❌ Login failed: {phone}")
    return jsonify({"success": False, "error": "Invalid credentials"}), 401

@app.route("/api/rsvp", methods=["POST"])
def rsvp():
    data = request.get_json()
    phone = normalize_phone(data.get("phone"))
    status = data.get("status")
    if not phone or status not in ['accepted', 'declined']:
        return jsonify({"success": False, "error": "Invalid data"}), 400
    session = Session()
    guest = session.query(Guest).filter_by(phone=phone).first()
    if not guest:
        session.close()
        return jsonify({"success": False, "error": "Guest not found"}), 404
    guest.rsvp_status = status
    session.commit()
    session.close()
    logger.info(f"✅ RSVP updated: {guest.name} - {status}")
    return jsonify({"success": True, "message": f"RSVP updated to {status}"})

@app.route("/api/test_whatsapp", methods=["GET"])
def test_whatsapp():
    logger.info(f"🧪 Testing {WHATSAPP_PROVIDER} configuration...")
    config = PROVIDERS.get(WHATSAPP_PROVIDER, {})
    if WHATSAPP_PROVIDER == 'authkey':
        if config.get('api_key'):
            return jsonify({"status": f"Authkey configured ✅", "provider": "Authkey", "free_messages": "1000/month", "api_key": "✅ Set"})
        else:
            return jsonify({"error": "Authkey API key not configured"})
    elif WHATSAPP_PROVIDER == 'wasender':
        if config.get('api_key'):
            return jsonify({"status": f"WasenderAPI configured ✅", "provider": "WasenderAPI", "pricing": "$6/month after free trial", "api_key": "✅ Set", "endpoint": "https://www.wasenderapi.com/api/send-message"})
        else:
            return jsonify({"error": "WasenderAPI API key not configured"})
    elif WHATSAPP_PROVIDER == 'twilio':
        if all([config.get('account_sid'), config.get('api_key'), config.get('api_secret')]):
            return jsonify({"status": f"Twilio configured ✅", "provider": "Twilio", "limitation": "Sandbox mode - single verified number", "account_sid": "✅ Set"})
        else:
            return jsonify({"error": "Twilio not fully configured"})
    return jsonify({"error": f"Unknown provider: {WHATSAPP_PROVIDER}"})

if __name__ == "__main__":
    logger.info("🚀 Starting Multi-Provider Wedding Invitation Backend...")
    logger.info(f"📱 WhatsApp Provider: {WHATSAPP_PROVIDER.upper()}")
    logger.info(f"🔗 Login link: {LOGIN_LINK}")
    port = int(os.getenv('PORT', 5000))
    host = os.getenv('HOST', '0.0.0.0')
    debug = os.getenv('FLASK_ENV') != 'production'
    logger.info(f"🌐 Starting server on {host}:{port} (debug={debug})")
    app.run(debug=debug, host=host, port=port)
