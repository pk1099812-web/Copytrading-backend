"""
CopyTrading Backend - Alice Blue
Real copy trading engine using Alice Blue ANT API
"""

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, List
import uvicorn
import asyncio
import logging

from database import init_db, get_db, SessionLocal
from alice_blue import AliceBlueClient
from copy_engine import CopyEngine
from models import User, MasterAccount, ChildAccount, Trade
import auth

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="CopyTrading API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Production mein apna domain daalo
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()
copy_engine = CopyEngine()

# ─── STARTUP ──────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    init_db()
    logger.info("✅ Database initialized")

# ─── AUTH MODELS ──────────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class MasterAccountRequest(BaseModel):
    client_id: str
    app_id: str
    api_key: str
    password: str
    totp: Optional[str] = None

class ChildAccountRequest(BaseModel):
    name: str
    client_id: str
    app_id: str
    api_key: str
    password: str
    multiplier: float = 1.0  # 0.5x, 1x, 2x, 3x
    lot_mode: str = "multiplier"  # multiplier ya fixed
    fixed_qty: Optional[int] = None
    max_loss: Optional[float] = None
    totp: Optional[str] = None

# ─── AUTH ROUTES ──────────────────────────────────────────────────────────────
@app.post("/api/register")
async def register(req: RegisterRequest):
    db = SessionLocal()
    try:
        # Check if email already exists
        existing = db.query(User).filter(User.email == req.email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        user = User(
            name=req.name,
            email=req.email,
            password_hash=auth.hash_password(req.password)
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        
        token = auth.create_token(user.id)
        return {"token": token, "user": {"id": user.id, "name": user.name, "email": user.email}}
    finally:
        db.close()

@app.post("/api/login")
async def login(req: LoginRequest):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == req.email).first()
        if not user or not auth.verify_password(req.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        token = auth.create_token(user.id)
        return {"token": token, "user": {"id": user.id, "name": user.name, "email": user.email}}
    finally:
        db.close()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    user_id = auth.verify_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    db = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    db.close()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

# ─── MASTER ACCOUNT ROUTES ────────────────────────────────────────────────────
@app.post("/api/master/connect")
async def connect_master(req: MasterAccountRequest, user=Depends(get_current_user)):
    """Alice Blue master account connect karo"""
    try:
        # Alice Blue se real connection
        client = AliceBlueClient(
            client_id=req.client_id,
            app_id=req.app_id,
            api_key=req.api_key
        )
        session = await client.login(req.password, req.totp)
        
        if not session:
            raise HTTPException(status_code=400, detail="Alice Blue login failed. Credentials check karo.")
        
        # Account details fetch karo
        profile = await client.get_profile()
        balance = await client.get_balance()
        
        # Database mein save karo
        db = SessionLocal()
        try:
            master = db.query(MasterAccount).filter(MasterAccount.user_id == user.id).first()
            if master:
                # Update existing
                master.client_id = req.client_id
                master.app_id = req.app_id
                master.api_key_encrypted = auth.encrypt(req.api_key)
                master.password_encrypted = auth.encrypt(req.password)
                master.session_token = session
                master.is_active = True
            else:
                master = MasterAccount(
                    user_id=user.id,
                    client_id=req.client_id,
                    app_id=req.app_id,
                    api_key_encrypted=auth.encrypt(req.api_key),
                    password_encrypted=auth.encrypt(req.password),
                    session_token=session,
                    is_active=True
                )
                db.add(master)
            db.commit()
            
            # Copy engine start karo
            await copy_engine.start_master_monitoring(user.id, client)
            
            return {
                "success": True,
                "message": "Master account connected!",
                "profile": profile,
                "balance": balance
            }
        finally:
            db.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Master connect error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/master/status")
async def master_status(user=Depends(get_current_user)):
    """Master account status aur live data"""
    db = SessionLocal()
    try:
        master = db.query(MasterAccount).filter(
            MasterAccount.user_id == user.id,
            MasterAccount.is_active == True
        ).first()
        
        if not master:
            return {"connected": False}
        
        # Live data fetch karo
        client = AliceBlueClient(
            client_id=master.client_id,
            app_id=master.app_id,
            api_key=auth.decrypt(master.api_key_encrypted)
        )
        client.session_token = master.session_token
        
        balance = await client.get_balance()
        positions = await client.get_positions()
        orders = await client.get_orders()
        
        return {
            "connected": True,
            "client_id": master.client_id,
            "app_id": master.app_id,
            "balance": balance,
            "positions": positions,
            "orders": orders
        }
    finally:
        db.close()

@app.delete("/api/master/disconnect")
async def disconnect_master(user=Depends(get_current_user)):
    db = SessionLocal()
    try:
        master = db.query(MasterAccount).filter(MasterAccount.user_id == user.id).first()
        if master:
            master.is_active = False
            db.commit()
        await copy_engine.stop_master_monitoring(user.id)
        return {"success": True, "message": "Master account disconnected"}
    finally:
        db.close()

# ─── CHILD ACCOUNTS ROUTES ───────────────────────────────────────────────────
@app.post("/api/children/add")
async def add_child(req: ChildAccountRequest, user=Depends(get_current_user)):
    """Child account add karo"""
    try:
        # Child account ka Alice Blue connection verify karo
        client = AliceBlueClient(
            client_id=req.client_id,
            app_id=req.app_id,
            api_key=req.api_key
        )
        session = await client.login(req.password, req.totp)
        
        if not session:
            raise HTTPException(status_code=400, detail="Child account Alice Blue login failed")
        
        db = SessionLocal()
        try:
            child = ChildAccount(
                user_id=user.id,
                name=req.name,
                client_id=req.client_id,
                app_id=req.app_id,
                api_key_encrypted=auth.encrypt(req.api_key),
                password_encrypted=auth.encrypt(req.password),
                session_token=session,
                multiplier=req.multiplier,
                lot_mode=req.lot_mode,
                fixed_qty=req.fixed_qty,
                max_loss=req.max_loss,
                is_active=True
            )
            db.add(child)
            db.commit()
            db.refresh(child)
            
            return {
                "success": True,
                "message": f"{req.name} ka account add ho gaya!",
                "child_id": child.id
            }
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/children")
async def get_children(user=Depends(get_current_user)):
    """Saare child accounts"""
    db = SessionLocal()
    try:
        children = db.query(ChildAccount).filter(ChildAccount.user_id == user.id).all()
        result = []
        for c in children:
            result.append({
                "id": c.id,
                "name": c.name,
                "client_id": c.client_id,
                "app_id": c.app_id,
                "multiplier": c.multiplier,
                "lot_mode": c.lot_mode,
                "is_active": c.is_active,
                "pnl_today": c.pnl_today,
                "trades_today": c.trades_today
            })
        return result
    finally:
        db.close()

@app.patch("/api/children/{child_id}")
async def update_child(child_id: int, data: dict, user=Depends(get_current_user)):
    db = SessionLocal()
    try:
        child = db.query(ChildAccount).filter(
            ChildAccount.id == child_id,
            ChildAccount.user_id == user.id
        ).first()
        if not child:
            raise HTTPException(status_code=404, detail="Child account not found")
        
        if "multiplier" in data:
            child.multiplier = data["multiplier"]
        if "is_active" in data:
            child.is_active = data["is_active"]
        if "max_loss" in data:
            child.max_loss = data["max_loss"]
        
        db.commit()
        return {"success": True}
    finally:
        db.close()

@app.delete("/api/children/{child_id}")
async def remove_child(child_id: int, user=Depends(get_current_user)):
    db = SessionLocal()
    try:
        child = db.query(ChildAccount).filter(
            ChildAccount.id == child_id,
            ChildAccount.user_id == user.id
        ).first()
        if not child:
            raise HTTPException(status_code=404, detail="Not found")
        db.delete(child)
        db.commit()
        return {"success": True, "message": "Child account removed"}
    finally:
        db.close()

# ─── TRADES ROUTES ────────────────────────────────────────────────────────────
@app.get("/api/trades")
async def get_trades(user=Depends(get_current_user), limit: int = 50):
    db = SessionLocal()
    try:
        trades = db.query(Trade).filter(
            Trade.user_id == user.id
        ).order_by(Trade.created_at.desc()).limit(limit).all()
        
        return [{
            "id": t.id,
            "symbol": t.symbol,
            "trade_type": t.trade_type,
            "quantity": t.quantity,
            "price": t.price,
            "master_order_id": t.master_order_id,
            "child_account_name": t.child_account_name,
            "status": t.status,
            "pnl": t.pnl,
            "created_at": str(t.created_at)
        } for t in trades]
    finally:
        db.close()

# ─── DASHBOARD STATS ──────────────────────────────────────────────────────────
@app.get("/api/dashboard")
async def dashboard(user=Depends(get_current_user)):
    db = SessionLocal()
    try:
        from datetime import date
        today = date.today()
        
        children = db.query(ChildAccount).filter(
            ChildAccount.user_id == user.id
        ).all()
        
        active_children = sum(1 for c in children if c.is_active)
        total_pnl = sum(c.pnl_today or 0 for c in children)
        total_trades = sum(c.trades_today or 0 for c in children)
        
        master = db.query(MasterAccount).filter(
            MasterAccount.user_id == user.id,
            MasterAccount.is_active == True
        ).first()
        
        return {
            "master_connected": master is not None,
            "total_children": len(children),
            "active_children": active_children,
            "total_pnl_today": total_pnl,
            "total_trades_today": total_trades,
        }
    finally:
        db.close()

# ─── HEALTH CHECK ─────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {"status": "running", "message": "CopyTrading API is live! 🚀"}

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
