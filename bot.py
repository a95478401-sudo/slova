"""
Бот для игры в слова и города.
Работает в личных сообщениях и группах.
Без рекламы.
"""

import json
import logging
import os
import sqlite3
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Токен бота
BOT_TOKEN = os.getenv("BOT_TOKEN", "8453043608:AAElu3C3DdE1uJzHkDENZIy0LKn_am1amcA")

# Пути к файлам
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORDS_FILE = os.path.join(BASE_DIR, "words.json")
CITIES_FILE = os.path.join(BASE_DIR, "cities.json")
DB_FILE = os.path.join(BASE_DIR, "game_data.db")

# Игровые режимы
MODE_WORDS = "words"
MODE_CITIES = "cities"

# ------------------------------------------------------------------ Словари --

def load_dictionary(path: str) -> set[str]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return {w.lower().strip() for w in data if w.strip()}
    except FileNotFoundError:
        logger.warning("Словарь не найден: %s", path)
        return set()


WORDS_DICT: set[str] = load_dictionary(WORDS_FILE)
CITIES_DICT: set[str] = load_dictionary(CITIES_FILE)
logger.info("Загружено слов: %d, городов: %d", len(WORDS_DICT), len(CITIES_DICT))

# ------------------------------------------------------------------ БД ------

def init_db() -> None:
    with sqlite3.connect(DB_FILE) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                mode TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                last_word TEXT
            );

            CREATE TABLE IF NOT EXISTS moves (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER NOT NULL REFERENCES games(id),
                user_id INTEGER NOT NULL,
                username TEXT,
                word TEXT NOT NULL,
                ts TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS top (
                user_id INTEGER NOT NULL,
                username TEXT,
                chat_id INTEGER NOT NULL,
                mode TEXT NOT NULL,
                words_count INTEGER DEFAULT 0,
                games_count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, chat_id, mode)
            );
        """)


def get_active_game(chat_id: int) -> dict | None:
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute(
            "SELECT id, mode, last_word FROM games WHERE chat_id=? AND ended_at IS NULL",
            (chat_id,),
        ).fetchone()
    if row:
        return {"id": row[0], "mode": row[1], "last_word": row[2]}
    return None


def start_game(chat_id: int, mode: str) -> int:
    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.execute(
            "INSERT INTO games (chat_id, mode, started_at, last_word) VALUES (?,?,?,?)",
            (chat_id, mode, datetime.utcnow().isoformat(), None),
        )
        return cur.lastrowid


def end_game(game_id: int) -> None:
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            "UPDATE games SET ended_at=? WHERE id=?",
            (datetime.utcnow().isoformat(), game_id),
        )


def add_move(game_id: int, user_id: int, username: str, word: str) -> None:
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            "INSERT INTO moves (game_id, user_id, username, word, ts) VALUES (?,?,?,?,?)",
            (game_id, user_id, username, word, datetime.utcnow().isoformat()),
        )
        conn.execute(
            """
            INSERT INTO top (user_id, username, chat_id, mode, words_count, games_count)
            VALUES (?,?,?,?,1,0)
            ON CONFLICT(user_id, chat_id, mode)
            DO UPDATE SET words_count=words_count+1, username=excluded.username
            """,
            (user_id, username, 0, "global"),  # 0 - глобальный чат
        )
        conn.execute(
            """
            INSERT INTO top (user_id, username, chat_id, mode, words_count, games_count)
            VALUES (?,?,?,?,1,0)
            ON CONFLICT(user_id, chat_id, mode)
            DO UPDATE SET words_count=words_count+1, username=excluded.username
            """,
            (user_id, username, _get_chat_from_game(conn, game_id), "chat"),
        )
        conn.execute(
            "UPDATE games SET last_word=? WHERE id=?",
            (word, game_id),
        )


def _get_chat_from_game(conn: sqlite3.Connection, game_id: int) -> int:
    row = conn.execute("SELECT chat_id FROM games WHERE id=?", (game_id,)).fetchone()
    return row[0] if row else 0


def get_game_moves(game_id: int) -> list[dict]:
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute(
            "SELECT username, word, ts FROM moves WHERE game_id=? ORDER BY id",
            (game_id,),
        ).fetchall()
    return [{"username": r[0], "word": r[1], "ts": r[2]} for r in rows]


def get_used_words(game_id: int) -> set[str]:
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute(
            "SELECT word FROM moves WHERE game_id=?", (game_id,)
        ).fetchall()
    return {r[0].lower() for r in rows}


def get_top_global(mode: str, limit: int = 10) -> list[dict]:
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute(
            """
            SELECT username, SUM(words_count) as total
            FROM top
            WHERE mode='global'
            GROUP BY user_id
            ORDER BY total DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [{"username": r[0], "count": r[1]} for r in rows]


