# app.py

from flask import Flask, request, jsonify, send_from_directory
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, Guest
import random
import string
import os
from twilio.rest import Client

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv('development.env')  # Load your specific env file
    print("✅ Loaded environment variables from development.env")
except ImportError:
    print("⚠️ python-dotenv not installed. Using system environment variables.")

app = Flask(__name__)

# Database setup
engine = create_engine('sqlite:///database.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

# Twilio Configuration (Using API Keys - new format)
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')  # Main Account SID
TWILIO_API_KEY_SID = os.getenv('TWILIO_API_KEY_SID')  # API Key SID
TWILIO_API_KEY_SECRET = os.getenv('TWILIO_API_KEY_SECRET')  # API Key Secret
TWILIO_WHATSAPP_NUMBER = 'whatsapp:+14155238886'     # Twilio Sandbox number (for testing)

# Your wedding invitation URL
LOGIN_LINK = "https://wedding-invitation.adkinsfamily.co.za/"

# Initialize Twilio client with API Key
client = None
if TWILIO_ACCOUNT_SID and TWILIO_API_KEY_SID and TWILIO_API_KEY_SECRET:
    client = Client(TWILIO_API_KEY_SID, TWILIO_API_KEY_SECRET, TWILIO_ACCOUNT_SID)
    print("✅ Twilio client initialized successfully")
else:
    print("⚠️ Twilio API Key not configured")
    print(f"   Account SID: {'✅' if TWILIO_ACCOUNT_SID else '❌'}")
    print(f"   API Key SID: {'✅' if TWILIO_API_KEY_SID else '❌'}")
    print(f"   API Key Secret: {'✅' if TWILIO_API_KEY_SECRET else '❌'}")

# Generate a random password
def generate_password(length=8):
    """Generate a simple, memorable password"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

# Send WhatsApp message via Twilio
def send_whatsapp_twilio(phone, message):
    """Send WhatsApp message using Twilio API"""
    if not client:
        print("⚠️ Twilio not configured - would send:", message)
        return False
    
    try:
        # Ensure phone number is in correct format
        if not phone.startswith('+'):
            phone = '+' + phone
        
        print(f"📱 Sending WhatsApp to {phone}")
        message_obj = client.messages.create(
            body=message,
            from_=TWILIO_WHATSAPP_NUMBER,
            to=f'whatsapp:{phone}'
        )
        
        print(f"✅ Message sent successfully: {message_obj.sid}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to send WhatsApp message: {str(e)}")
        return False

@app.route("/")
def index():
    """Serve the login page"""
    return send_from_directory('.', 'index.html')

@app.route("/admin")
def admin():
    """Serve the admin panel"""
    return send_from_directory('.', 'admin.html')

@app.route("/api/add_guest", methods=["POST"])
def add_guest():
    """Add a new guest with auto-generated password"""
    data = request.get_json()
    session = Session()

    name = data.get("name")
    phone = data.get("phone")
    
    print(f"🆕 Adding guest: {name} - {phone}")
    
    # Validate input
    if not name or not phone:
        return jsonify({"error": "Name and phone are required"}), 400
    
    # Check if guest already exists
    if session.query(Guest).filter_by(phone=phone).first():
        session.close()
        return jsonify({"error": "Guest already exists"}), 409

    # Generate password
    password = generate_password()
    
    # Create guest
    guest = Guest(name=name, phone=phone, password=password)
    session.add(guest)
    session.commit()
    session.close()

    print(f"✅ Guest added: {name} - Password: {password}")
    return jsonify({
        "message": f"Guest {name} added successfully", 
        "password": password,
        "phone": phone
    })

@app.route("/api/send_invite/<int:guest_id>", methods=["POST"])
def send_invite(guest_id):
    """Send WhatsApp invitation to a specific guest"""
    session = Session()
    guest = session.query(Guest).get(guest_id)

    if not guest:
        session.close()
        return jsonify({"error": "Guest not found"}), 404

    print(f"📧 Sending invite to {guest.name} ({guest.phone})")

    # Custom wedding invitation message
    message = f"""🌟 You're invited to the best wedding this galaxy has ever experienced! 🚀

Hi {guest.name}! 💍

You're cordially invited to join us for our special day. 

📱 RSVP here: {LOGIN_LINK}
🔐 Your password: {guest.password}

Can't wait to celebrate with you! ✨

Love,
The Happy Couple 💕"""

    # Send WhatsApp message
    success = send_whatsapp_twilio(guest.phone, message)
    
    if success:
        guest.invite_sent = True
        session.commit()
        print(f"✅ Invitation sent to {guest.name}")
        response = {"message": f"Invitation sent to {guest.name}"}
    else:
        print(f"❌ Failed to send invitation to {guest.name}")
        response = {"error": "Failed to send WhatsApp message"}

    session.close()
    return jsonify(response)

@app.route("/api/guests", methods=["GET"])
def get_guests():
    """Get all guests for admin panel"""
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
    print(f"📋 Retrieved {len(data)} guests")
    return jsonify(data)

@app.route("/api/login", methods=["POST"])
def login():
    """Validate guest login"""
    data = request.get_json()
    phone = data.get("phone")
    password = data.get("password")
    
    print(f"🔐 Login attempt: {phone}")
    
    if not phone or not password:
        return jsonify({"success": False, "error": "Phone and password required"}), 400
    
    session = Session()
    guest = session.query(Guest).filter_by(phone=phone, password=password).first()
    session.close()

    if guest:
        print(f"✅ Login successful: {guest.name}")
        return jsonify({
            "success": True, 
            "guest": {
                "name": guest.name,
                "phone": guest.phone,
                "rsvp_status": guest.rsvp_status
            }
        })
    
    print(f"❌ Login failed: {phone}")
    return jsonify({"success": False, "error": "Invalid credentials"}), 401

@app.route("/api/test_twilio", methods=["GET"])
def test_twilio():
    """Test Twilio configuration"""
    print("🧪 Testing Twilio configuration...")
    
    if not client:
        error_msg = "Twilio not configured. Set TWILIO_ACCOUNT_SID, TWILIO_API_KEY_SID, and TWILIO_API_KEY_SECRET environment variables"
        print(f"❌ {error_msg}")
        return jsonify({"error": error_msg})
    
    try:
        # Test by getting account info
        account = client.api.accounts(TWILIO_ACCOUNT_SID).fetch()
        success_msg = {
            "status": "Twilio configured successfully",
            "account_sid": account.sid,
            "account_name": account.friendly_name,
            "whatsapp_number": TWILIO_WHATSAPP_NUMBER
        }
        print(f"✅ Twilio test successful: {account.friendly_name}")
        return jsonify(success_msg)
    except Exception as e:
        error_msg = f"Twilio configuration error: {str(e)}"
        print(f"❌ {error_msg}")
        return jsonify({"error": error_msg})

if __name__ == "__main__":
    print("🚀 Starting Wedding Invitation Backend...")
    print(f"📱 WhatsApp invites will be sent from: {TWILIO_WHATSAPP_NUMBER}")
    print(f"🔗 Login link: {LOGIN_LINK}")
    
    if not TWILIO_ACCOUNT_SID or not TWILIO_API_KEY_SID:
        print("⚠️ Warning: Twilio not configured. Set environment variables:")
        print("   export TWILIO_ACCOUNT_SID='your_account_sid'")
        print("   export TWILIO_API_KEY_SID='your_api_key_sid'")
        print("   export TWILIO_API_KEY_SECRET='your_api_key_secret'")
    else:
        print("✅ Twilio configuration looks good!")
    
    app.run(debug=True, host="0.0.0.0", port=5000)