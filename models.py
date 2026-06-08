"""Database Models"""
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    email = Column(String(100), unique=True)
    password_hash = Column(String(200))
    created_at = Column(DateTime, default=datetime.utcnow)

class MasterAccount(Base):
    __tablename__ = "master_accounts"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    client_id = Column(String(50))
    app_id = Column(String(50))
    api_key_encrypted = Column(Text)
    password_encrypted = Column(Text)
    session_token = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class ChildAccount(Base):
    __tablename__ = "child_accounts"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String(100))
    client_id = Column(String(50))
    app_id = Column(String(50))
    api_key_encrypted = Column(Text)
    password_encrypted = Column(Text)
    session_token = Column(Text, nullable=True)
    multiplier = Column(Float, default=1.0)
    lot_mode = Column(String(20), default="multiplier")
    fixed_qty = Column(Integer, nullable=True)
    max_loss = Column(Float, nullable=True)
    is_active = Column(Boolean, default=True)
    pnl_today = Column(Float, default=0)
    trades_today = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

class Trade(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    symbol = Column(String(100))
    exchange = Column(String(20))
    trade_type = Column(String(10))
    quantity = Column(Integer)
    price = Column(Float)
    master_order_id = Column(String(100))
    child_account_id = Column(Integer, nullable=True)
    child_account_name = Column(String(100))
    status = Column(String(50))
    pnl = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