def get_top_chat(chat_id: int, mode: str, limit: int = 10) -> list[dict]:
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute(
            """
            SELECT username, words_count
            FROM top
            WHERE chat_id=? AND mode='chat'
            ORDER BY words_count DESC
            LIMIT ?
            """,
            (chat_id, limit),
        ).fetchall()
    return [{"username": r[0], "count": r[1]} for r in rows]


# --------------------------------------------------------------- Игровая логика --

def get_first_letter(word: str) -> str:
    """Возвращает первую букву слова (нижний регистр)."""
    return word[0].lower() if word else ""


def get_expected_letter(last_word: str) -> str:
    """Следующее слово должно начинаться с последней буквы предыдущего.
    Буквы Ъ и Ь - перепрыгиваем к предпоследней."""
    skip = {"ъ", "ь"}
    for ch in reversed(last_word.lower()):
        if ch not in skip:
            return ch
    return last_word[-1].lower()


def validate_word(word: str, mode: str, last_word: str | None, used: set[str]) -> str | None:
    """Проверяет слово. Возвращает текст ошибки или None если всё OK."""
    w = word.lower().strip()

    if not w:
        return "Пустое слово."

    if not all(c.isalpha() or c == "-" for c in w):
        return "Слово должно состоять из букв."

    if len(w) < 2:
        return "Слово слишком короткое."

    if w in used:
        return f'Слово "{w}" уже использовалось в этой игре.'

    dictionary = CITIES_DICT if mode == MODE_CITIES else WORDS_DICT
    if dictionary and w not in dictionary:
        kind = "город" if mode == MODE_CITIES else "слово"
        return f'Такое {kind} не найдено в словаре.'

    if last_word:
        expected = get_expected_letter(last_word)
        if get_first_letter(w) != expected:
            return (
                f'Слово должно начинаться на букву "{expected.upper()}" '
                f'(последняя буква слова "{last_word}").'
            )

    return None


# ----------------------------------------------------------------- Хелперы ---

def user_name(update: Update) -> str:
    u = update.effective_user
    if u.username:
        return "@" + u.username
    return u.full_name or "Игрок"


def mode_label(mode: str) -> str:
    return "Города" if mode == MODE_CITIES else "Слова"


# ---------------------------------------------------------------- Хендлеры ---

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Привет! Я бот для игры в слова и города.\n\n"
        "Команды:\n"
        "/play - начать игру в слова\n"
        "/cities - начать игру в города\n"
        "/stop - остановить текущую игру\n"
        "/results - итоги текущей игры\n"
        "/top - топ этого чата\n"
        "/gtop - глобальный топ\n"
        "/help - помощь\n\n"
        "Правило простое: каждое следующее слово начинается с последней буквы предыдущего."
    )
    await update.message.reply_text(text)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Как играть:\n\n"
        "1. Запусти игру командой /play (слова) или /cities (города).\n"
        "2. Бот назовёт первое слово - ты называешь следующее, начинающееся на последнюю букву.\n"
        "3. Нельзя повторять уже сказанные слова.\n"
        "4. Буквы Ъ и Ь в конце слова пропускаются.\n"
        "5. /stop - завершить игру и посмотреть итоги.\n\n"
        "Работает в личных сообщениях и группах."
    )
    await update.message.reply_text(text)


async def _start_game_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE, mode: str
) -> None:
    chat_id = update.effective_chat.id
    existing = get_active_game(chat_id)
    if existing:
        await update.message.reply_text(
            f"В этом чате уже идёт игра ({mode_label(existing['mode'])}).\n"
            "Используй /stop чтобы её завершить."
        )
        return

    game_id = start_game(chat_id, mode)

    # Выбираем стартовое слово
    if mode == MODE_CITIES:
        start_words = [c.lower() for c in CITIES_DICT if len(c) >= 4]
        start_word = "москва" if "москва" in start_words else (start_words[0] if start_words else "москва")
    else:
        start_words = [w for w in WORDS_DICT if len(w) >= 4]
        start_word = "яблоко" if "яблоко" in start_words else (start_words[0] if start_words else "яблоко")

    add_move(game_id, 0, "Бот", start_word)

    expected = get_expected_letter(start_word)
    label = mode_label(mode)
    await update.message.reply_text(
        f"Игра начата - режим: {label}\n\n"
        f"Первое слово: {start_word.capitalize()}\n"
        f"Твоя очередь - слово на букву {expected.upper()}"
    )


