import sqlite3
import json
import os
import time
from typing import Optional

DB_PATH = os.getenv("DB_PATH", "game_data.db")

RANKS = [
    {"level": 1,  "name": "🌱 Новичок",        "xp_needed": 0},
    {"level": 2,  "name": "📚 Ученик",          "xp_needed": 100},
    {"level": 3,  "name": "✏️ Грамотей",        "xp_needed": 250},
    {"level": 4,  "name": "🔤 Знаток букв",     "xp_needed": 500},
    {"level": 5,  "name": "💬 Словоблуд",       "xp_needed": 900},
    {"level": 6,  "name": "📖 Книгочей",        "xp_needed": 1400},
    {"level": 7,  "name": "🧠 Эрудит",          "xp_needed": 2000},
    {"level": 8,  "name": "🏆 Чемпион слов",    "xp_needed": 3000},
    {"level": 9,  "name": "⭐ Мастер",          "xp_needed": 4500},
    {"level": 10, "name": "👑 Гроссмейстер",    "xp_needed": 7000},
    {"level": 11, "name": "🔥 Легенда",         "xp_needed": 10000},
    {"level": 12, "name": "💎 Бессмертный",     "xp_needed": 15000},
]

LEVEL_UP_REWARDS = {
    2:  {"hints": 2, "title": "📚 Первые шаги"},
    3:  {"hints": 2, "title": "✏️ Грамотей"},
    4:  {"hints": 3, "skip_skips": 1, "title": "🔤 Знаток"},
    5:  {"hints": 3, "word_replaces": 1, "title": "💬 Словоблуд"},
    6:  {"hints": 4, "skip_skips": 1, "title": "📖 Книгочей"},
    7:  {"hints": 5, "skip_skips": 2, "title": "🧠 Эрудит"},
    8:  {"hints": 5, "skip_skips": 2, "word_replaces": 1, "title": "🏆 Чемпион"},
    9:  {"hints": 7, "skip_skips": 3, "title": "⭐ Мастер"},
    10: {"hints": 10, "skip_skips": 3, "title": "👑 Гроссмейстер"},
    11: {"hints": 15, "skip_skips": 5, "word_replaces": 2, "title": "🔥 Легенда"},
    12: {"hints": 20, "skip_skips": 7, "word_replaces": 2, "title": "💎 Бессмертный"},
}

STREAK_REWARDS = {
    3:  {"coins": 50,   "msg": "🔥 3 дня подряд! +50 монет"},
    7:  {"coins": 150,  "msg": "🔥 7 дней подряд! +150 монет"},
    14: {"coins": 400,  "msg": "🔥 2 недели подряд! +400 монет"},
    30: {"coins": 1000, "msg": "🔥 30 дней подряд! +1000 монет"},
}

SHOP_ITEMS = {
    "hint":             {"name": "💡 Подсказка",           "price": 150,  "desc": "Открывает случайную букву"},
    "shield":           {"name": "🛡 Защита от пропуска",  "price": 250,  "desc": "Спасает от сектора ПРОПУСК"},
    "bankrupt_shield":  {"name": "💎 Защита от банкрота",  "price": 400,  "desc": "Спасает от сектора БАНКРОТ — очки не сгорят!"},
    "replace":          {"name": "🔄 Замена слова",        "price": 450,  "desc": "Заменяет слово без штрафа"},
}

