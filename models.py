# models.py

from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Guest(Base):
    __tablename__ = 'guests'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    phone = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    invite_sent = Column(Boolean, default=False)
    rsvp_status = Column(String, default="pending")
