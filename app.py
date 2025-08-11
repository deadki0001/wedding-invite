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
import time
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
WHATSAPP_PROVIDER = os.getenv('WHATSAPP_PROVIDER', 'wasender').lower()
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

# ---------- Helpers ----------
def normalize_phone(phone: str) -> str:
    """Normalize phone numbers - ensure proper format for WasenderAPI"""
    if not phone:
        return ""
    
    # Clean the phone number
    phone = phone.strip().replace(" ", "").replace("-", "")
    
    # Handle different input formats
    if phone.startswith("+27"):
        return phone  # Already correct: +27646191448
    elif phone.startswith("27"):
        return "+" + phone  # Add +: +27646191448
    elif phone.startswith("0"):
        return "+27" + phone[1:]  # Convert: +27646191448
    else:
        return "+27" + phone  # Assume SA number: +27646191448

def generate_password(length=8):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

# ---------- WhatsApp Senders ----------
def send_whatsapp_message(phone, message):
    try:
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
    except Exception as e:
        logger.error(f"❌ send_whatsapp_message exception: {e}", exc_info=True)
        return False

def send_authkey_message(phone, message):
    try:
        config = PROVIDERS['authkey']
        if not config['api_key']:
            logger.warning("⚠️ Authkey API key not configured")
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
    """Fixed WasenderAPI implementation with proper phone formatting"""
    try:
        config = PROVIDERS['wasender']
        api_key = config['api_key']

        if not api_key:
            logger.warning("⚠️ WasenderAPI API key not configured")
            return False

        # Fix phone number format - WasenderAPI needs country code without +
        clean_phone = phone.replace('+', '').replace('-', '').replace(' ', '')
        
        # Ensure it starts with country code (27 for South Africa)
        if clean_phone.startswith('0'):
            clean_phone = '27' + clean_phone[1:]  # Convert 0646191448 to 27646191448
        elif not clean_phone.startswith('27'):
            clean_phone = '27' + clean_phone  # Add country code if missing

        # Use the correct endpoint and payload structure
        api_url = 'https://www.wasenderapi.com/api/send-message'
        payload = {"to": clean_phone, "text": message}
        
        headers = {
            'Authorization': f'Bearer {api_key}', 
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

        logger.info(f"📱 Sending via WasenderAPI to {clean_phone}")
        logger.info(f"🔧 Using URL: {api_url}")
        logger.info(f"🔧 Payload: {payload}")
        
        response = requests.post(api_url, json=payload, headers=headers, timeout=30)
        logger.info(f"📊 Response status: {response.status_code}")
        logger.info(f"📊 Response body: {response.text}")

        if response.status_code == 200:
            try:
                result = response.json()
                logger.info(f"✅ WasenderAPI message sent: {result}")
                return True
            except json.JSONDecodeError:
                # Check for success in plain text
                if any(keyword in response.text.lower() for keyword in ['success', 'sent', 'delivered', 'queued']):
                    logger.info("✅ WasenderAPI message sent (plain text response)")
                    return True
                else:
                    logger.error(f"❌ Unexpected response format: {response.text}")
                    return False
                    
        elif response.status_code == 422:
            logger.error(f"❌ WasenderAPI validation error (422): {response.text}")
            logger.error(f"❌ Phone format issue - tried: {clean_phone}")
            return False
            
        elif response.status_code == 429:
            try:
                error_data = response.json()
                retry_after = error_data.get('retry_after', 60)
                logger.error(f"❌ WasenderAPI rate limited - retry after {retry_after} seconds")
            except:
                logger.error("❌ WasenderAPI rate limited - free trial: 1 message per minute")
            return False
            
        elif response.status_code == 401:
            logger.error("❌ WasenderAPI unauthorized - check API key")
            return False
            
        else:
            logger.error(f"❌ WasenderAPI HTTP error {response.status_code}: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"❌ WasenderAPI exception: {e}", exc_info=True)
        return False

def send_twilio_message(phone, message):
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

# ---------- Routes ----------
@app.route("/")
def index():
    return send_from_directory('.', 'index.html')

@app.route("/admin")
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

@app.route("/api/send_invite/<int:guest_id>", methods=["POST"])
def send_invite(guest_id):
    session = Session()
    guest = session.get(Guest, guest_id)

    if not guest:
        session.close()
        return jsonify({"error": "Guest not found"}), 404

    # Store guest details before potential session closure
    guest_name = guest.name
    guest_phone = guest.phone
    guest_password = guest.password
    
    logger.info(f"📧 Sending invite to {guest_name} ({guest_phone}) via {WHATSAPP_PROVIDER}")

    message = f"""🌟 You're invited to the best wedding this galaxy has ever experienced! 🚀

Hi {guest_name}! 💍

You're cordially invited to join us for our special day.

📱 RSVP: {LOGIN_LINK}
📱 Username: Your cell number
🔐 Your password: {guest_password}

📅 Date: Sunday, September 28th, 2025
📍 Venue: Carmel Coastal Retreat
🕐 Time: 12:00 PM - Midday

Can't wait to celebrate with you! ✨

Love,
The Happy Couple 💕"""

    try:
        success = send_whatsapp_message(guest_phone, message)
    except Exception as e:
        logger.error(f"❌ Exception while sending invite: {e}", exc_info=True)
        session.close()
        return jsonify({"error": "Internal server error while sending invite"}), 500

    if success:
        guest.invite_sent = True
        session.commit()
        session.close()
        logger.info(f"✅ Invitation sent to {guest_name}")
        return jsonify({"message": f"Invitation sent to {guest_name} via {WHATSAPP_PROVIDER}"})
    else:
        session.close()
        logger.error(f"❌ Failed to send invitation to {guest_name}")
        return jsonify({"error": f"Failed to send WhatsApp message via {WHATSAPP_PROVIDER}"}), 500

@app.route("/api/send_invite_with_delay/<int:guest_id>", methods=["POST"])
def send_invite_with_delay(guest_id):
    """Send invite with automatic delay handling for free trial rate limits"""
    session = Session()
    guest = session.get(Guest, guest_id)

    if not guest:
        session.close()
        return jsonify({"error": "Guest not found"}), 404

    # Store guest details before potential session closure
    guest_name = guest.name
    guest_phone = guest.phone
    guest_password = guest.password
    
    logger.info(f"📧 Sending invite to {guest_name} ({guest_phone}) via {WHATSAPP_PROVIDER}")

    message = f"""🌟 You're invited to the best wedding this galaxy has ever experienced! 🚀

Hi {guest_name}! 💍

You're cordially invited to join us for our special day.

📱 RSVP: {LOGIN_LINK}
📱 Username: Your cell number
🔐 Your password: {guest_password}

📅 Date: Sunday, September 28th, 2025
📍 Venue: Carmel Coastal Retreat
🕐 Time: 12:00 PM - Midday

Can't wait to celebrate with you! ✨

Love,
The Happy Couple 💕"""

    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            success = send_whatsapp_message(guest_phone, message)
            
            if success:
                guest.invite_sent = True
                session.commit()
                session.close()
                logger.info(f"✅ Invitation sent to {guest_name}")
                return jsonify({"message": f"Invitation sent to {guest_name} via {WHATSAPP_PROVIDER}"})
            else:
                retry_count += 1
                if retry_count < max_retries:
                    logger.info(f"⏳ Retrying in 65 seconds (attempt {retry_count + 1}/{max_retries})...")
                    time.sleep(65)  # Wait just over 1 minute for rate limit reset
                    continue
                    
        except Exception as e:
            logger.error(f"❌ Exception while sending invite: {e}", exc_info=True)
            break
    
    session.close()
    return jsonify({"error": f"Failed to send invitation after {max_retries} attempts"}), 500

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
        return jsonify({"success": True, "guest": {
            "name": guest.name,
            "phone": guest.phone,
            "rsvp_status": guest.rsvp_status
        }})
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
            return jsonify({"status": "Authkey configured ✅", "provider": "Authkey", "free_messages": "1000/month", "api_key": "✅ Set"})
        else:
            return jsonify({"error": "Authkey API key not configured"})

    elif WHATSAPP_PROVIDER == 'wasender':
        if config.get('api_key'):
            return jsonify({"status": "WasenderAPI configured ✅", "provider": "WasenderAPI", "pricing": "$6/month after free trial", "api_key": "✅ Set"})
        else:
            return jsonify({"error": "WasenderAPI API key not configured"})

    elif WHATSAPP_PROVIDER == 'twilio':
        if all([config.get('account_sid'), config.get('api_key'), config.get('api_secret')]):
            return jsonify({"status": "Twilio configured ✅", "provider": "Twilio", "limitation": "Sandbox mode - single verified number", "account_sid": "✅ Set"})
        else:
            return jsonify({"error": "Twilio not fully configured"})

    return jsonify({"error": f"Unknown provider: {WHATSAPP_PROVIDER}"})

@app.route("/api/test_whatsapp_detailed", methods=["GET"])
def test_whatsapp_detailed():
    """Enhanced diagnostic endpoint for WasenderAPI"""
    logger.info(f"🧪 Detailed testing {WHATSAPP_PROVIDER} configuration...")
    
    if WHATSAPP_PROVIDER != 'wasender':
        return jsonify({"error": "This detailed test is for WasenderAPI only"})
    
    config = PROVIDERS.get('wasender', {})
    api_key = config.get('api_key')
    api_url = config.get('api_url')
    
    if not api_key:
        return jsonify({"error": "WasenderAPI API key not configured"})
    
    # Test multiple endpoints
    test_results = []
    endpoints_to_test = [
        'https://www.wasenderapi.com/api/send-message',
        'https://api.wasenderapi.com/v1/send-message',
        'https://wasenderapi.com/api/v1/messages/send',
        'https://www.wasenderapi.com/api/status'
    ]
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    
    for endpoint in endpoints_to_test:
        try:
            response = requests.get(endpoint, headers=headers, timeout=10)
            
            result = {
                "endpoint": endpoint,
                "status_code": response.status_code,
                "content_type": response.headers.get('content-type', 'unknown'),
                "is_html": response.headers.get('content-type', '').startswith('text/html'),
                "response_preview": response.text[:100] + "..." if len(response.text) > 100 else response.text
            }
            
            if result["is_html"]:
                result["issue"] = "Returns HTML instead of JSON - possible auth issue"
            elif response.status_code == 200:
                result["status"] = "✅ Accessible"
            elif response.status_code == 401:
                result["issue"] = "❌ Unauthorized - check API key"
            elif response.status_code == 404:
                result["issue"] = "❌ Not found - endpoint may not exist"
            else:
                result["issue"] = f"❌ HTTP {response.status_code}"
                
            test_results.append(result)
            
        except Exception as e:
            test_results.append({
                "endpoint": endpoint,
                "error": str(e),
                "issue": "❌ Connection failed"
            })
    
    return jsonify({
        "provider": "WasenderAPI",
        "api_key_configured": "✅ Yes",
        "configured_url": api_url,
        "endpoint_tests": test_results,
        "recommendations": [
            "Check if your WhatsApp session is connected in WasenderAPI dashboard",
            "Verify your API key is active and not expired", 
            "Ensure your account has sufficient credits/is not suspended",
            "Try reconnecting your WhatsApp session if endpoints return HTML"
        ]
    })

@app.route("/api/test_send", methods=["POST"])
def test_send():
    """Test sending a message to a specific number"""
    data = request.get_json()
    phone = data.get('phone')
    
    if not phone:
        return jsonify({"error": "Phone number required"}), 400
    
    phone = normalize_phone(phone)
    test_message = "🧪 Test message from wedding invitation system. If you receive this, the system is working!"
    
    logger.info(f"🧪 Sending test message to {phone}")
    success = send_whatsapp_message(phone, test_message)
    
    if success:
        return jsonify({"success": True, "message": f"Test message sent to {phone}"})
    else:
        return jsonify({"success": False, "error": "Failed to send test message"}), 500

@app.route("/api/delete_guest/<int:guest_id>", methods=["DELETE"])
def delete_guest(guest_id):
    """Delete a specific guest by ID"""
    session = Session()
    guest = session.get(Guest, guest_id)
    
    if not guest:
        session.close()
        return jsonify({"error": "Guest not found"}), 404
    
    guest_name = guest.name
    session.delete(guest)
    session.commit()
    session.close()
    
    logger.info(f"🗑️ Deleted guest: {guest_name} (ID: {guest_id})")
    return jsonify({"message": f"Guest {guest_name} deleted successfully"})

@app.route("/api/delete_all_guests", methods=["DELETE"])
def delete_all_guests():
    """Delete ALL guests - use with caution!"""
    session = Session()
    guest_count = session.query(Guest).count()
    
    if guest_count == 0:
        session.close()
        return jsonify({"message": "No guests to delete"})
    
    session.query(Guest).delete()
    session.commit()
    session.close()
    
    logger.info(f"🗑️ Deleted ALL {guest_count} guests from database")
    return jsonify({"message": f"Successfully deleted all {guest_count} guests"})

@app.route("/api/delete_test_guests", methods=["DELETE"])
def delete_test_guests():
    """Delete guests that look like test users"""
    session = Session()
    
    # Define patterns that indicate test users
    test_patterns = [
        'test', 'Test', 'TEST',
        'demo', 'Demo', 'DEMO',
        'example', 'Example', 'EXAMPLE',
        'dummy', 'Dummy', 'DUMMY',
        'sample', 'Sample', 'SAMPLE',
        'fake', 'Fake', 'FAKE'
    ]
    
    deleted_guests = []
    
    # Find guests with test-like names
    for pattern in test_patterns:
        test_guests = session.query(Guest).filter(Guest.name.contains(pattern)).all()
        for guest in test_guests:
            deleted_guests.append({"name": guest.name, "phone": guest.phone})
            session.delete(guest)
    
    # Also delete guests with obvious test phone numbers
    test_phone_patterns = ['1234567', '0000000', '1111111', '9999999']
    for pattern in test_phone_patterns:
        test_guests = session.query(Guest).filter(Guest.phone.contains(pattern)).all()
        for guest in test_guests:
            if {"name": guest.name, "phone": guest.phone} not in deleted_guests:
                deleted_guests.append({"name": guest.name, "phone": guest.phone})
                session.delete(guest)
    
    session.commit()
    session.close()
    
    logger.info(f"🗑️ Deleted {len(deleted_guests)} test guests")
    return jsonify({
        "message": f"Deleted {len(deleted_guests)} test guests",
        "deleted_guests": deleted_guests
    })

if __name__ == "__main__":
    logger.info("🚀 Starting Multi-Provider Wedding Invitation Backend...")
    logger.info(f"📱 WhatsApp Provider: {WHATSAPP_PROVIDER.upper()}")
    logger.info(f"🔗 Login link: {LOGIN_LINK}")

    config = PROVIDERS.get(WHATSAPP_PROVIDER, {})
    port = int(os.getenv('PORT', 5000))
    host = os.getenv('HOST', '0.0.0.0')
    debug = os.getenv('FLASK_ENV') != 'production'

    logger.info(f"🌐 Starting server on {host}:{port} (debug={debug})")
    app.run(debug=debug, host=host, port=port)