ACHIEVEMENTS = {
    "first_word":   {"name": "🎯 Первое слово",      "desc": "Угадай первое слово"},
    "streak_3":     {"name": "🔥 Три дня",           "desc": "3 дня подряд в игре"},
    "streak_7":     {"name": "⚡ Неделя",            "desc": "7 дней подряд в игре"},
    "words_10":     {"name": "📖 Читатель",          "desc": "Угадай 10 слов"},
    "words_50":     {"name": "📚 Книжный червь",     "desc": "Угадай 50 слов"},
    "words_100":    {"name": "🏆 Словарь",           "desc": "Угадай 100 слов"},
    "score_1000":   {"name": "💰 Тысячник",          "desc": "Набери 1000+ очков за игру"},
    "score_5000":   {"name": "💎 Богач",             "desc": "Набери 5000+ очков за игру"},
    "rich":         {"name": "🏦 Банкир",            "desc": "Накопи 10000 монет"},
    "thief":        {"name": "🦊 Лисица",            "desc": "Укради очки у соперника"},
    "double_win":   {"name": "✌️ Двойная ставка",   "desc": "Выиграй двойной раунд"},
    "perfect_word": {"name": "✨ Перфекционист",     "desc": "Угадай слово без ошибок"},
    "gift_sent":    {"name": "🎁 Щедрая душа",       "desc": "Подари предмет другу"},
    "duel_win":     {"name": "⚔️ Дуэлянт",          "desc": "Победи в дуэльном режиме"},
}

def get_rank_for_xp(xp: int) -> dict:
    current = RANKS[0]
    for rank in RANKS:
        if xp >= rank["xp_needed"]:
            current = rank
        else:
            break
    return current

def get_next_rank(xp: int) -> Optional[dict]:
    for rank in RANKS:
        if rank["xp_needed"] > xp:
            return rank
    return None

