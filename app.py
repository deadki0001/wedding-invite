# app.py

from flask import Flask, request, jsonify
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, Guest
import random
import string
import requests

app = Flask(__name__)

engine = create_engine('sqlite:///database.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

LOGIN_LINK = "https://yourdomain.com"  # Replace with actual link

# Generate a random password
def generate_password(length=10):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

# CallMeBot for free WhatsApp messages
def send_whatsapp(phone, message):
    url = f"https://api.callmebot.com/whatsapp.php?phone={phone}&text={message}&apikey=free"
    response = requests.get(url)
    return response.status_code == 200

@app.route("/api/add_guest", methods=["POST"])
def add_guest():
    data = request.get_json()
    session = Session()

    name = data.get("name")
    phone = data.get("phone")
    password = generate_password()

    if session.query(Guest).filter_by(phone=phone).first():
        return jsonify({"error": "Guest already exists"}), 409

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

    message = f"You’re invited to a wedding unlike this galaxy has ever experienced! 🌌 Click here to RSVP: {LOGIN_LINK} — Use password: {guest.password}"

    if send_whatsapp(guest.phone, message):
        guest.invite_sent = True
        session.commit()
        response = {"message": "Invite sent"}
    else:
        response = {"error": "Failed to send message"}

    session.close()
    return jsonify(response)

@app.route("/api/guests", methods=["GET"])
def get_guests():
    session = Session()
    guests = session.query(Guest).all()
    data = [{"id": g.id, "name": g.name, "phone": g.phone, "invite_sent": g.invite_sent} for g in guests]
    session.close()
    return jsonify(data)

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    phone = data.get("phone")
    password = data.get("password")
    session = Session()

    guest = session.query(Guest).filter_by(phone=phone, password=password).first()
    session.close()

    if guest:
        return jsonify({"success": True})
    return jsonify({"success": False}), 401

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