async def cmd_play(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _start_game_handler(update, context, MODE_WORDS)


async def cmd_cities(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _start_game_handler(update, context, MODE_CITIES)


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    game = get_active_game(chat_id)
    if not game:
        await update.message.reply_text("Сейчас нет активной игры. Начни новую: /play или /cities")
        return

    moves = get_game_moves(game["id"])
    end_game(game["id"])

    total = max(0, len(moves) - 1)  # первый ход бота не считаем
    text = (
        f"Игра завершена!\n"
        f"Режим: {mode_label(game['mode'])}\n"
        f"Всего слов сыграно: {total}\n"
    )

    if moves:
        text += f"Последнее слово: {moves[-1]['word'].capitalize()}"

    await update.message.reply_text(text)


async def cmd_results(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    game = get_active_game(chat_id)
    if not game:
        await update.message.reply_text("Нет активной игры.")
        return

    moves = get_game_moves(game["id"])
    if not moves:
        await update.message.reply_text("Ещё ни одного хода.")
        return

    # Считаем очки участников (не считаем ход бота)
    scores: dict[str, int] = {}
    for m in moves[1:]:
        name = m["username"] or "Неизвестный"
        scores[name] = scores.get(name, 0) + 1

    if not scores:
        await update.message.reply_text("Ещё никто не сделал хода.")
        return

    lines = [f"Итоги игры ({mode_label(game['mode'])}):\n"]
    for i, (name, cnt) in enumerate(
        sorted(scores.items(), key=lambda x: -x[1]), start=1
    ):
        lines.append(f"{i}. {name} - {cnt} слов")

    lines.append(f"\nВсего ходов: {len(moves) - 1}")
    lines.append(f"Текущее слово: {moves[-1]['word'].capitalize()}")

    await update.message.reply_text("\n".join(lines))


async def cmd_top(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    rows = get_top_chat(chat_id, "chat")
    if not rows:
        await update.message.reply_text("В этом чате пока нет статистики.")
        return
    lines = ["Топ этого чата:\n"]
    for i, r in enumerate(rows, start=1):
        lines.append(f"{i}. {r['username']} - {r['count']} слов")
    await update.message.reply_text("\n".join(lines))


async def cmd_gtop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rows = get_top_global("global")
    if not rows:
        await update.message.reply_text("Глобальная статистика пуста.")
        return
    lines = ["Глобальный топ:\n"]
    for i, r in enumerate(rows, start=1):
        lines.append(f"{i}. {r['username']} - {r['count']} слов")
    await update.message.reply_text("\n".join(lines))


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    game = get_active_game(chat_id)
    if not game:
        return  # нет игры - молчим

    text = update.message.text.strip()

    # Игнорируем команды
    if text.startswith("/"):
        return

    word = text.lower().strip()
    used = get_used_words(game["id"])

    error = validate_word(word, game["mode"], game["last_word"], used)
    if error:
        await update.message.reply_text(f"Ошибка: {error}")
        return

    name = user_name(update)
    add_move(game["id"], update.effective_user.id, name, word)

    expected = get_expected_letter(word)
    await update.message.reply_text(
        f"{word.capitalize()} - принято!\n"
        f"Следующее слово на букву {expected.upper()}"
    )


# --------------------------------------------------------------- Запуск -----

def main() -> None:
    init_db()

    token = BOT_TOKEN
    if token == "ВАШ_ТОКЕН_ЗДЕСЬ":
        logger.error("Укажи токен бота в переменной окружения BOT_TOKEN или в файле bot.py")
        return

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("play", cmd_play))
    app.add_handler(CommandHandler("cities", cmd_cities))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("results", cmd_results))
    app.add_handler(CommandHandler("top", cmd_top))
    app.add_handler(CommandHandler("gtop", cmd_gtop))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
