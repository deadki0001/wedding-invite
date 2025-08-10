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
    # Serve the enhanced admin panel
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Wedding Admin Panel</title>
    <style>
        body {
            font-family: 'Segoe UI', sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem;
            background: linear-gradient(135deg, #f8cfd5, #fbeaea);
            min-height: 100vh;
        }
        
        .card {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            padding: 2rem;
            margin: 1rem 0;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            backdrop-filter: blur(10px);
        }
        
        h1 {
            color: #7b1e3b;
            text-align: center;
            margin-bottom: 2rem;
        }
        
        h2 {
            color: #d46a7c;
            border-bottom: 2px solid #f8cfd5;
            padding-bottom: 0.5rem;
        }
        
        .provider-status {
            background: rgba(212, 175, 55, 0.1);
            border: 2px solid #d4af37;
            border-radius: 10px;
            padding: 1rem;
            margin: 1rem 0;
        }
        
        .provider-status.success { border-color: #28a745; background: rgba(40, 167, 69, 0.1); }
        .provider-status.error { border-color: #dc3545; background: rgba(220, 53, 69, 0.1); }
        
        .form-group {
            margin: 1rem 0;
        }
        
        label {
            display: block;
            color: #7b1e3b;
            font-weight: bold;
            margin-bottom: 0.5rem;
        }
        
        input, select {
            width: 100%;
            padding: 0.8rem;
            border: 2px solid #f8cfd5;
            border-radius: 8px;
            font-size: 1rem;
            box-sizing: border-box;
        }
        
        input:focus, select:focus {
            outline: none;
            border-color: #d46a7c;
        }
        
        .button {
            display: inline-block;
            background: #7b1e3b;
            color: white;
            padding: 0.8rem 1.5rem;
            text-decoration: none;
            border: none;
            border-radius: 25px;
            margin: 0.5rem;
            cursor: pointer;
            font-size: 1rem;
            transition: all 0.3s ease;
        }
        
        .button:hover {
            background: #d46a7c;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        }
        
        .button.success { background: #28a745; }
        .button.warning { background: #ffc107; color: #000; }
        .button.danger { background: #dc3545; }
        .button.bulk { background: #d4af37; color: #000; font-weight: bold; }
        
        .guests-table {
            width: 100%;
            border-collapse: collapse;
            margin: 1rem 0;
        }
        
        .guests-table th,
        .guests-table td {
            border: 1px solid #f8cfd5;
            padding: 0.8rem;
            text-align: left;
        }
        
        .guests-table th {
            background: #d46a7c;
            color: white;
        }
        
        .guests-table tr:nth-child(even) {
            background: rgba(248, 207, 213, 0.3);
        }
        
        .status-badge {
            padding: 0.3rem 0.8rem;
            border-radius: 15px;
            font-size: 0.85rem;
            font-weight: bold;
        }
        
        .status-pending { background: #ffc107; color: #000; }
        .status-accepted { background: #28a745; color: white; }
        .status-declined { background: #dc3545; color: white; }
        .invite-sent { background: #17a2b8; color: white; }
        .invite-not-sent { background: #6c757d; color: white; }
        
        .stats-row {
            display: flex;
            gap: 1rem;
            margin: 1rem 0;
            flex-wrap: wrap;
        }
        
        .stat-card {
            flex: 1;
            background: rgba(212, 175, 55, 0.1);
            border-radius: 10px;
            padding: 1rem;
            text-align: center;
            min-width: 120px;
        }
        
        .stat-number {
            font-size: 2rem;
            font-weight: bold;
            color: #7b1e3b;
        }
        
        .stat-label {
            color: #d46a7c;
            font-size: 0.9rem;
        }
        
        .bulk-actions {
            background: rgba(212, 175, 55, 0.05);
            border: 2px dashed #d4af37;
            border-radius: 10px;
            padding: 1.5rem;
            margin: 1rem 0;
            text-align: center;
        }
        
        .message-log {
            background: #2d2d2d;
            color: #f8f8f2;
            padding: 1rem;
            border-radius: 8px;
            font-family: 'Courier New', monospace;
            margin: 1rem 0;
            max-height: 200px;
            overflow-y: auto;
            font-size: 0.85rem;
        }
    </style>
</head>
<body>
    <div class="card">
        <h1>💍 Wedding Admin Panel 🚀</h1>
        
        <!-- Provider Status -->
        <div id="providerStatus" class="provider-status">
            <h3>📡 Checking WhatsApp provider...</h3>
        </div>
        
        <!-- Stats Dashboard -->
        <div class="stats-row" id="statsRow">
            <div class="stat-card">
                <div class="stat-number" id="totalGuests">0</div>
                <div class="stat-label">Total Guests</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="invitesSent">0</div>
                <div class="stat-label">Invites Sent</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="rsvpAccepted">0</div>
                <div class="stat-label">RSVP Yes</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="rsvpDeclined">0</div>
                <div class="stat-label">RSVP No</div>
            </div>
        </div>
        
        <!-- Bulk Actions -->
        <div class="bulk-actions">
            <h3>🚀 Bulk Actions</h3>
            <p>Send wedding invites to all guests who haven't received one yet!</p>
            <button class="button bulk" onclick="sendAllInvites()">📱 Send All Pending Invites</button>
            <button class="button" onclick="loadGuests()">🔄 Refresh Guest List</button>
        </div>
        
        <!-- Add Guest Form -->
        <h2>➕ Add New Guest</h2>
        <form id="guestForm" onsubmit="addGuest(event)">
            <div class="form-group">
                <label for="guestName">Guest Name:</label>
                <input type="text" id="guestName" required placeholder="Enter guest name">
            </div>
            <div class="form-group">
                <label for="guestPhone">Phone Number (with country code):</label>
                <input type="tel" id="guestPhone" required placeholder="+27641234567">
            </div>
            <button type="submit" class="button">➕ Add Guest</button>
        </form>
        
        <!-- Guests List -->
        <h2>📋 Guest List</h2>
        <table class="guests-table" id="guestsTable">
            <thead>
                <tr>
                    <th>Name</th>
                    <th>Phone</th>
                    <th>Password</th>
                    <th>Invite Status</th>
                    <th>RSVP</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody id="guestsTableBody">
                <tr><td colspan="6">Loading guests...</td></tr>
            </tbody>
        </table>
        
        <!-- Message Log -->
        <h2>📞 Message Log</h2>
        <div id="messageLog" class="message-log">
            Ready to send invites...<br>
        </div>
    </div>

    <script>
        let guests = [];
        let providerInfo = {};

        // Check provider status on load
        async function checkProviderStatus() {
            try {
                const response = await fetch('/api/test_whatsapp');
                const result = await response.json();
                const statusDiv = document.getElementById('providerStatus');
                
                if (result.error) {
                    statusDiv.className = 'provider-status error';
                    statusDiv.innerHTML = `
                        <h3>❌ ${result.error}</h3>
                        <p>Please configure your WhatsApp provider in the .env file</p>
                    `;
                } else {
                    statusDiv.className = 'provider-status success';
                    providerInfo = result;
                    statusDiv.innerHTML = `
                        <h3>✅ ${result.status}</h3>
                        <p><strong>Provider:</strong> ${result.provider}</p>
                        <p><strong>Pricing:</strong> ${result.pricing || 'N/A'}</p>
                        <p><strong>API Key:</strong> ${result.api_key || 'Not set'}</p>
                    `;
                }
            } catch (error) {
                console.error('Provider check failed:', error);
                document.getElementById('providerStatus').innerHTML = `
                    <h3>❌ Connection Error</h3>
                    <p>Could not check provider status. Make sure the backend is running.</p>
                `;
            }
        }

        // Load guests from API
        async function loadGuests() {
            try {
                const response = await fetch('/api/guests');
                guests = await response.json();
                updateStats();
                updateGuestsTable();
                logMessage(`📋 Loaded ${guests.length} guests`);
            } catch (error) {
                logMessage(`❌ Failed to load guests: ${error.message}`);
                console.error('Failed to load guests:', error);
            }
        }

        // Update statistics
        function updateStats() {
            document.getElementById('totalGuests').textContent = guests.length;
            document.getElementById('invitesSent').textContent = guests.filter(g => g.invite_sent).length;
            document.getElementById('rsvpAccepted').textContent = guests.filter(g => g.rsvp_status === 'accepted').length;
            document.getElementById('rsvpDeclined').textContent = guests.filter(g => g.rsvp_status === 'declined').length;
        }

        // Update guests table
        function updateGuestsTable() {
            const tbody = document.getElementById('guestsTableBody');
            if (guests.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6">No guests added yet. Add your first guest above! 🎉</td></tr>';
                return;
            }

            tbody.innerHTML = guests.map(guest => `
                <tr>
                    <td>${guest.name}</td>
                    <td>${guest.phone}</td>
                    <td><code>${guest.password || 'N/A'}</code></td>
                    <td>
                        <span class="status-badge ${guest.invite_sent ? 'invite-sent' : 'invite-not-sent'}">
                            ${guest.invite_sent ? '✅ Sent' : '⏳ Pending'}
                        </span>
                    </td>
                    <td>
                        <span class="status-badge status-${guest.rsvp_status || 'pending'}">
                            ${guest.rsvp_status === 'accepted' ? '✅ Yes' : 
                              guest.rsvp_status === 'declined' ? '❌ No' : '⏳ Pending'}
                        </span>
                    </td>
                    <td>
                        <button class="button ${guest.invite_sent ? 'warning' : 'success'}" 
                                onclick="sendInvite(${guest.id})">
                            ${guest.invite_sent ? '🔄 Resend' : '📱 Send'}
                        </button>
                    </td>
                </tr>
            `).join('');
        }

        // Add new guest
        async function addGuest(event) {
            event.preventDefault();
            
            const name = document.getElementById('guestName').value;
            const phone = document.getElementById('guestPhone').value;
            
            try {
                const response = await fetch('/api/add_guest', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name, phone })
                });
                
                const result = await response.json();
                
                if (response.ok) {
                    logMessage(`✅ Added guest: ${name} - Password: ${result.password}`);
                    document.getElementById('guestForm').reset();
                    await loadGuests();
                } else {
                    logMessage(`❌ Failed to add guest: ${result.error}`);
                    alert(`Error: ${result.error}`);
                }
            } catch (error) {
                logMessage(`❌ Error adding guest: ${error.message}`);
                console.error('Failed to add guest:', error);
            }
        }

        // Send invite to specific guest
        async function sendInvite(guestId) {
            const guest = guests.find(g => g.id === guestId);
            if (!guest) return;
            
            logMessage(`📱 Sending invite to ${guest.name}...`);
            
            try {
                const response = await fetch(`/api/send_invite/${guestId}`, {
                    method: 'POST'
                });
                
                const result = await response.json();
                
                if (response.ok) {
                    logMessage(`✅ ${result.message}`);
                    await loadGuests();
                } else {
                    logMessage(`❌ ${result.error}`);
                    alert(`Error: ${result.error}`);
                }
            } catch (error) {
                logMessage(`❌ Failed to send invite: ${error.message}`);
                console.error('Failed to send invite:', error);
            }
        }

        // Send all pending invites
        async function sendAllInvites() {
            const pendingGuests = guests.filter(g => !g.invite_sent);
            
            if (pendingGuests.length === 0) {
                alert('🎉 All invites have already been sent!');
                return;
            }
            
            if (!confirm(`Send invites to ${pendingGuests.length} guests?`)) {
                return;
            }
            
            logMessage(`🚀 Sending bulk invites to ${pendingGuests.length} guests...`);
            
            try {
                const response = await fetch('/api/send_all_invites', {
                    method: 'POST'
                });
                
                const result = await response.json();
                
                if (response.ok) {
                    logMessage(`✅ ${result.message}`);
                    if (result.results) {
                        result.results.sent.forEach(name => logMessage(`  ✅ Sent to ${name}`));
                        result.results.failed.forEach(name => logMessage(`  ❌ Failed: ${name}`));
                    }
                    await loadGuests();
                } else {
                    logMessage(`❌ Bulk send failed: ${result.error}`);
                    alert(`Error: ${result.error}`);
                }
            } catch (error) {
                logMessage(`❌ Bulk send error: ${error.message}`);
                console.error('Bulk send failed:', error);
            }
        }

        // Log message to console
        function logMessage(message) {
            const timestamp = new Date().toLocaleTimeString();
            const logDiv = document.getElementById('messageLog');
            logDiv.innerHTML += `[${timestamp}] ${message}<br>`;
            logDiv.scrollTop = logDiv.scrollHeight;
            console.log(`[Admin] ${message}`);
        }

        // Initialize page
        window.addEventListener('load', async () => {
            logMessage('🚀 Wedding Admin Panel loaded');
            await checkProviderStatus();
            await loadGuests();
        });
    </script>
</body>
</html>"""

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