def xp_for_score(score: int) -> int:
    return score // 10

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id       INTEGER PRIMARY KEY,
            username      TEXT,
            xp            INTEGER DEFAULT 0,
            level         INTEGER DEFAULT 1,
            total_score   INTEGER DEFAULT 0,
            games_played  INTEGER DEFAULT 0,
            words_guessed INTEGER DEFAULT 0,
            free_hints    INTEGER DEFAULT 1,
            skip_skips    INTEGER DEFAULT 0,
            word_replaces    INTEGER DEFAULT 0,
            bankrupt_shields INTEGER DEFAULT 0,
            titles           TEXT DEFAULT '[]',
            active_title     TEXT DEFAULT '',
            coins            INTEGER DEFAULT 0,
            streak           INTEGER DEFAULT 0,
            last_visit       INTEGER DEFAULT 0,
            achievements     TEXT DEFAULT '[]'
        )
    """)
    for col, typ, defval in [
        ("word_replaces",    "INTEGER", "0"),
        ("bankrupt_shields", "INTEGER", "0"),
        ("coins",            "INTEGER", "0"),
        ("streak",           "INTEGER", "0"),
        ("last_visit",       "INTEGER", "0"),
        ("achievements",     "TEXT",    "'[]'"),
    ]:
        try:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} {typ} DEFAULT {defval}")
            conn.commit()
        except Exception:
            pass
    conn.commit()
    conn.close()

def _row_to_user(row) -> dict:
    cols = ["user_id","username","xp","level","total_score","games_played",
            "words_guessed","free_hints","skip_skips","word_replaces",
            "bankrupt_shields","titles","active_title","coins","streak","last_visit","achievements"]
    row = list(row) + [None] * (len(cols) - len(row))
    d = dict(zip(cols, row))
    d["titles"]       = json.loads(d["titles"] or "[]")
    d["achievements"] = json.loads(d["achievements"] or "[]")
    d["coins"]        = d["coins"] or 0
    d["streak"]       = d["streak"] or 0
    d["last_visit"]   = d["last_visit"] or 0
    d["word_replaces"]    = d["word_replaces"] or 0
    d["bankrupt_shields"] = d["bankrupt_shields"] or 0
    return d

def get_user(user_id: int) -> Optional[dict]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return _row_to_user(row) if row else None

def ensure_user(user_id: int, username: str) -> dict:
    u = get_user(user_id)
    if u:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("UPDATE users SET username=? WHERE user_id=?", (username, user_id))
        conn.commit(); conn.close()
        u["username"] = username
        return u
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO users (user_id, username) VALUES (?,?)", (user_id, username))
    conn.commit(); conn.close()
    return get_user(user_id)

def daily_checkin(user_id: int) -> dict:
    u = get_user(user_id)
    if not u:
        return {}
    now   = int(time.time())
    today = now // 86400
    last  = (u["last_visit"] or 0) // 86400
    diff  = today - last
    if diff == 0:
        return {"streak": u["streak"], "bonus_coins": 0, "is_new": False}
    new_streak   = (u["streak"] + 1) if diff == 1 else 1
    daily_coins  = 20 + min((new_streak - 1) * 5, 80)
    streak_bonus = 0
    streak_msg   = ""
    for days, reward in STREAK_REWARDS.items():
        if new_streak == days:
            streak_bonus = reward["coins"]
            streak_msg   = reward["msg"]
    total = daily_coins + streak_bonus
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE users SET streak=?, last_visit=?, coins=coins+? WHERE user_id=?",
                 (new_streak, now, total, user_id))
    conn.commit(); conn.close()
    return {"streak": new_streak, "bonus_coins": total, "daily_coins": daily_coins,
            "streak_bonus": streak_bonus, "streak_msg": streak_msg, "is_new": True}

def grant_achievement(user_id: int, key: str) -> bool:
    u = get_user(user_id)
    if not u or key in u["achievements"]:
        return False
    new_list = u["achievements"] + [key]
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE users SET achievements=? WHERE user_id=?",
                 (json.dumps(new_list, ensure_ascii=False), user_id))
    conn.commit(); conn.close()
    return True

def add_coins(user_id: int, amount: int) -> bool:
    if not get_user(user_id) or amount <= 0: return False
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE users SET coins=coins+? WHERE user_id=?", (amount, user_id))
    conn.commit(); conn.close(); return True

def spend_coins(user_id: int, amount: int) -> bool:
    u = get_user(user_id)
    if not u or u["coins"] < amount: return False
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE users SET coins=coins-? WHERE user_id=?", (amount, user_id))
    conn.commit(); conn.close(); return True

def steal_coins_from(victim_id: int, amount: int) -> int:
    u = get_user(victim_id)
    if not u: return 0
    stolen = min(amount, u["coins"])
    if stolen <= 0: return 0
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE users SET coins=coins-? WHERE user_id=?", (stolen, victim_id))
    conn.commit(); conn.close()
    return stolen

def add_score_and_xp(user_id: int, score: int, words: int = 0) -> dict:
    u = get_user(user_id)
    if not u: return {}
    gained_xp  = xp_for_score(score)
    old_level  = u["level"]
    new_xp     = u["xp"] + gained_xp
    new_rank   = get_rank_for_xp(new_xp)
    new_level  = new_rank["level"]
    leveled_up = new_level > old_level
    rewards = {}
    for lvl in range(old_level + 1, new_level + 1):
        r = LEVEL_UP_REWARDS.get(lvl, {})
        rewards["hints"]         = rewards.get("hints", 0)         + r.get("hints", 0)
        rewards["skip_skips"]    = rewards.get("skip_skips", 0)    + r.get("skip_skips", 0)
        rewards["word_replaces"] = rewards.get("word_replaces", 0) + r.get("word_replaces", 0)
        if "title" in r:
            rewards.setdefault("titles", []).append(r["title"])
    new_hints    = u["free_hints"]    + rewards.get("hints", 0)
    new_skips    = u["skip_skips"]    + rewards.get("skip_skips", 0)
    new_replaces = u["word_replaces"] + rewards.get("word_replaces", 0)
    new_titles   = u["titles"] + rewards.get("titles", [])
    earned_coins = score // 10
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        UPDATE users SET
            xp=?, level=?, total_score=total_score+?,
            games_played=games_played+1, words_guessed=words_guessed+?,
            free_hints=?, skip_skips=?, word_replaces=?,
            titles=?, coins=coins+?
        WHERE user_id=?
    """, (new_xp, new_level, score, words, new_hints, new_skips, new_replaces,
          json.dumps(new_titles, ensure_ascii=False), earned_coins, user_id))
    conn.commit(); conn.close()
    return {"gained_xp": gained_xp, "leveled_up": leveled_up,
            "old_level": old_level, "new_level": new_level,
            "new_rank_name": new_rank["name"], "rewards": rewards,
            "earned_coins": earned_coins}

