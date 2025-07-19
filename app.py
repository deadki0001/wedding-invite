from flask import Flask, request, jsonify, send_from_directory
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, Guest
import random
import string
import os
import logging
from twilio.rest import Client

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv('development.env')  # Load your specific env file
    logger.info("✅ Loaded environment variables from development.env")
except ImportError:
    logger.warning("⚠️ python-dotenv not installed. Using system environment variables.")

app = Flask(__name__)

# Database setup
engine = create_engine('sqlite:///database.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

# Twilio Configuration (Using API Keys - new format)
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_API_KEY_SID = os.getenv('TWILIO_API_KEY_SID')
TWILIO_API_KEY_SECRET = os.getenv('TWILIO_API_KEY_SECRET')
TWILIO_WHATSAPP_NUMBER = 'whatsapp:+14155238886'

# Your wedding invitation URL
LOGIN_LINK = "https://wedding-invitation.adkinsfamily.co.za/"

# Initialize Twilio client with API Key
client = None
if TWILIO_ACCOUNT_SID and TWILIO_API_KEY_SID and TWILIO_API_KEY_SECRET:
    client = Client(TWILIO_API_KEY_SID, TWILIO_API_KEY_SECRET, TWILIO_ACCOUNT_SID)
    logger.info("✅ Twilio client initialized successfully")
else:
    logger.warning("⚠️ Twilio API Key not configured")
    logger.warning(f"   Account SID: {'✅' if TWILIO_ACCOUNT_SID else '❌'}")
    logger.warning(f"   API Key SID: {'✅' if TWILIO_API_KEY_SID else '❌'}")
    logger.warning(f"   API Key Secret: {'✅' if TWILIO_API_KEY_SECRET else '❌'}")

# Generate a random password
def generate_password(length=8):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

# Send WhatsApp message via Twilio
def send_whatsapp_twilio(phone, message):
    if not client:
        logger.warning("⚠️ Twilio not configured - would send: %s", message)
        return False

    try:
        if not phone.startswith('+'):
            phone = '+' + phone

        to_whatsapp = f'whatsapp:{phone}'
        logger.info(f"📱 Sending WhatsApp to {to_whatsapp} with message: {message}")

        message_obj = client.messages.create(
            body=message,
            from_=TWILIO_WHATSAPP_NUMBER,
            to=to_whatsapp
        )

        logger.info(f"✅ Message sent successfully: SID = {message_obj.sid}")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to send WhatsApp message to {phone}: {e}", exc_info=True)
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

    logger.info(f"📧 Sending invite to {guest.name} ({guest.phone})")

    message = f"""🌟 You're invited to the best wedding this galaxy has ever experienced! 🚀\n\nHi {guest.name}! 💍\n\nYou're cordially invited to join us for our special day. \n\n📱 RSVP here: {LOGIN_LINK}\n🔐 Your password: {guest.password}\n\nCan't wait to celebrate with you! ✨\n\nLove,\nThe Happy Couple 💕"""

    success = send_whatsapp_twilio(guest.phone, message)

    if success:
        guest.invite_sent = True
        session.commit()
        logger.info(f"✅ Invitation sent to {guest.name}")
        response = {"message": f"Invitation sent to {guest.name}"}
    else:
        logger.error(f"❌ Failed to send invitation to {guest.name}")
        response = {"error": "Failed to send WhatsApp message"}

    session.close()
    return jsonify(response)

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

@app.route("/api/test_twilio", methods=["GET"])
def test_twilio():
    logger.info("🧪 Testing Twilio configuration...")

    if not client:
        error_msg = "Twilio not configured. Set TWILIO_ACCOUNT_SID, TWILIO_API_KEY_SID, and TWILIO_API_KEY_SECRET"
        logger.error(f"❌ {error_msg}")
        return jsonify({"error": error_msg})

    try:
        account = client.api.accounts(TWILIO_ACCOUNT_SID).fetch()
        logger.info(f"✅ Twilio test successful: {account.friendly_name}")
        return jsonify({
            "status": "Twilio configured successfully",
            "account_sid": account.sid,
            "account_name": account.friendly_name,
            "whatsapp_number": TWILIO_WHATSAPP_NUMBER
        })
    except Exception as e:
        error_msg = f"Twilio configuration error: {str(e)}"
        logger.error(f"❌ {error_msg}", exc_info=True)
        return jsonify({"error": error_msg})

if __name__ == "__main__":
    logger.info("🚀 Starting Wedding Invitation Backend...")
    logger.info(f"📱 WhatsApp invites will be sent from: {TWILIO_WHATSAPP_NUMBER}")
    logger.info(f"🔗 Login link: {LOGIN_LINK}")

    if not TWILIO_ACCOUNT_SID or not TWILIO_API_KEY_SID:
        logger.warning("⚠️ Warning: Twilio not configured. Set environment variables:")
        logger.warning("   export TWILIO_ACCOUNT_SID='your_account_sid'")
        logger.warning("   export TWILIO_API_KEY_SID='your_api_key_sid'")
        logger.warning("   export TWILIO_API_KEY_SECRET='your_api_key_secret'")
    else:
        logger.info("✅ Twilio configuration looks good!")

    app.run(debug=True, host="0.0.0.0", port=5000)
