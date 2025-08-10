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

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv('development.env')
    logger.info("✅ Loaded environment variables from development.env")
except ImportError:
    logger.warning("⚠️ python-dotenv not installed. Using system environment variables.")

app = Flask(__name__)

# Database setup
engine = create_engine('sqlite:///database.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

# Multi-provider WhatsApp configuration
WHATSAPP_PROVIDER = os.getenv('WHATSAPP_PROVIDER', 'authkey')  # authkey, wasender, twilio
LOGIN_LINK = "https://wedding-invitation.adkinsfamily.co.za/"

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

def generate_password(length=8):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def send_whatsapp_message(phone, message):
    """Multi-provider WhatsApp message sender"""
    provider = WHATSAPP_PROVIDER.lower()
    
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

        # Format phone number
        if not phone.startswith('+'):
            phone = '+' + phone
        
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
        if not config['api_key']:
            logger.warning("⚠️ WasenderAPI API key not configured")
            return False

        # Format phone number (remove + and spaces, keep country code)
        clean_phone = phone.replace('+', '').replace('-', '').replace(' ', '')
        
        payload = {
            "to": clean_phone,
            "text": message
        }
        
        headers = {
            'Authorization': f'Bearer {config["api_key"]}',
            'Content-Type': 'application/json'
        }
        
        # Correct WasenderAPI endpoint
        api_url = 'https://www.wasenderapi.com/api/send-message'
        
        logger.info(f"📱 Sending via WasenderAPI to {clean_phone}")
        logger.info(f"🔗 Using endpoint: {api_url}")
        
        response = requests.post(api_url, 
                               json=payload,  # Use json parameter instead of data
                               headers=headers)
        
        logger.info(f"📊 Response status: {response.status_code}")
        logger.info(f"📊 Response body: {response.text}")
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success') is not False:  # WasenderAPI might not have 'success' field
                logger.info(f"✅ WasenderAPI message sent: {result}")
                return True
            else:
                logger.error(f"❌ WasenderAPI error: {result}")
                return False
        else:
            logger.error(f"❌ WasenderAPI HTTP error: {response.status_code} - {response.text}")
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
        
        if not phone.startswith('+'):
            phone = '+' + phone
        
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

@app.route("/")
def index():
    return send_from_directory('.', 'index.html')

@app.route("/admin")
def admin():
    return send_from_directory('.', 'admin.html')

@app.route("/api/add_guest", methods=["POST"])
def add_guest():
    data = request.get_json()
    session = Session()

    name = data.get("name")
    phone = data.get("phone")
    logger.info(f"🆕 Adding guest: {name} - {phone}")

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

    logger.info(f"✅ Guest added: {name} - Password: {password}")
    return jsonify({
        "message": f"Guest {name} added successfully",
        "password": password,
        "phone": phone
    })

@app.route("/api/send_invite/<int:guest_id>", methods=["POST"])
def send_invite(guest_id):
    session = Session()
    guest = session.query(Guest).get(guest_id)

    if not guest:
        session.close()
        return jsonify({"error": "Guest not found"}), 404

    logger.info(f"📧 Sending invite to {guest.name} ({guest.phone}) via {WHATSAPP_PROVIDER}")

    message = f"""🌟 You're invited to the best wedding this galaxy has ever experienced! 🚀

Hi {guest.name}! 💍

You're cordially invited to join us for our special day.

📱 RSVP here: {LOGIN_LINK}
🔐 Your password: {guest.password}

📅 Date: Saturday, August 12th, 2025
📍 Venue: The Spectacular Galaxy Gardens
🕐 Time: 4:00 PM - Late Night

Can't wait to celebrate with you! ✨

Love,
The Happy Couple 💕"""

    success = send_whatsapp_message(guest.phone, message)

    if success:
        guest.invite_sent = True
        session.commit()
        logger.info(f"✅ Invitation sent to {guest.name}")
        response = {"message": f"Invitation sent to {guest.name} via {WHATSAPP_PROVIDER}"}
    else:
        logger.error(f"❌ Failed to send invitation to {guest.name}")
        response = {"error": f"Failed to send WhatsApp message via {WHATSAPP_PROVIDER}"}

    session.close()
    return jsonify(response)

@app.route("/api/send_all_invites", methods=["POST"])
def send_all_invites():
    """Bulk send invites to all guests who haven't received one yet"""
    session = Session()
    unsent_guests = session.query(Guest).filter_by(invite_sent=False).all()
    
    if not unsent_guests:
        session.close()
        return jsonify({"message": "All invites already sent!"})
    
    results = {"sent": [], "failed": []}
    
    for guest in unsent_guests:
        logger.info(f"📧 Bulk sending to {guest.name} ({guest.phone})")
        
        message = f"""🌟 You're invited to the best wedding this galaxy has ever experienced! 🚀

Hi {guest.name}! 💍

You're cordially invited to join us for our special day.

📱 RSVP here: {LOGIN_LINK}
🔐 Your password: {guest.password}

📅 Date: Saturday, August 12th, 2025
📍 Venue: The Spectacular Galaxy Gardens
🕐 Time: 4:00 PM - Late Night

Can't wait to celebrate with you! ✨

Love,
The Happy Couple 💕"""
        
        if send_whatsapp_message(guest.phone, message):
            guest.invite_sent = True
            results["sent"].append(guest.name)
            logger.info(f"✅ Bulk invite sent to {guest.name}")
        else:
            results["failed"].append(guest.name)
            logger.error(f"❌ Failed to send bulk invite to {guest.name}")
    
    session.commit()
    session.close()
    
    return jsonify({
        "message": f"Bulk send complete! Sent: {len(results['sent'])}, Failed: {len(results['failed'])}",
        "results": results,
        "provider": WHATSAPP_PROVIDER
    })

@app.route("/api/guests", methods=["GET"])
def get_guests():
    session = Session()
    guests = session.query(Guest).all()
    data = [{
        "id": g.id,
        "name": g.name,
        "phone": g.phone,
        "invite_sent": g.invite_sent,
        "rsvp_status": g.rsvp_status
    } for g in guests]
    session.close()
    logger.info(f"📋 Retrieved {len(data)} guests")
    return jsonify(data)

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    phone = data.get("phone")
    password = data.get("password")
    logger.info(f"🔐 Login attempt: {phone}")

    if not phone or not password:
        return jsonify({"success": False, "error": "Phone and password required"}), 400

    session = Session()
    guest = session.query(Guest).filter_by(phone=phone, password=password).first()
    session.close()

    if guest:
        logger.info(f"✅ Login successful: {guest.name}")
        return jsonify({
            "success": True,
            "guest": {
                "name": guest.name,
                "phone": guest.phone,
                "rsvp_status": guest.rsvp_status
            }
        })

    logger.warning(f"❌ Login failed: {phone}")
    return jsonify({"success": False, "error": "Invalid credentials"}), 401

@app.route("/api/test_whatsapp", methods=["GET"])
def test_whatsapp():
    """Test the configured WhatsApp provider"""
    logger.info(f"🧪 Testing {WHATSAPP_PROVIDER} configuration...")
    
    config = PROVIDERS.get(WHATSAPP_PROVIDER, {})
    
    if WHATSAPP_PROVIDER == 'authkey':
        if config.get('api_key'):
            return jsonify({
                "status": f"Authkey configured ✅",
                "provider": "Authkey",
                "free_messages": "1000/month",
                "api_key": "✅ Set"
            })
        else:
            return jsonify({"error": "Authkey API key not configured"})
    
    elif WHATSAPP_PROVIDER == 'wasender':
        if config.get('api_key'):
            return jsonify({
                "status": f"WasenderAPI configured ✅",
                "provider": "WasenderAPI", 
                "pricing": "$6/month after free trial",
                "api_key": "✅ Set",
                "endpoint": "https://www.wasenderapi.com/api/send-message"
            })
        else:
            return jsonify({"error": "WasenderAPI API key not configured"})
    
    elif WHATSAPP_PROVIDER == 'twilio':
        if all([config.get('account_sid'), config.get('api_key'), config.get('api_secret')]):
            return jsonify({
                "status": f"Twilio configured ✅",
                "provider": "Twilio",
                "limitation": "Sandbox mode - single verified number",
                "account_sid": "✅ Set"
            })
        else:
            return jsonify({"error": "Twilio not fully configured"})
    
    return jsonify({"error": f"Unknown provider: {WHATSAPP_PROVIDER}"})

if __name__ == "__main__":
    logger.info("🚀 Starting Multi-Provider Wedding Invitation Backend...")
    logger.info(f"📱 WhatsApp Provider: {WHATSAPP_PROVIDER.upper()}")
    logger.info(f"🔗 Login link: {LOGIN_LINK}")
    
    # Configuration check
    config = PROVIDERS.get(WHATSAPP_PROVIDER, {})
    if WHATSAPP_PROVIDER == 'authkey':
        if config.get('api_key'):
            logger.info("✅ Authkey configured - 1000 free messages/month!")
        else:
            logger.warning("⚠️ Set AUTHKEY_API_KEY environment variable")
    
    elif WHATSAPP_PROVIDER == 'wasender':
        if config.get('api_key'):
            logger.info("✅ WasenderAPI configured - Free trial then $6/month!")
        else:
            logger.warning("⚠️ Set WASENDER_API_KEY environment variable")
    
    elif WHATSAPP_PROVIDER == 'twilio':
        if all([config.get('account_sid'), config.get('api_key'), config.get('api_secret')]):
            logger.info("✅ Twilio configured - but limited to sandbox mode")
        else:
            logger.warning("⚠️ Twilio configuration incomplete")

    app.run(debug=True, host="0.0.0.0", port=5000)