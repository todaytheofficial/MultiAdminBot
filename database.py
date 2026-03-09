# database.py
import os
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pymongo import MongoClient, DESCENDING, ASCENDING

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
            self._col("warnings").create_index("user_id")
        except Exception as e:
            logger.debug(f"Index error: {e}")

    # ══════════════════════════════════════════════════
    #                   ПОЛЬЗОВАТЕЛИ
    # ══════════════════════════════════════════════════

    def get_user(self, user_id: int) -> Optional[Dict]:
        user = self._col("users").find_one({"user_id": user_id})
        if user:
            user.pop("_id", None)
            user.setdefault("cards", [])
            user.setdefault("arena_cards", [])
            user.setdefault("coins", 0)
            user.setdefault("spin_tickets", 0)
            user.setdefault("shields", 0)
            user.setdefault("rating", 0)
            user.setdefault("wins", 0)
            user.setdefault("losses", 0)
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
                        "spin_tickets": 1,
                        "shields": 0,
                        "rating": 0,
                        "wins": 0,
                        "losses": 0,
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

    def update_user_field(self, user_id: int, field: str, value):
        """Обновить одно поле пользователя"""
        self._col("users").update_one(
            {"user_id": user_id},
            {"$set": {field: value}}
        )

    # ══════════════════════════════════════════════════
    #                     TICKETS
    # ══════════════════════════════════════════════════

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
        except Exception:
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
        except Exception:
            return 0

    def reset_ticket_cooldown(self, user_id: int):
        self._col("users").update_one({"user_id": user_id}, {"$unset": {"last_free_ticket": ""}})

    # ══════════════════════════════════════════════════
    #                      CARDS
    # ══════════════════════════════════════════════════

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

    # ══════════════════════════════════════════════════
    #                 COINS & SHIELDS
    # ══════════════════════════════════════════════════

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

    # ══════════════════════════════════════════════════
    #                      ARENA
    # ══════════════════════════════════════════════════

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

    # ══════════════════════════════════════════════════
    #                      MARKET
    # ══════════════════════════════════════════════════

    def add_listing(self, user_id: int, card_name: str, price: int):
        self._col("market").insert_one({
            "seller_id": user_id, "card_name": card_name, "price": price,
            "created_at": datetime.now().isoformat(), "sold": False
        })

    def get_my_listings(self, user_id: int) -> list:
        cursor = self._col("market").find({"seller_id": user_id, "sold": False}).sort("created_at", DESCENDING)
        return [{"id": str(d["_id"]), "card_name": d["card_name"], "price": d["price"]} for d in cursor]

    def get_all_listings(self) -> list:
        cursor = self._col("market").find({"sold": False}).sort("created_at", DESCENDING)
        return [{"id": str(d["_id"]), "seller_id": d["seller_id"], "card_name": d["card_name"], "price": d["price"]} for d in cursor]

    def get_listing_by_id(self, listing_id) -> Optional[dict]:
        from bson import ObjectId
        try:
            doc = self._col("market").find_one({"_id": ObjectId(listing_id), "sold": False})
            if doc:
                return {"id": str(doc["_id"]), "seller_id": doc["seller_id"], "card_name": doc["card_name"], "price": doc["price"]}
        except Exception:
            pass
        return None

    def remove_listing(self, listing_id):
        from bson import ObjectId
        try:
            self._col("market").delete_one({"_id": ObjectId(listing_id)})
        except Exception:
            pass

    # ══════════════════════════════════════════════════
    #                       TOP
    # ══════════════════════════════════════════════════

    def get_top_players(self, limit: int = 10) -> list:
        cursor = self._col("users").find(
            {"$or": [{"rating": {"$gt": 0}}, {"wins": {"$gt": 0}}]}
        ).sort([("rating", DESCENDING), ("wins", DESCENDING)]).limit(limit)
        return [{"user_id": d["user_id"], "first_name": d.get("first_name"), "rating": d.get("rating", 0), "wins": d.get("wins", 0), "losses": d.get("losses", 0)} for d in cursor]

    def get_top_by_cards(self, limit: int = 10) -> list:
        cursor = self._col("users").find()
        result = []
        for d in cursor:
            cards = d.get("cards", [])
            if cards:
                result.append({"user_id": d["user_id"], "first_name": d.get("first_name"), "cards_count": len(cards)})
        return sorted(result, key=lambda x: -x["cards_count"])[:limit]

    def get_top_by_coins(self, limit: int = 10) -> list:
        cursor = self._col("users").find({"coins": {"$gt": 0}}).sort("coins", DESCENDING).limit(limit)
        return [{"user_id": d["user_id"], "first_name": d.get("first_name"), "coins": d.get("coins", 0)} for d in cursor]

    # ══════════════════════════════════════════════════
    #                     PROFILE
    # ══════════════════════════════════════════════════

    def set_bio(self, user_id: int, bio: str):
        self._col("users").update_one({"user_id": user_id}, {"$set": {"bio": bio[:500]}})

    # ══════════════════════════════════════════════════
    #                    WARNINGS
    # ══════════════════════════════════════════════════

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
        return [{"reason": d.get("reason"), "expires_at": d.get("expires_at")} for d in cursor]

    def clear_warnings(self, user_id: int):
        self._col("warnings").delete_many({"user_id": user_id})

    def remove_one_warning(self, user_id: int):
        warn = self._col("warnings").find_one({"user_id": user_id}, sort=[("created_at", DESCENDING)])
        if warn:
            self._col("warnings").delete_one({"_id": warn["_id"]})

    # ══════════════════════════════════════════════════
    #                   PUNISHMENTS
    # ══════════════════════════════════════════════════

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

    # ══════════════════════════════════════════════════
    #                      RULES
    # ══════════════════════════════════════════════════

    def get_rules(self) -> str:
        doc = self._col("settings").find_one({"key": "rules"})
        return doc.get("value", "") if doc else ""

    def set_rules(self, rules: str):
        self._col("settings").update_one({"key": "rules"}, {"$set": {"value": rules}}, upsert=True)

    # ══════════════════════════════════════════════════
    #                      RANKS
    # ══════════════════════════════════════════════════

    def get_user_rank(self, user_id: int):
        doc = self._col("ranks").find_one({"user_id": user_id})
        if doc:
            return {"user_id": user_id, "rank_level": doc.get("rank_level", 0), "custom_title": doc.get("custom_title", ""), "promoted_by": doc.get("promoted_by")}
        return {"user_id": user_id, "rank_level": 0, "custom_title": "", "promoted_by": None}

    def set_user_rank(self, user_id: int, rank_level: int, custom_title: str = "", promoted_by: int = None):
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
            result.append({
                "user_id": d["user_id"],
                "rank_level": d.get("rank_level", 0),
                "custom_title": d.get("custom_title", ""),
                "username": user.get("username") if user else None,
                "first_name": user.get("first_name") if user else None
            })
        return result

