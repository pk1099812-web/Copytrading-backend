"""
Copy Trading Engine
Master ka har trade automatically saare active child accounts mein copy karta hai
"""

import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime, date

from alice_blue import AliceBlueClient
from database import SessionLocal
from models import MasterAccount, ChildAccount, Trade
import auth

logger = logging.getLogger(__name__)

class CopyEngine:
    def __init__(self):
        # user_id → (AliceBlueClient, asyncio.Task)
        self._masters: Dict[int, AliceBlueClient] = {}
        self._tasks: Dict[int, asyncio.Task] = {}
        self._last_trade_ids: Dict[int, set] = {}  # Already copied trade IDs

    async def start_master_monitoring(self, user_id: int, master_client: AliceBlueClient):
        """Master account ka trade monitoring shuru karo"""
        # Pehle purana task stop karo
        await self.stop_master_monitoring(user_id)
        
        self._masters[user_id] = master_client
        self._last_trade_ids[user_id] = set()
        
        # Background task shuru karo
        task = asyncio.create_task(self._monitor_loop(user_id))
        self._tasks[user_id] = task
        logger.info(f"✅ Copy engine started for user {user_id}")

    async def stop_master_monitoring(self, user_id: int):
        """Monitoring band karo"""
        if user_id in self._tasks:
            self._tasks[user_id].cancel()
            del self._tasks[user_id]
        if user_id in self._masters:
            del self._masters[user_id]
        logger.info(f"⏹ Copy engine stopped for user {user_id}")

    async def _monitor_loop(self, user_id: int):
        """
        Har 2 second mein master ka trade book check karo
        Naya trade mila → saare child accounts mein copy karo
        """
        logger.info(f"🔄 Monitor loop started for user {user_id}")
        
        while True:
            try:
                await self._check_and_copy(user_id)
                await asyncio.sleep(2)  # 2 second interval
                
            except asyncio.CancelledError:
                logger.info(f"Monitor loop cancelled for user {user_id}")
                break
            except Exception as e:
                logger.error(f"Monitor loop error for user {user_id}: {e}")
                await asyncio.sleep(5)  # Error pe thoda zyada wait karo

    async def _check_and_copy(self, user_id: int):
        """Master ke naye trades dhundo aur copy karo"""
        master_client = self._masters.get(user_id)
        if not master_client:
            return

        # Master ke aaj ke trades fetch karo
        trades = await master_client.get_trade_book()
        
        if not trades:
            return

        # Naye trades filter karo (jo already copy nahi hue)
        known_ids = self._last_trade_ids.get(user_id, set())
        new_trades = [t for t in trades if t["order_id"] not in known_ids]
        
        if not new_trades:
            return

        logger.info(f"🆕 {len(new_trades)} naye trades mile for user {user_id}")

        # Child accounts fetch karo
        db = SessionLocal()
        try:
            children = db.query(ChildAccount).filter(
                ChildAccount.user_id == user_id,
                ChildAccount.is_active == True
            ).all()

            if not children:
                logger.info("Koi active child account nahi")
                return

            # Har naye trade ke liye copy karo
            for trade in new_trades:
                order_id = trade["order_id"]
                
                # Mark as known
                self._last_trade_ids[user_id].add(order_id)
                
                # Har child mein copy karo
                for child in children:
                    await self._copy_trade_to_child(user_id, trade, child)
                    
        finally:
            db.close()

    async def _copy_trade_to_child(self, user_id: int, master_trade: dict, child: ChildAccount):
        """Ek specific child account mein trade copy karo"""
        try:
            # Quantity calculate karo based on child settings
            original_qty = master_trade["qty"]
            
            if child.lot_mode == "fixed" and child.fixed_qty:
                copy_qty = child.fixed_qty
            else:
                copy_qty = max(1, int(original_qty * child.multiplier))

            # Max loss check karo
            if child.max_loss and child.pnl_today:
                if child.pnl_today <= -child.max_loss:
                    logger.warning(f"Child {child.name}: Max loss limit reached, skipping copy")
                    self._save_trade_log(user_id, master_trade, child, 0, "SKIPPED_MAX_LOSS")
                    return

            # Child ke liye fresh session
            child_client = AliceBlueClient(
                client_id=child.client_id,
                app_id=child.app_id,
                api_key=auth.decrypt(child.api_key_encrypted)
            )
            
            # Session token reuse karo (agar valid hai)
            if child.session_token:
                child_client.session_token = child.session_token
                child_client._update_headers()
            else:
                # Re-login karo
                password = auth.decrypt(child.password_encrypted)
                session = await child_client.login(password)
                if not session:
                    logger.error(f"Child {child.name}: Login failed")
                    return

            # Order place karo
            result = await child_client.place_order(
                symbol=master_trade["symbol"],
                exchange=master_trade["exchange"],
                trade_type=master_trade["trade_type"],
                quantity=copy_qty,
                price=0,  # Market order
                order_type="MKT",
                product=master_trade.get("product", "MIS")
            )

            status = "COPIED" if result.get("success") else "FAILED"
            logger.info(f"Copy to {child.name}: {status} | {master_trade['symbol']} {copy_qty} qty")

            # Log save karo
            self._save_trade_log(user_id, master_trade, child, copy_qty, status)

            # Child stats update karo
            if result.get("success"):
                db = SessionLocal()
                try:
                    db_child = db.query(ChildAccount).filter(ChildAccount.id == child.id).first()
                    if db_child:
                        db_child.trades_today = (db_child.trades_today or 0) + 1
                        db.commit()
                finally:
                    db.close()

        except Exception as e:
            logger.error(f"Copy trade error for {child.name}: {e}")
            self._save_trade_log(user_id, master_trade, child, 0, f"ERROR: {str(e)[:100]}")

    def _save_trade_log(self, user_id: int, master_trade: dict, child: ChildAccount, copy_qty: int, status: str):
        """Trade log database mein save karo"""
        db = SessionLocal()
        try:
            trade_log = Trade(
                user_id=user_id,
                symbol=master_trade["symbol"],
                exchange=master_trade.get("exchange", ""),
                trade_type=master_trade["trade_type"],
                quantity=copy_qty,
                price=master_trade.get("price", 0),
                master_order_id=master_trade["order_id"],
                child_account_id=child.id,
                child_account_name=child.name,
                status=status,
                pnl=None
            )
            db.add(trade_log)
            db.commit()
        except Exception as e:
            logger.error(f"Save trade log error: {e}")
        finally:
            db.close()

    def get_status(self) -> Dict:
        """Engine ka current status"""
        return {
            "active_masters": list(self._masters.keys()),
            "running_tasks": len(self._tasks)
        }
