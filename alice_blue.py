"""
Alice Blue ANT API Client
Real integration with Alice Blue broker API
Docs: https://v2api.aliceblueonline.com/
"""

import hashlib
import aiohttp
import asyncio
import json
import logging
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

ALICE_BASE_URL = "https://ant.aliceblueonline.com/rest/AliceBlueAPIService/api"

class AliceBlueClient:
    def __init__(self, client_id: str, app_id: str, api_key: str):
        self.client_id = client_id.upper()
        self.app_id = app_id
        self.api_key = api_key
        self.session_token = None
        self._headers = {}

    def _make_user_data(self, password: str) -> str:
        """Alice Blue ke liye SHA-256 hash generate karo"""
        # Step 1: api_key ka SHA-256
        api_sha = hashlib.sha256(self.api_key.encode()).hexdigest()
        # Step 2: clientId + apiSha + password ka SHA-256
        user_data = hashlib.sha256(
            f"{self.client_id}{api_sha}".encode()
        ).hexdigest()
        return user_data

    async def login(self, password: str, totp: Optional[str] = None) -> Optional[str]:
        """Alice Blue mein login karo aur session token lo"""
        try:
            user_data = self._make_user_data(password)
            
            payload = {
                "userId": self.client_id,
                "userData": user_data
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{ALICE_BASE_URL}/customer/getUserSID",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as resp:
                    data = await resp.json()
                    logger.info(f"Login response: {data}")
                    
                    if data.get("stat") == "Ok":
                        self.session_token = data.get("sessionID")
                        self._update_headers()
                        logger.info(f"✅ Alice Blue login successful for {self.client_id}")
                        return self.session_token
                    else:
                        logger.error(f"❌ Login failed: {data.get('emsg', 'Unknown error')}")
                        return None
                        
        except Exception as e:
            logger.error(f"Login exception: {e}")
            return None

    def _update_headers(self):
        """Authorization headers update karo"""
        self._headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.client_id} {self.session_token}"
        }

    async def get_profile(self) -> Dict:
        """Account profile fetch karo"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{ALICE_BASE_URL}/customer/accountDetails",
                    headers=self._headers
                ) as resp:
                    data = await resp.json()
                    if data.get("stat") == "Ok":
                        return {
                            "name": data.get("accountName", ""),
                            "client_id": data.get("accountId", self.client_id),
                            "email": data.get("emailAddr", ""),
                            "mobile": data.get("cellAddr", ""),
                            "exchanges": data.get("exchEnabled", "NSE,BSE,NFO").split(",")
                        }
                    return {"client_id": self.client_id}
        except Exception as e:
            logger.error(f"Get profile error: {e}")
            return {"client_id": self.client_id}

    async def get_balance(self) -> Dict:
        """Account balance aur margin fetch karo"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{ALICE_BASE_URL}/limits/getRmsLimits",
                    json={"seg": "ALL", "exch": "ALL", "prod": "ALL"},
                    headers=self._headers
                ) as resp:
                    data = await resp.json()
                    if isinstance(data, list) and len(data) > 0:
                        rms = data[0]
                        net = float(rms.get("net", 0))
                        used = float(rms.get("marginused", 0))
                        return {
                            "total": net,
                            "available": net - used,
                            "used": used
                        }
                    return {"total": 0, "available": 0, "used": 0}
        except Exception as e:
            logger.error(f"Get balance error: {e}")
            return {"total": 0, "available": 0, "used": 0}

    async def get_positions(self) -> List[Dict]:
        """Open positions fetch karo"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{ALICE_BASE_URL}/positionAndHoldings/positionBook",
                    headers=self._headers
                ) as resp:
                    data = await resp.json()
                    positions = []
                    if isinstance(data, list):
                        for p in data:
                            if p.get("stat") == "Ok":
                                continue
                            net_qty = int(p.get("netqty", 0))
                            if net_qty != 0:
                                positions.append({
                                    "symbol": p.get("trdSym", ""),
                                    "exchange": p.get("exch", ""),
                                    "qty": net_qty,
                                    "avg_price": float(p.get("avgprc", 0)),
                                    "ltp": float(p.get("ltp", 0)),
                                    "pnl": float(p.get("unrealizedprofitloss", 0)),
                                    "trade_type": "BUY" if net_qty > 0 else "SELL"
                                })
                    return positions
        except Exception as e:
            logger.error(f"Get positions error: {e}")
            return []

    async def get_orders(self) -> List[Dict]:
        """Order book fetch karo"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{ALICE_BASE_URL}/placeOrder/fetchOrderBook",
                    headers=self._headers
                ) as resp:
                    data = await resp.json()
                    orders = []
                    if isinstance(data, list):
                        for o in data:
                            if o.get("stat") == "Ok":
                                continue
                            status = o.get("status", "").upper()
                            if status in ["OPEN", "TRIGGER PENDING", "AFTER MARKET ORDER REQ RECEIVED"]:
                                orders.append({
                                    "order_id": o.get("norenordno", ""),
                                    "symbol": o.get("trdSym", ""),
                                    "trade_type": o.get("trantype", ""),
                                    "qty": int(o.get("qty", 0)),
                                    "price": float(o.get("prc", 0)),
                                    "status": status,
                                    "time": o.get("exch_tm", "")
                                })
                    return orders
        except Exception as e:
            logger.error(f"Get orders error: {e}")
            return []

    async def get_trade_book(self) -> List[Dict]:
        """Aaj ke executed trades"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{ALICE_BASE_URL}/placeOrder/fetchTradeBook",
                    headers=self._headers
                ) as resp:
                    data = await resp.json()
                    trades = []
                    if isinstance(data, list):
                        for t in data:
                            if t.get("stat") == "Ok":
                                continue
                            trades.append({
                                "order_id": t.get("norenordno", ""),
                                "symbol": t.get("trdSym", ""),
                                "exchange": t.get("exch", ""),
                                "trade_type": t.get("trantype", "B").upper(),
                                "qty": int(t.get("qty", 0)),
                                "price": float(t.get("prc", 0)),
                                "product": t.get("prd", ""),
                                "order_type": t.get("prctyp", ""),
                                "time": t.get("exch_tm", ""),
                                "isin": t.get("isin", "")
                            })
                    return trades
        except Exception as e:
            logger.error(f"Get trade book error: {e}")
            return []

    async def place_order(
        self,
        symbol: str,
        exchange: str,
        trade_type: str,  # "BUY" or "SELL"
        quantity: int,
        price: float = 0,
        order_type: str = "MKT",  # MKT, LMT, SL, SL-M
        product: str = "MIS",  # MIS, CNC, NRML
        trigger_price: float = 0
    ) -> Dict:
        """Order place karo"""
        try:
            payload = {
                "exch": exchange,
                "trdSym": symbol,
                "qty": str(quantity),
                "prc": str(price),
                "trgPrc": str(trigger_price),
                "trantype": "B" if trade_type == "BUY" else "S",
                "prctyp": order_type,
                "prd": product,
                "ret": "DAY",
                "remarks": "CopyTrade",
                "discqty": "0",
                "MktPro": "NA"
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{ALICE_BASE_URL}/placeOrder/executePlaceOrder",
                    json=[payload],
                    headers=self._headers
                ) as resp:
                    data = await resp.json()
                    logger.info(f"Order placed: {data}")
                    
                    if isinstance(data, list) and len(data) > 0:
                        result = data[0]
                        if result.get("stat") == "Ok":
                            return {
                                "success": True,
                                "order_id": result.get("NOrdNo", ""),
                                "message": "Order placed successfully"
                            }
                        else:
                            return {
                                "success": False,
                                "error": result.get("emsg", "Order failed")
                            }
                    return {"success": False, "error": "Invalid response"}
                    
        except Exception as e:
            logger.error(f"Place order error: {e}")
            return {"success": False, "error": str(e)}

    async def cancel_order(self, order_id: str, exchange: str = "NSE") -> Dict:
        """Order cancel karo"""
        try:
            payload = {
                "norenordno": order_id,
                "exch": exchange
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{ALICE_BASE_URL}/placeOrder/cancelOrder",
                    json=payload,
                    headers=self._headers
                ) as resp:
                    data = await resp.json()
                    return {"success": data.get("stat") == "Ok"}
        except Exception as e:
            return {"success": False, "error": str(e)}