def use_free_hint(user_id: int) -> bool:
    u = get_user(user_id)
    if not u or u["free_hints"] <= 0: return False
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE users SET free_hints=free_hints-1 WHERE user_id=?", (user_id,))
    conn.commit(); conn.close(); return True

def add_free_hints(user_id: int, amount: int = 1) -> bool:
    if amount <= 0 or not get_user(user_id): return False
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE users SET free_hints=free_hints+? WHERE user_id=?", (amount, user_id))
    conn.commit(); conn.close(); return True

def use_skip_skip(user_id: int) -> bool:
    u = get_user(user_id)
    if not u or u["skip_skips"] <= 0: return False
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE users SET skip_skips=skip_skips-1 WHERE user_id=?", (user_id,))
    conn.commit(); conn.close(); return True

def add_skip_skips(user_id: int, amount: int = 1) -> bool:
    if amount <= 0 or not get_user(user_id): return False
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE users SET skip_skips=skip_skips+? WHERE user_id=?", (amount, user_id))
    conn.commit(); conn.close(); return True

def use_word_replace(user_id: int) -> bool:
    u = get_user(user_id)
    if not u or u.get("word_replaces", 0) <= 0: return False
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE users SET word_replaces=word_replaces-1 WHERE user_id=?", (user_id,))
    conn.commit(); conn.close(); return True

def use_bankrupt_shield(user_id: int) -> bool:
    u = get_user(user_id)
    if not u or u.get("bankrupt_shields", 0) <= 0: return False
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE users SET bankrupt_shields=bankrupt_shields-1 WHERE user_id=?", (user_id,))
    conn.commit(); conn.close(); return True

def add_bankrupt_shields(user_id: int, amount: int = 1) -> bool:
    if amount <= 0 or not get_user(user_id): return False
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE users SET bankrupt_shields=bankrupt_shields+? WHERE user_id=?", (amount, user_id))
    conn.commit(); conn.close(); return True

def add_word_replaces(user_id: int, amount: int = 1) -> bool:
    if amount <= 0 or not get_user(user_id): return False
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE users SET word_replaces=word_replaces+? WHERE user_id=?", (amount, user_id))
    conn.commit(); conn.close(); return True

def set_active_title(user_id: int, title: str) -> bool:
    u = get_user(user_id)
    if not u or title not in u["titles"]: return False
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE users SET active_title=? WHERE user_id=?", (title, user_id))
    conn.commit(); conn.close(); return True

def get_leaderboard_xp(limit: int = 10, offset: int = 0) -> list:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id,username,xp,level,total_score FROM users ORDER BY xp DESC,total_score DESC LIMIT ? OFFSET ?", (limit, offset))
    rows = c.fetchall(); conn.close()
    return [{"user_id":r[0],"username":r[1],"xp":r[2],"level":r[3],"total_score":r[4]} for r in rows]

def get_leaderboard_score(limit: int = 10, offset: int = 0) -> list:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id,username,xp,level,total_score FROM users ORDER BY total_score DESC,xp DESC LIMIT ? OFFSET ?", (limit, offset))
    rows = c.fetchall(); conn.close()
    return [{"user_id":r[0],"username":r[1],"xp":r[2],"level":r[3],"total_score":r[4]} for r in rows]

def get_users_count() -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    n = c.fetchone()[0]; conn.close(); return int(n or 0)

def get_user_position_xp(user_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT xp FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if not row: conn.close(); return 0
    c.execute("SELECT COUNT(*)+1 FROM users WHERE xp>?", (row[0],))
    pos = c.fetchone()[0]; conn.close(); return int(pos or 0)

def get_user_position_score(user_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT total_score FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if not row: conn.close(); return 0
    c.execute("SELECT COUNT(*)+1 FROM users WHERE total_score>?", (row[0],))
    pos = c.fetchone()[0]; conn.close(); return int(pos or 0)