# database.py — добавь этот метод в класс GroupDatabase, после метода remove_card_from_user

def remove_cards_by_rarity(self, user_id: int, rarity: str, count: int) -> bool:
    """Удаляет N карт определённой редкости у пользователя. Возвращает True если хватило карт."""
    user = self.get_user(user_id)
    if not user:
        return False
    
    cards = user.get("cards", [])
    
    # Считаем сколько карт нужной редкости
    rarity_count = sum(1 for c in cards if c.get("rarity") == rarity)
    if rarity_count < count:
        return False
    
    # Удаляем N карт этой редкости (сначала дубликаты — одинаковые имена)
    # Считаем количество каждой карты
    name_counts = {}
    for c in cards:
        if c.get("rarity") == rarity:
            name_counts[c["name"]] = name_counts.get(c["name"], 0) + 1
    
    # Сортируем: сначала удаляем те, которых больше всего (дупы)
    sorted_names = sorted(name_counts.items(), key=lambda x: -x[1])
    
    to_remove = count
    remove_plan = {}  # name -> сколько удалить
    
    for name, cnt in sorted_names:
        if to_remove <= 0:
            break
        can_remove = min(cnt, to_remove)
        remove_plan[name] = can_remove
        to_remove -= can_remove
    
    # Применяем удаление
    new_cards = []
    removed_counts = {}
    for c in cards:
        name = c["name"]
        if c.get("rarity") == rarity and name in remove_plan:
            already_removed = removed_counts.get(name, 0)
            if already_removed < remove_plan[name]:
                removed_counts[name] = already_removed + 1
                continue  # пропускаем (удаляем)
        new_cards.append(c)
    
    self._col("users").update_one(
        {"user_id": user_id},
        {"$set": {"cards": new_cards}}
    )
    return True

    # ══════════════════════════════════════════════════
    #                      RESET
    # ══════════════════════════════════════════════════

    def clear_user_all(self, user_id: int):
        self._col("users").update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "cards": [],
                    "arena_cards": [],
                    "coins": 0,
                    "rating": 0,
                    "wins": 0,
                    "losses": 0,
                    "spin_tickets": 1,
                    "shields": 0
                },
                "$unset": {
                    "last_free_ticket": "",
                    "last_spin_time": "",
                    "last_multispin_time": ""
                }
            }
        )


# ══════════════════════════════════════════════════
#               GlobalDatabase
# ══════════════════════════════════════════════════

class GlobalDatabase:
    def __init__(self):
        self.db = MongoDB.get_db()
        self._ensure_indexes()

    def _ensure_indexes(self):
        try:
            self.db.users_global.create_index("user_id", unique=True)
            self.db.users_global.create_index("username")
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


# ══════════════════════════════════════════════════
#               DatabaseManager
# ══════════════════════════════════════════════════

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