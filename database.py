# database.py
import os
import logging
from datetime import datetime, timedelta, date
from typing import Optional, List, Dict, Any
from pymongo import MongoClient, DESCENDING, ASCENDING
from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)

MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://Today_Idk:TpdauT434odayTodayToday23@cluster0.rlgkop5.mongodb.net/MultiAdmin?retryWrites=true&w=majority&appName=Cluster0")
DB_NAME = os.getenv("DB_NAME", "MultiAdmin")


class MongoDB:
    _client: Optional[MongoClient] = None
    _db = None

    @classmethod
    def get_client(cls):
        if cls._client is None:
            cls._client = MongoClient(MONGO_URI)
        return cls._client

    @classmethod
    def get_db(cls):
        if cls._db is None:
            cls._db = cls.get_client()[DB_NAME]
        return cls._db


class GroupDatabase:
    def __init__(self, chat_id: int):
        self.chat_id = chat_id
        self.db = MongoDB.get_db()
        self.prefix = f"g{str(chat_id).replace('-', 'n')}_"
        self._ensure_indexes()

    def _col(self, name: str):
        return self.db[f"{self.prefix}{name}"]

    def _ensure_indexes(self):
        try:
            self._col("users").create_index("user_id", unique=True)
            self._col("market").create_index("seller_id")
            self._col("market").create_index("sold")
            self._col("arena_queue").create_index("user_id", unique=True)
            self._col("battles").create_index("created_at")
            self._col("warnings").create_index("user_id")
            self._col("quests").create_index([("user_id", 1), ("quest_date", 1)], unique=True)
        except Exception as e:
            logger.debug(f"Index error: {e}")

    # ──────────── ПОЛЬЗОВАТЕЛИ ────────────

    def get_user(self, user_id: int) -> Optional[Dict]:
        user = self._col("users").find_one({"user_id": user_id})
        if user:
            user.pop("_id", None)
            user.setdefault("cards", [])
            user.setdefault("arena_cards", [])
            user.setdefault("coins", 0)
            user.setdefault("mults", 0)
            user.setdefault("spin_tickets", 0)
            user.setdefault("shields", 0)
            user.setdefault("rating", 0)
            user.setdefault("wins", 0)
            user.setdefault("losses", 0)
            user.setdefault("daily_streak", 0)
            user.setdefault("pity_counter", 0)
            user.setdefault("last_epic_spin", 0)
            user.setdefault("last_legendary_spin", 0)
            user.setdefault("last_mythic_spin", 0)
            user.setdefault("total_mults_earned", 0)
            user.setdefault("total_fusions", 0)
            user.setdefault("luck_boost", 1.0)
            user.setdefault("luck_boost_until", None)
            user.setdefault("fusion_tokens", 0)
            user.setdefault("tickets", 0)
        return user

    def create_user(self, user_id: int, username: str = None, first_name: str = None):
        try:
            self._col("users").update_one(
                {"user_id": user_id},
                {
                    "$setOnInsert": {
                        "user_id": user_id,
                        "cards": [],
                        "arena_cards": [],
                        "coins": 0,
                        "mults": 0,
                        "spin_tickets": 1,
                        "shields": 0,
                        "rating": 0,
                        "wins": 0,
                        "losses": 0,
                        "daily_streak": 0,
                        "pity_counter": 0,
                        "last_epic_spin": 0,
                        "last_legendary_spin": 0,
                        "last_mythic_spin": 0,
                        "total_mults_earned": 0,
                        "total_fusions": 0,
                        "luck_boost": 1.0,
                        "luck_boost_until": None,
                        "fusion_tokens": 0,
                        "tickets": 0,
                        "created_at": datetime.now().isoformat()
                    },
                    "$set": {
                        "username": username,
                        "first_name": first_name
                    }
                },
                upsert=True
            )
        except Exception as e:
            logger.error(f"create_user error: {e}")

    def update_user(self, user_id: int, data: dict):
        if data:
            self._col("users").update_one({"user_id": user_id}, {"$set": data})

    # ──────────── MULTS ────────────

    def get_mults(self, user_id: int) -> int:
        user = self.get_user(user_id)
        return user.get("mults", 0) if user else 0

    def add_mults(self, user_id: int, amount: int):
        if amount <= 0:
            return
        self._col("users").update_one(
            {"user_id": user_id},
            {"$inc": {"mults": amount, "total_mults_earned": amount}}
        )

    def remove_mults(self, user_id: int, amount: int) -> bool:
        if amount <= 0:
            return True
        result = self._col("users").update_one(
            {"user_id": user_id, "mults": {"$gte": amount}},
            {"$inc": {"mults": -amount}}
        )
        return result.modified_count > 0

    def set_mults(self, user_id: int, amount: int):
        self._col("users").update_one(
            {"user_id": user_id},
            {"$set": {"mults": max(0, amount)}}
        )

    def exchange_coins_to_mults(self, user_id: int, coins_amount: int) -> Dict:
        if coins_amount < 100:
            return {"success": False, "error": "Минимум 100 монет", "mults_received": 0, "coins_spent": 0}

        mults_to_give = coins_amount // 100
        coins_to_spend = mults_to_give * 100

        user = self.get_user(user_id)
        if not user or user.get("coins", 0) < coins_to_spend:
            return {"success": False, "error": "Недостаточно монет", "mults_received": 0, "coins_spent": 0}

        self._col("users").update_one(
            {"user_id": user_id},
            {"$inc": {"coins": -coins_to_spend, "mults": mults_to_give, "total_mults_earned": mults_to_give}}
        )

        self._col("mults_history").insert_one({
            "user_id": user_id,
            "coins_spent": coins_to_spend,
            "mults_received": mults_to_give,
            "exchanged_at": datetime.now().isoformat()
        })

        return {"success": True, "mults_received": mults_to_give, "coins_spent": coins_to_spend, "error": ""}

    def get_exchange_history(self, user_id: int, limit: int = 10) -> List[Dict]:
        cursor = self._col("mults_history").find(
            {"user_id": user_id}
        ).sort("exchanged_at", DESCENDING).limit(limit)
        return [{k: v for k, v in doc.items() if k != "_id"} for doc in cursor]

    # ──────────── LUCK BOOST ────────────

    def set_luck_boost(self, user_id: int, multiplier: float, until: str):
        self._col("users").update_one(
            {"user_id": user_id},
            {"$set": {"luck_boost": multiplier, "luck_boost_until": until}}
        )

    def get_luck_boost(self, user_id: int) -> tuple:
        user = self.get_user(user_id)
        if not user:
            return 1.0, None
        multiplier = user.get("luck_boost", 1.0)
        until = user.get("luck_boost_until")
        if until:
            try:
                until_dt = datetime.fromisoformat(until) if isinstance(until, str) else until
                if until_dt <= datetime.now():
                    self._col("users").update_one(
                        {"user_id": user_id},
                        {"$set": {"luck_boost": 1.0}, "$unset": {"luck_boost_until": ""}}
                    )
                    return 1.0, None
            except:
                pass
        return multiplier, until

    def remove_luck_boost(self, user_id: int):
        self._col("users").update_one(
            {"user_id": user_id},
            {"$set": {"luck_boost": 1.0}, "$unset": {"luck_boost_until": ""}}
        )

    # ──────────── FUSION ────────────

    def add_fusion_history(self, user_id: int, card1: str, card2: str, result: str):
        self._col("fusion_history").insert_one({
            "user_id": user_id,
            "card1_name": card1,
            "card2_name": card2,
            "result_card_name": result,
            "fused_at": datetime.now().isoformat()
        })
        self._col("users").update_one(
            {"user_id": user_id},
            {"$inc": {"total_fusions": 1}}
        )

    def get_fusion_history(self, user_id: int, limit: int = 10) -> List[Dict]:
        cursor = self._col("fusion_history").find(
            {"user_id": user_id}
        ).sort("fused_at", DESCENDING).limit(limit)
        return [{"card1": d["card1_name"], "card2": d["card2_name"], "result": d["result_card_name"], "fused_at": d["fused_at"]} for d in cursor]

    def get_total_fusions(self, user_id: int) -> int:
        user = self.get_user(user_id)
        return user.get("total_fusions", 0) if user else 0

    def add_fusion_tokens(self, user_id: int, amount: int):
        if amount <= 0:
            return
        self._col("users").update_one(
            {"user_id": user_id},
            {"$inc": {"fusion_tokens": amount}}
        )

    def remove_fusion_tokens(self, user_id: int, amount: int) -> bool:
        if amount <= 0:
            return True
        result = self._col("users").update_one(
            {"user_id": user_id, "fusion_tokens": {"$gte": amount}},
            {"$inc": {"fusion_tokens": -amount}}
        )
        return result.modified_count > 0

    def get_fusion_tokens(self, user_id: int) -> int:
        user = self.get_user(user_id)
        return user.get("fusion_tokens", 0) if user else 0

    # ──────────── DAILY ────────────

    def get_daily_info(self, user_id: int):
        user = self.get_user(user_id)
        if not user:
            return {"can_claim": True, "streak": 0, "next_claim": None}
        last_daily = user.get("last_daily")
        streak = user.get("daily_streak", 0)
        if not last_daily:
            return {"can_claim": True, "streak": 0, "next_claim": None}
        try:
            last_time = datetime.fromisoformat(last_daily)
            now = datetime.now()
            days_diff = (now.date() - last_time.date()).days
            if days_diff == 0:
                tomorrow = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
                return {"can_claim": False, "streak": streak, "next_claim": tomorrow}
            elif days_diff == 1:
                return {"can_claim": True, "streak": streak, "next_claim": None}
            else:
                return {"can_claim": True, "streak": 0, "next_claim": None}
        except:
            return {"can_claim": True, "streak": 0, "next_claim": None}

    def claim_daily(self, user_id: int):
        info = self.get_daily_info(user_id)
        if not info["can_claim"]:
            return {"success": False, "reason": "already_claimed", "next_claim": info["next_claim"]}
        new_streak = info["streak"] + 1
        if new_streak > 7:
            new_streak = 1
        self._col("users").update_one(
            {"user_id": user_id},
            {"$set": {"daily_streak": new_streak, "last_daily": datetime.now().isoformat()}}
        )
        return {"success": True, "streak": new_streak}

    # ──────────── PITY ────────────

    def get_pity_counters(self, user_id: int):
        user = self.get_user(user_id)
        if not user:
            return {"total": 0, "since_epic": 0, "since_legendary": 0, "since_mythic": 0}
        total = user.get("pity_counter", 0)
        return {
            "total": total,
            "since_epic": total - user.get("last_epic_spin", 0),
            "since_legendary": total - user.get("last_legendary_spin", 0),
            "since_mythic": total - user.get("last_mythic_spin", 0),
        }

    def increment_pity(self, user_id: int):
        self._col("users").update_one({"user_id": user_id}, {"$inc": {"pity_counter": 1}})

    def reset_pity_for_rarity(self, user_id: int, rarity: str):
        user = self.get_user(user_id)
        if not user:
            return
        current = user.get("pity_counter", 0)
        update = {}
        if rarity in ["epic", "legendary", "mythic", "special", "mega", "limited"]:
            update["last_epic_spin"] = current
        if rarity in ["legendary", "mythic", "special", "mega", "limited"]:
            update["last_legendary_spin"] = current
        if rarity in ["mythic", "special", "mega", "limited"]:
            update["last_mythic_spin"] = current
        if update:
            self._col("users").update_one({"user_id": user_id}, {"$set": update})

    # ──────────── LIMITED CARDS ────────────

    def get_limited_card_count(self, card_name: str) -> int:
        return self._col("limited_cards").count_documents({"card_name": card_name})

    def issue_limited_card(self, card_name: str, user_id: int) -> bool:
        try:
            self._col("limited_cards").insert_one({
                "card_name": card_name,
                "user_id": user_id,
                "issued_at": datetime.now().isoformat()
            })
            return True
        except DuplicateKeyError:
            return False

    def user_has_limited_card(self, user_id: int, card_name: str) -> bool:
        return self._col("limited_cards").find_one({"user_id": user_id, "card_name": card_name}) is not None

    # ──────────── TICKETS ────────────

    def get_spin_tickets(self, user_id: int) -> int:
        user = self.get_user(user_id)
        return user.get("spin_tickets", 0) if user else 0

    def add_spin_tickets(self, user_id: int, amount: int = 1):
        if amount <= 0:
            return
        self._col("users").update_one({"user_id": user_id}, {"$inc": {"spin_tickets": amount}})

    def add_tickets(self, user_id: int, amount: int = 1):
        self.add_spin_tickets(user_id, amount)

    def use_spin_ticket(self, user_id: int) -> bool:
        result = self._col("users").update_one(
            {"user_id": user_id, "spin_tickets": {"$gt": 0}},
            {"$inc": {"spin_tickets": -1}, "$set": {"last_spin": datetime.now().isoformat()}}
        )
        return result.modified_count > 0

    def check_and_give_free_ticket(self, user_id: int):
        user = self.get_user(user_id)
        if not user:
            return False, 0
        last_free = user.get("last_free_ticket")
        if not last_free:
            self._give_free_ticket(user_id)
            return True, 0
        try:
            last_time = datetime.fromisoformat(last_free)
            next_time = last_time + timedelta(minutes=30)
            now = datetime.now()
            if now >= next_time:
                self._give_free_ticket(user_id)
                return True, 0
            else:
                return False, int((next_time - now).total_seconds() / 60) + 1
        except:
            self._give_free_ticket(user_id)
            return True, 0

    def _give_free_ticket(self, user_id: int):
        self._col("users").update_one(
            {"user_id": user_id},
            {"$inc": {"spin_tickets": 1}, "$set": {"last_free_ticket": datetime.now().isoformat()}}
        )

    def get_time_until_free_ticket(self, user_id: int) -> int:
        user = self.get_user(user_id)
        if not user:
            return 0
        last_free = user.get("last_free_ticket")
        if not last_free:
            return 0
        try:
            last_time = datetime.fromisoformat(last_free)
            next_time = last_time + timedelta(minutes=30)
            now = datetime.now()
            if now >= next_time:
                return 0
            return int((next_time - now).total_seconds() / 60) + 1
        except:
            return 0

    def reset_free_ticket_cooldown(self, user_id: int):
        self._col("users").update_one({"user_id": user_id}, {"$unset": {"last_free_ticket": ""}})

    def reset_ticket_cooldown(self, user_id: int):
        self.reset_free_ticket_cooldown(user_id)

    # ──────────── CARDS ────────────

    def add_card(self, user_id: int, card: dict):
        self._col("users").update_one({"user_id": user_id}, {"$push": {"cards": card}})

    def remove_card_from_user(self, user_id: int, card_name: str) -> bool:
        user = self.get_user(user_id)
        if not user:
            return False
        cards = user.get("cards", [])
        for i, c in enumerate(cards):
            if c["name"] == card_name:
                cards.pop(i)
                self._col("users").update_one({"user_id": user_id}, {"$set": {"cards": cards}})
                return True
        return False

    def clear_user_cards(self, user_id: int):
        self._col("users").update_one({"user_id": user_id}, {"$set": {"cards": []}})

    def get_user_card_count(self, user_id: int, card_name: str) -> int:
        user = self.get_user(user_id)
        if not user:
            return 0
        return sum(1 for c in user.get("cards", []) if c["name"] == card_name)

    # ──────────── COINS & SHIELDS ────────────

    def get_coins(self, user_id: int) -> int:
        user = self.get_user(user_id)
        return user.get("coins", 0) if user else 0

    def add_coins(self, user_id: int, amount: int):
        if amount == 0:
            return
        self._col("users").update_one({"user_id": user_id}, {"$inc": {"coins": amount}})
        self._col("users").update_one({"user_id": user_id, "coins": {"$lt": 0}}, {"$set": {"coins": 0}})

    def remove_coins(self, user_id: int, amount: int) -> bool:
        if amount <= 0:
            return True
        result = self._col("users").update_one(
            {"user_id": user_id, "coins": {"$gte": amount}},
            {"$inc": {"coins": -amount}}
        )
        return result.modified_count > 0

    def set_coins(self, user_id: int, amount: int):
        self._col("users").update_one({"user_id": user_id}, {"$set": {"coins": max(0, amount)}})

    def get_shields(self, user_id: int) -> int:
        user = self.get_user(user_id)
        return user.get("shields", 0) if user else 0

    def add_shields(self, user_id: int, amount: int):
        if amount <= 0:
            return
        self._col("users").update_one({"user_id": user_id}, {"$inc": {"shields": amount}})

    def use_shield(self, user_id: int) -> bool:
        result = self._col("users").update_one(
            {"user_id": user_id, "shields": {"$gt": 0}},
            {"$inc": {"shields": -1}}
        )
        return result.modified_count > 0

    # ──────────── ARENA ────────────

    def set_arena_cards(self, user_id: int, cards: list):
        self._col("users").update_one({"user_id": user_id}, {"$set": {"arena_cards": cards}})

    def get_arena_cards(self, user_id: int) -> list:
        user = self.get_user(user_id)
        return user.get("arena_cards", []) if user else []

    def join_arena_queue(self, user_id: int, cards: list):
        self._col("arena_queue").update_one(
            {"user_id": user_id},
            {"$set": {"user_id": user_id, "cards": cards, "joined_at": datetime.now().isoformat()}},
            upsert=True
        )

    def leave_arena_queue(self, user_id: int):
        self._col("arena_queue").delete_one({"user_id": user_id})

    def get_arena_queue(self) -> list:
        cursor = self._col("arena_queue").find().sort("joined_at", ASCENDING)
        return [{"user_id": d["user_id"], "cards": d.get("cards", []), "joined_at": d.get("joined_at")} for d in cursor]

    def is_in_queue(self, user_id: int) -> bool:
        return self._col("arena_queue").find_one({"user_id": user_id}) is not None

    def add_battle(self, p1: int, p2: int, winner: int, p1_cards: list, p2_cards: list, log: str = ""):
        self._col("battles").insert_one({
            "player1_id": p1, "player2_id": p2, "winner_id": winner,
            "player1_cards": p1_cards, "player2_cards": p2_cards,
            "battle_log": log, "created_at": datetime.now().isoformat()
        })

    def update_rating(self, user_id: int, rating_change: int, is_win: bool):
        inc = {"rating": rating_change}
        if is_win:
            inc["wins"] = 1
        else:
            inc["losses"] = 1
        self._col("users").update_one({"user_id": user_id}, {"$inc": inc})
        self._col("users").update_one({"user_id": user_id, "rating": {"$lt": 0}}, {"$set": {"rating": 0}})

    def reset_user_rating(self, user_id: int):
        self._col("users").update_one(
            {"user_id": user_id},
            {"$set": {"rating": 0, "wins": 0, "losses": 0}}
        )

    # ──────────── MARKET ────────────

    def add_listing(self, user_id: int, card_name: str, price: int):
        self._col("market").insert_one({
            "seller_id": user_id, "card_name": card_name, "price": price,
            "created_at": datetime.now().isoformat(), "sold": False
        })

    def get_my_listings(self, user_id: int) -> list:
        cursor = self._col("market").find({"seller_id": user_id, "sold": False}).sort("created_at", DESCENDING)
        return [{"id": str(d["_id"]), "card_name": d["card_name"], "price": d["price"], "created_at": d.get("created_at")} for d in cursor]

    def get_all_listings(self) -> list:
        cursor = self._col("market").find({"sold": False}).sort("created_at", DESCENDING)
        return [{"id": str(d["_id"]), "seller_id": d["seller_id"], "card_name": d["card_name"], "price": d["price"], "created_at": d.get("created_at")} for d in cursor]

    def get_listing_by_id(self, listing_id) -> Optional[dict]:
        from bson import ObjectId
        try:
            doc = self._col("market").find_one({"_id": ObjectId(listing_id), "sold": False})
            if doc:
                return {"id": str(doc["_id"]), "seller_id": doc["seller_id"], "card_name": doc["card_name"], "price": doc["price"], "created_at": doc.get("created_at"), "sold": doc.get("sold", False)}
        except:
            pass
        return None

    def remove_listing(self, listing_id):
        from bson import ObjectId
        try:
            self._col("market").delete_one({"_id": ObjectId(listing_id)})
        except:
            pass

    def mark_listing_sold(self, listing_id, buyer_id: int):
        from bson import ObjectId
        try:
            self._col("market").update_one({"_id": ObjectId(listing_id)}, {"$set": {"sold": True, "buyer_id": buyer_id}})
        except:
            pass

    def get_market_listings(self, limit: int = 15) -> list:
        return self.get_all_listings()[:limit]

    # ──────────── TOP ────────────

    def get_top_players(self, limit: int = 10) -> list:
        cursor = self._col("users").find(
            {"$or": [{"rating": {"$gt": 0}}, {"wins": {"$gt": 0}}]}
        ).sort([("rating", DESCENDING), ("wins", DESCENDING)]).limit(limit)
        return [{"user_id": d["user_id"], "username": d.get("username"), "first_name": d.get("first_name"), "rating": d.get("rating", 0), "wins": d.get("wins", 0), "losses": d.get("losses", 0)} for d in cursor]

    def get_top_by_cards(self, limit: int = 10) -> list:
        cursor = self._col("users").find()
        result = []
        for d in cursor:
            cards = d.get("cards", [])
            if cards:
                unique = len(set(c["name"] for c in cards))
                result.append({"user_id": d["user_id"], "username": d.get("username"), "first_name": d.get("first_name"), "cards_count": len(cards), "unique_count": unique})
        return sorted(result, key=lambda x: (-x["cards_count"], -x["unique_count"]))[:limit]

    def get_top_by_coins(self, limit: int = 10) -> list:
        cursor = self._col("users").find({"coins": {"$gt": 0}}).sort("coins", DESCENDING).limit(limit)
        return [{"user_id": d["user_id"], "username": d.get("username"), "first_name": d.get("first_name"), "coins": d.get("coins", 0)} for d in cursor]

    def get_top_by_mults(self, limit: int = 10) -> list:
        cursor = self._col("users").find({"mults": {"$gt": 0}}).sort("mults", DESCENDING).limit(limit)
        return [{"user_id": d["user_id"], "username": d.get("username"), "first_name": d.get("first_name"), "mults": d.get("mults", 0)} for d in cursor]

    # ──────────── PROFILE ────────────

    def set_bio(self, user_id: int, bio: str):
        self._col("users").update_one({"user_id": user_id}, {"$set": {"bio": bio[:500]}})

    def set_profile_photo(self, user_id: int, photo_id: str):
        self._col("users").update_one({"user_id": user_id}, {"$set": {"profile_photo_id": photo_id}})

    def remove_profile_photo(self, user_id: int):
        self.set_profile_photo(user_id, "")

    # ──────────── WARNINGS ────────────

    def add_warning(self, user_id: int, reason: str, warned_by: int, duration_hours: int = None):
        expires_at = None
        if duration_hours:
            expires_at = (datetime.now() + timedelta(hours=duration_hours)).isoformat()
        self._col("warnings").insert_one({
            "user_id": user_id, "reason": reason, "warned_by": warned_by,
            "created_at": datetime.now().isoformat(), "expires_at": expires_at
        })

    def get_warnings(self, user_id: int) -> int:
        now = datetime.now().isoformat()
        self._col("warnings").delete_many({"user_id": user_id, "expires_at": {"$ne": None, "$lt": now}})
        return self._col("warnings").count_documents({"user_id": user_id})

    def get_warnings_list(self, user_id: int) -> list:
        now = datetime.now().isoformat()
        self._col("warnings").delete_many({"user_id": user_id, "expires_at": {"$ne": None, "$lt": now}})
        cursor = self._col("warnings").find({"user_id": user_id}).sort("created_at", DESCENDING)
        return [{"id": str(d["_id"]), "reason": d.get("reason"), "warned_by": d.get("warned_by"), "created_at": d.get("created_at"), "expires_at": d.get("expires_at")} for d in cursor]

    def clear_warnings(self, user_id: int):
        self._col("warnings").delete_many({"user_id": user_id})

    def remove_one_warning(self, user_id: int):
        warn = self._col("warnings").find_one({"user_id": user_id}, sort=[("created_at", DESCENDING)])
        if warn:
            self._col("warnings").delete_one({"_id": warn["_id"]})

    # ──────────── PUNISHMENTS ────────────

    def add_punishment(self, user_id: int, punishment_type: str, reason: str, punished_by: int, duration_minutes: int = None):
        expires_at = None
        if duration_minutes:
            expires_at = (datetime.now() + timedelta(minutes=duration_minutes)).isoformat()
        self._col("punishments").insert_one({
            "user_id": user_id, "punishment_type": punishment_type, "reason": reason,
            "punished_by": punished_by, "created_at": datetime.now().isoformat(),
            "expires_at": expires_at, "is_active": True
        })

    def remove_punishment(self, user_id: int, punishment_type: str):
        self._col("punishments").update_many(
            {"user_id": user_id, "punishment_type": punishment_type, "is_active": True},
            {"$set": {"is_active": False}}
        )

    def get_expired_punishments(self) -> list:
        now = datetime.now().isoformat()
        cursor = self._col("punishments").find({"is_active": True, "expires_at": {"$ne": None, "$lt": now}})
        return [{"id": str(d["_id"]), "user_id": d["user_id"], "punishment_type": d["punishment_type"], "chat_id": self.chat_id} for d in cursor]

    def deactivate_punishment(self, punishment_id):
        from bson import ObjectId
        try:
            self._col("punishments").update_one({"_id": ObjectId(punishment_id)}, {"$set": {"is_active": False}})
        except:
            pass

    # ──────────── RULES ────────────

    def get_rules(self) -> str:
        doc = self._col("settings").find_one({"key": "rules"})
        return doc.get("value", "") if doc else ""

    def set_rules(self, rules: str):
        self._col("settings").update_one({"key": "rules"}, {"$set": {"value": rules}}, upsert=True)

    # ──────────── PROMO CODES ────────────

    def user_used_promo_code(self, user_id: int, promo_code: str) -> bool:
        return self._col("used_promos").find_one({"user_id": user_id, "promo_code": promo_code}) is not None

    def use_promo_code(self, user_id: int, promo_code: str):
        try:
            self._col("used_promos").insert_one({"user_id": user_id, "promo_code": promo_code, "used_at": datetime.now().isoformat()})
        except:
            pass

    # ──────────── QUESTS ────────────

    def get_user_quests(self, user_id: int):
        today = date.today().isoformat()
        doc = self._col("quests").find_one({"user_id": user_id, "quest_date": today})
        if doc:
            return {"quests": doc.get("quests", []), "last_reset": doc.get("last_reset", today)}
        return None

    def set_user_quests(self, user_id: int, quests_data):
        today = date.today().isoformat()
        if isinstance(quests_data, dict):
            quests_list = quests_data.get("quests", [])
            last_reset = quests_data.get("last_reset", datetime.now().isoformat())
        elif isinstance(quests_data, list):
            quests_list = quests_data
            last_reset = datetime.now().isoformat()
        else:
            return
        self._col("quests").update_one(
            {"user_id": user_id, "quest_date": today},
            {"$set": {"quests": quests_list, "last_reset": last_reset}},
            upsert=True
        )

    # ──────────── EVENTS ────────────

    def create_event(self, name, description, event_type, start_date, end_date, rewards, created_by):
        result = self._col("events").insert_one({
            "name": name, "description": description, "event_type": event_type,
            "start_date": start_date, "end_date": end_date, "rewards": rewards,
            "is_active": True, "created_by": created_by, "created_at": datetime.now().isoformat()
        })
        return str(result.inserted_id)

    def get_active_events(self) -> list:
        now = datetime.now().isoformat()
        cursor = self._col("events").find({"is_active": True, "start_date": {"$lte": now}, "end_date": {"$gte": now}}).sort("end_date", ASCENDING)
        return [{"id": str(d["_id"]), "name": d["name"], "description": d.get("description"), "event_type": d.get("event_type"), "start_date": d["start_date"], "end_date": d["end_date"], "rewards": d.get("rewards", {}), "is_active": d.get("is_active", True)} for d in cursor]

    def get_event_by_id(self, event_id):
        from bson import ObjectId
        try:
            doc = self._col("events").find_one({"_id": ObjectId(event_id)})
            if doc:
                return {"id": str(doc["_id"]), "name": doc["name"], "description": doc.get("description"), "event_type": doc.get("event_type"), "start_date": doc["start_date"], "end_date": doc["end_date"], "rewards": doc.get("rewards", {}), "is_active": doc.get("is_active", True)}
        except:
            pass
        return None

    def end_event(self, event_id):
        from bson import ObjectId
        try:
            self._col("events").update_one({"_id": ObjectId(event_id)}, {"$set": {"is_active": False}})
        except:
            pass

    def join_event(self, event_id, user_id):
        from bson import ObjectId
        try:
            self._col("event_participants").update_one(
                {"event_id": ObjectId(event_id), "user_id": user_id},
                {"$setOnInsert": {"score": 0, "joined_at": datetime.now().isoformat()}},
                upsert=True
            )
        except:
            pass

    def add_event_score(self, event_id, user_id, score):
        from bson import ObjectId
        try:
            self._col("event_participants").update_one({"event_id": ObjectId(event_id), "user_id": user_id}, {"$inc": {"score": score}})
        except:
            pass

    def get_event_leaderboard(self, event_id, limit=10):
        from bson import ObjectId
        try:
            cursor = self._col("event_participants").find({"event_id": ObjectId(event_id)}).sort("score", DESCENDING).limit(limit)
            result = []
            for d in cursor:
                user = self.get_user(d["user_id"])
                result.append({"user_id": d["user_id"], "score": d.get("score", 0), "username": user.get("username") if user else None, "first_name": user.get("first_name") if user else None})
            return result
        except:
            return []

    def get_user_event_score(self, event_id, user_id):
        from bson import ObjectId
        try:
            doc = self._col("event_participants").find_one({"event_id": ObjectId(event_id), "user_id": user_id})
            return doc.get("score", 0) if doc else 0
        except:
            return 0

    # ──────────── MARRIAGES ────────────

    def get_marriage(self, user_id):
        doc = self._col("marriages").find_one({"$or": [{"user1_id": user_id}, {"user2_id": user_id}]})
        if not doc:
            return None
        m = {"id": str(doc["_id"]), "user1_id": doc["user1_id"], "user2_id": doc["user2_id"], "married_at": doc["married_at"]}
        m["partner_id"] = m["user2_id"] if m["user1_id"] == user_id else m["user1_id"]
        return m

    def create_marriage(self, user1_id, user2_id):
        self._col("marriages").insert_one({"user1_id": user1_id, "user2_id": user2_id, "married_at": datetime.now().isoformat()})

    def delete_marriage(self, user_id):
        self._col("marriages").delete_one({"$or": [{"user1_id": user_id}, {"user2_id": user_id}]})

    def get_all_marriages(self):
        cursor = self._col("marriages").find().sort("married_at", ASCENDING)
        return [{"id": str(d["_id"]), "user1_id": d["user1_id"], "user2_id": d["user2_id"], "married_at": d["married_at"]} for d in cursor]

    def create_proposal(self, proposer_id, target_id):
        result = self._col("proposals").insert_one({"proposer_id": proposer_id, "target_id": target_id, "status": "pending", "created_at": datetime.now().isoformat()})
        return str(result.inserted_id)

    def get_pending_proposal(self, proposer_id, target_id):
        doc = self._col("proposals").find_one({"proposer_id": proposer_id, "target_id": target_id, "status": "pending"})
        if doc:
            return {"id": str(doc["_id"]), "proposer_id": doc["proposer_id"], "target_id": doc["target_id"], "status": doc["status"], "created_at": doc["created_at"]}
        return None

    def get_proposal_by_id(self, proposal_id):
        from bson import ObjectId
        try:
            doc = self._col("proposals").find_one({"_id": ObjectId(proposal_id)})
            if doc:
                return {"id": str(doc["_id"]), "proposer_id": doc["proposer_id"], "target_id": doc["target_id"], "status": doc["status"], "created_at": doc["created_at"]}
        except:
            pass
        return None

    def update_proposal_status(self, proposal_id, status):
        from bson import ObjectId
        try:
            self._col("proposals").update_one({"_id": ObjectId(proposal_id)}, {"$set": {"status": status}})
        except:
            pass

    # ──────────── RANKS ────────────

    def get_user_rank(self, user_id):
        doc = self._col("ranks").find_one({"user_id": user_id})
        if doc:
            return {"user_id": user_id, "rank_level": doc.get("rank_level", 0), "custom_title": doc.get("custom_title", ""), "promoted_by": doc.get("promoted_by")}
        return {"user_id": user_id, "rank_level": 0, "custom_title": "", "promoted_by": None}

    def set_user_rank(self, user_id, rank_level, custom_title="", promoted_by=None):
        self._col("ranks").update_one(
            {"user_id": user_id},
            {"$set": {"rank_level": rank_level, "custom_title": custom_title, "promoted_by": promoted_by, "promoted_at": datetime.now().isoformat()}},
            upsert=True
        )

    def get_chat_ranks(self):
        cursor = self._col("ranks").find({"rank_level": {"$gt": 0}}).sort("rank_level", DESCENDING)
        result = []
        for d in cursor:
            user = self.get_user(d["user_id"])
            result.append({"user_id": d["user_id"], "rank_level": d.get("rank_level", 0), "custom_title": d.get("custom_title", ""), "username": user.get("username") if user else None, "first_name": user.get("first_name") if user else None})
        return result

    # ──────────── MESSAGE STATS ────────────

    def record_message(self, user_id):
        today = date.today().isoformat()
        try:
            self._col("message_stats").update_one({"user_id": user_id}, {"$inc": {"message_count": 1}, "$set": {"last_message_date": today}}, upsert=True)
            self._col("message_history").update_one({"user_id": user_id, "date": today}, {"$inc": {"count": 1}}, upsert=True)
        except Exception as e:
            logger.debug(f"Message stat error: {e}")

    def get_top_messages_today(self, limit=10):
        today = date.today().isoformat()
        cursor = self._col("message_history").find({"date": today}).sort("count", DESCENDING).limit(limit)
        return [{"user_id": d["user_id"], "count": d["count"]} for d in cursor]

    def get_top_messages_month(self, limit=10):
        month_ago = (date.today() - timedelta(days=30)).isoformat()
        pipeline = [{"$match": {"date": {"$gte": month_ago}}}, {"$group": {"_id": "$user_id", "total": {"$sum": "$count"}}}, {"$sort": {"total": -1}}, {"$limit": limit}]
        result = list(self._col("message_history").aggregate(pipeline))
        return [{"user_id": d["_id"], "count": d["total"]} for d in result]

    def get_top_messages_all_time(self, limit=10):
        cursor = self._col("message_stats").find().sort("message_count", DESCENDING).limit(limit)
        return [{"user_id": d["user_id"], "count": d["message_count"]} for d in cursor]

    # ──────────── RESET ────────────

    def clear_user_all(self, user_id):
        self._col("users").update_one(
            {"user_id": user_id},
            {"$set": {
                "cards": [], "arena_cards": [], "coins": 0, "mults": 0,
                "rating": 0, "wins": 0, "losses": 0, "spin_tickets": 1,
                "shields": 0, "daily_streak": 0, "pity_counter": 0,
                "last_epic_spin": 0, "last_legendary_spin": 0, "last_mythic_spin": 0,
                "total_mults_earned": 0, "total_fusions": 0, "luck_boost": 1.0,
                "fusion_tokens": 0, "tickets": 0
            }, "$unset": {"last_daily": "", "last_free_ticket": "", "luck_boost_until": ""}}
        )


# ════════════════════════════════════════════════════
#          GlobalDatabase — ИСПРАВЛЕННЫЙ
# ════════════════════════════════════════════════════

class GlobalDatabase:
    def __init__(self):
        self.db = MongoDB.get_db()
        self._ensure_indexes()

    def _ensure_indexes(self):
        try:
            self.db.users_global.create_index("user_id", unique=True)
            self.db.users_global.create_index("username")
            # ИСПРАВЛЕНО: составной индекс user_id + chat_id
            self.db.spin_boosts.drop_indexes()
            self.db.spin_boosts.create_index([("user_id", 1), ("chat_id", 1)], unique=True)
        except Exception as e:
            logger.debug(f"Global index error: {e}")

    def update_user(self, user_id: int, username: str = None, first_name: str = None):
        self.db.users_global.update_one(
            {"user_id": user_id},
            {"$set": {"username": username, "first_name": first_name, "last_seen": datetime.now().isoformat()}},
            upsert=True
        )

    def find_by_username(self, username: str):
        doc = self.db.users_global.find_one({"username": {"$regex": f"^{username}$", "$options": "i"}})
        if doc:
            return {"user_id": doc["user_id"], "username": doc.get("username"), "first_name": doc.get("first_name")}
        return None

    def set_spin_boost(self, user_id: int, multiplier: float, duration_hours: int = None, chat_id: int = None):
        """
        Установить буст удачи.
        Если chat_id указан — буст только для этой группы.
        Если chat_id=None — используем 0 как "глобальный" (но по факту не будет матчиться).
        """
        expires_at = None
        if duration_hours:
            expires_at = (datetime.now() + timedelta(hours=duration_hours)).isoformat()

        cid = chat_id or 0

        self.db.spin_boosts.update_one(
            {"user_id": user_id, "chat_id": cid},
            {"$set": {
                "multiplier": multiplier,
                "created_at": datetime.now().isoformat(),
                "expires_at": expires_at
            }},
            upsert=True
        )

    def get_spin_boost(self, user_id: int, chat_id: int = None) -> float:
        """
        Получить буст удачи для конкретной группы.
        Без chat_id — возвращает 1.0 (нет глобального буста).
        """
        now = datetime.now().isoformat()

        # Удаляем все истёкшие бусты этого юзера
        self.db.spin_boosts.delete_many({
            "user_id": user_id,
            "expires_at": {"$ne": None, "$lt": now}
        })

        if not chat_id:
            return 1.0

        # Ищем буст для конкретной группы
        doc = self.db.spin_boosts.find_one({"user_id": user_id, "chat_id": chat_id})
        if doc:
            return doc.get("multiplier", 1.0)

        return 1.0

    def remove_spin_boost(self, user_id: int, chat_id: int = None):
        """Удалить буст. Если chat_id — только для этой группы, иначе все."""
        if chat_id:
            self.db.spin_boosts.delete_one({"user_id": user_id, "chat_id": chat_id})
        else:
            self.db.spin_boosts.delete_many({"user_id": user_id})


class DatabaseManager:
    _instances: Dict[int, GroupDatabase] = {}
    _global_db: Optional[GlobalDatabase] = None

    @classmethod
    def get_db(cls, chat_id: int) -> GroupDatabase:
        if chat_id not in cls._instances:
            cls._instances[chat_id] = GroupDatabase(chat_id)
        return cls._instances[chat_id]

    @classmethod
    def get_group_db(cls, chat_id: int) -> GroupDatabase:
        return cls.get_db(chat_id)

    @classmethod
    def get_global_db(cls) -> GlobalDatabase:
        if cls._global_db is None:
            cls._global_db = GlobalDatabase()
        return cls._global_db

    @classmethod
    def get_all_group_dbs(cls) -> List[GroupDatabase]:
        return list(cls._instances.values())


class LegacyDB:
    def get_user(self, user_id, chat_id=None):
        if chat_id:
            return DatabaseManager.get_db(chat_id).get_user(user_id)
        return None

    def create_user(self, user_id, username=None, first_name=None, chat_id=None):
        if chat_id:
            DatabaseManager.get_db(chat_id).create_user(user_id, username, first_name)
        DatabaseManager.get_global_db().update_user(user_id, username, first_name)


db = LegacyDB()