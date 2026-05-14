#!/usr/bin/env python3
import asyncio
import logging
import random
import os
import time
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton, BotCommand,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from words import WORDS_BY_CATEGORY, ALL_CATEGORIES
from game_logic import (
    GameRoom, SinglePlayerGame, DuelGame,
    WHEEL_SECTORS, DIFFICULTY_SETTINGS,
    spin_wheel, format_word_display, ALPHABET,
)
from db import (
    init_db, ensure_user, get_user, add_score_and_xp,
    use_free_hint, add_free_hints, use_skip_skip, add_skip_skips,
    use_word_replace, add_word_replaces,
    use_bankrupt_shield, add_bankrupt_shields,
    set_active_title, daily_checkin, grant_achievement,
    add_coins, spend_coins, steal_coins_from,
    get_leaderboard_xp, get_leaderboard_score, get_users_count,
    get_user_position_xp, get_user_position_score,
    get_rank_for_xp, get_next_rank,
    RANKS, SHOP_ITEMS, ACHIEVEMENTS, STREAK_REWARDS,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "8622943091:AAEa19llqG6GVYyh11TzH5lWWoPOYaUG2IU")

# ---------------------------------------------------------------------------
# FSM States
# ---------------------------------------------------------------------------
class CreateRoom(StatesGroup):
    waiting_rounds = State(); waiting_players = State()
    waiting_difficulty = State(); waiting_category = State()

class CreateGroupRoom(StatesGroup):
    waiting_rounds = State(); waiting_players = State()
    waiting_difficulty = State(); waiting_category = State()

class JoinRoom(StatesGroup):
    waiting_room_id = State()

class SinglePlay(StatesGroup):
    choosing_rounds = State(); choosing_difficulty = State()
    choosing_category = State(); playing = State()

class ProfileState(StatesGroup):
    choosing_title = State()

class GiftState(StatesGroup):
    choosing_item = State(); entering_user = State()

class DuelState(StatesGroup):
    waiting_opponent = State(); playing = State()

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
rooms:        dict[str, GameRoom]         = {}
single_games: dict[int, SinglePlayerGame] = {}
last_single_settings: dict[int, tuple]   = {}
group_rooms:  dict[int, str]             = {}
duels:        dict[str, DuelGame]        = {}  # duel_id -> DuelGame
pending_duels: dict[int, str]            = {}  # challenger_uid -> duel_id
matchmaking_pool: list[int]              = []  # uids waiting for random match
user_duel:    dict[int, str]             = {}  # uid -> duel_id

TURN_TIMEOUT_SEC = 45
turn_timer_tasks: dict[str, asyncio.Task] = {}
duel_timer_tasks: dict[str, asyncio.Task] = {}

# Short category IDs for callback_data (Telegram limit: 64 bytes)
CATEGORY_ID_TO_NAME = {str(i): cat for i, cat in enumerate(ALL_CATEGORIES)}
CATEGORY_NAME_TO_ID = {cat: cid for cid, cat in CATEGORY_ID_TO_NAME.items()}

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp  = Dispatcher(storage=MemoryStorage())

# ===========================================================================
# KEYBOARDS
# ===========================================================================

def kb_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Одиночная игра",   callback_data="single_play"),
         InlineKeyboardButton(text="⚔️ Дуэль",            callback_data="duel_menu")],
        [InlineKeyboardButton(text="👥 Мультиплеер (ЛС)", callback_data="multi_play"),
         InlineKeyboardButton(text="🔍 Поиск игры",       callback_data="matchmaking")],
        [InlineKeyboardButton(text="👤 Профиль",          callback_data="profile"),
         InlineKeyboardButton(text="🎒 Инвентарь",        callback_data="inventory")],
        [InlineKeyboardButton(text="🏪 Магазин",          callback_data="shop"),
         InlineKeyboardButton(text="🏆 Достижения",       callback_data="achievements")],
        [InlineKeyboardButton(text="📊 Рейтинг",          callback_data="leaderboard"),
         InlineKeyboardButton(text="🎁 Подарить",         callback_data="gift_start")],
        [InlineKeyboardButton(text="📖 Правила",          callback_data="rules")],
    ])

def kb_group_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎡 Создать игру",   callback_data="group_create_room")],
        [InlineKeyboardButton(text="📊 Рейтинг",        callback_data="leaderboard")],
    ])

def kb_single_rounds() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=str(i), callback_data=f"srounds_{i}") for i in range(1, 6)],
        [InlineKeyboardButton(text=str(i), callback_data=f"srounds_{i}") for i in range(6, 11)],
        [InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu")],
    ])

def kb_difficulty(prefix: str = "diff") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 Лёгкий  (3-5 букв)",  callback_data=f"{prefix}_easy")],
        [InlineKeyboardButton(text="🟡 Средний (6-8 букв)",  callback_data=f"{prefix}_medium")],
        [InlineKeyboardButton(text="🔴 Сложный (9+ букв)",   callback_data=f"{prefix}_hard")],
        [InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu")],
    ])

def kb_categories(prefix: str = "cat") -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for cat in ALL_CATEGORIES:
        cat_id = CATEGORY_NAME_TO_ID.get(cat)
        if cat_id is None:
            continue
        row.append(InlineKeyboardButton(text=cat, callback_data=f"{prefix}_{cat_id}"))
        if len(row) == 2:
            buttons.append(row); row = []
    if row: buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🎲 Случайная", callback_data=f"{prefix}_random")])
    buttons.append([InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_rounds(prefix: str = "rounds") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=str(i), callback_data=f"{prefix}_{i}") for i in range(1, 4)],
        [InlineKeyboardButton(text=str(i), callback_data=f"{prefix}_{i}") for i in range(4, 6)],
        [InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu")],
    ])

def kb_multi_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать комнату",      callback_data="create_room")],
        [InlineKeyboardButton(text="🚪 Войти по коду",        callback_data="join_room")],
        [InlineKeyboardButton(text="🔍 Поиск рандомной игры", callback_data="matchmaking")],
        [InlineKeyboardButton(text="🏠 Меню",                 callback_data="main_menu")],
    ])

def kb_back_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
    ])

def kb_rematch(room_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Играть ещё", callback_data=f"rematch_{room_id}")],
        [InlineKeyboardButton(text="🏠 Меню",        callback_data="main_menu")],
    ])

def kb_single_rematch() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Играть ещё", callback_data="single_rematch")],
        [InlineKeyboardButton(text="🏠 Меню",        callback_data="main_menu")],
    ])

def kb_spin(room: GameRoom, uid: int) -> InlineKeyboardMarkup:
    u = get_user(uid)
    rows = [[InlineKeyboardButton(text="🎡 Крутить барабан!", callback_data="spin_wheel")]]
    rows.append([InlineKeyboardButton(text="🔤 Назвать слово целиком", callback_data="guess_word_multi")])
    if u and u["free_hints"] > 0:
        rows.append([InlineKeyboardButton(
            text=f"💡 Подсказка ({u['free_hints']} шт)", callback_data="use_free_hint_multi")])
    if u and u.get("word_replaces", 0) > 0:
        rows.append([InlineKeyboardButton(
            text=f"🔄 Замена слова ({u['word_replaces']} шт)",
            callback_data=f"word_replace_multi_{room.room_id}")])
    rows.append([InlineKeyboardButton(text="🏳️ Сдаться", callback_data=f"surrender_{room.room_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_group_active(room_id: str, uid: int = 0) -> InlineKeyboardMarkup:
    rows = []
    if uid:
        u = get_user(uid)
        if u and u.get("word_replaces", 0) > 0:
            rows.append([InlineKeyboardButton(
                text=f"🔄 Замена слова ({u['word_replaces']} шт)",
                callback_data=f"word_replace_group_{room_id}")])
    rows.append([InlineKeyboardButton(text="🏳️ Сдаться", callback_data=f"surrender_{room_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_group_lobby(room_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Войти в игру",    callback_data=f"gjoin_{room_id}")],
        [InlineKeyboardButton(text="▶️ Начать досрочно", callback_data=f"gstart_{room_id}")],
        [InlineKeyboardButton(text="❌ Отменить",         callback_data=f"gcancel_{room_id}")],
    ])

def kb_host_ls(room_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Начать досрочно", callback_data=f"gstart_{room_id}")],
        [InlineKeyboardButton(text="❌ Отменить",         callback_data=f"gcancel_ls_{room_id}")],
    ])

def kb_player_ls(room_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚪 Покинуть игру", callback_data=f"gleave_{room_id}")],
    ])

def kb_host_room(room_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Начать досрочно",  callback_data=f"start_game_{room_id}")],
        [InlineKeyboardButton(text="❌ Удалить комнату",   callback_data=f"delete_room_{room_id}")],
        [InlineKeyboardButton(text="🚪 Выйти",             callback_data=f"leave_room_{room_id}")],
    ])

def kb_player_room(room_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚪 Выйти", callback_data=f"leave_room_{room_id}")],
    ])

def kb_single_alphabet(used: set, show_free_hint: bool = False, show_replace: bool = False) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for letter in ALPHABET:
        if letter in used:
            row.append(InlineKeyboardButton(text="·", callback_data="used_letter"))
        else:
            row.append(InlineKeyboardButton(text=letter, callback_data=f"sletter_{letter}"))
        if len(row) == 6:
            buttons.append(row); row = []
    if row: buttons.append(row)
    extra = []
    if show_free_hint:
        extra.append(InlineKeyboardButton(text="💡 Бесплатная подсказка!", callback_data="sfree_hint"))
    extra.append(InlineKeyboardButton(text="💡 Подсказка (-50 очков)", callback_data="shint"))
    buttons.append(extra)
    buttons.append([InlineKeyboardButton(text="🔤 Назвать слово целиком", callback_data="sguess_word")])
    if show_replace:
        buttons.append([InlineKeyboardButton(text="🔄 Заменить слово", callback_data="sword_replace")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_duel_alphabet(used: set) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for letter in ALPHABET:
        if letter in used:
            row.append(InlineKeyboardButton(text="·", callback_data="duel_used"))
        else:
            row.append(InlineKeyboardButton(text=letter, callback_data=f"dletter_{letter}"))
        if len(row) == 6:
            buttons.append(row); row = []
    if row: buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🔤 Назвать слово целиком", callback_data="duel_guess_word")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ===========================================================================
# HELPERS
# ===========================================================================

def mention(user_id: int, name: str) -> str:
    return f'<a href="tg://user?id={user_id}">{name}</a>'

async def notify_all_in_room(room: GameRoom, text: str, reply_markup=None):
    for uid in room.player_ids:
        try:
            await bot.send_message(uid, text, reply_markup=reply_markup)
        except Exception as e:
            logger.warning(f"notify_all error {uid}: {e}")

def build_round_status(room: GameRoom) -> str:
    display = format_word_display(room.current_word, room.guessed_letters)
    cfg_label = DIFFICULTY_SETTINGS[room.difficulty]["label"]
    double_tag = "  🔥x2" if room.double_round else ""
    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"🎯 <b>Раунд {room.current_round}/{room.total_rounds}</b>  {cfg_label}{double_tag}",
        f"📚 Категория: <b>{room.current_category}</b>",
        f"💬 Подсказка: <i>{room.current_hint}</i>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"🔤 <code>{display}</code>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"📝 Буквы: {' '.join(sorted(room.guessed_letters)) or '—'}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "", "💰 <b>Счёт:</b>",
    ]
    for uid in room.player_ids:
        name    = room.player_names[uid]
        score   = room.scores[uid]
        r_score = room.round_scores[uid]
        marker  = "👑" if uid == room.current_player_id else "  "
        lines.append(f"{marker} {name}: <b>{score}</b>  (+{r_score} раунд)")
    return "\n".join(lines)

def build_single_status(game: SinglePlayerGame) -> str:
    display   = format_word_display(game.word, game.guessed_letters)
    lives_str = "❤️" * game.lives + "🖤" * (game.max_lives - game.lives)
    cfg_label = DIFFICULTY_SETTINGS[game.difficulty]["label"]
    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"🎯 <b>Слово {game.word_index}/{game.total_words}</b>  {cfg_label}",
        f"📚 Категория: <b>{game.category}</b>",
        f"💬 Подсказка: <i>{game.hint}</i>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"🔤 <code>{display}</code>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"❤️ Жизни: {lives_str}",
        f"💰 Очки: <b>{game.score}</b>  🎡 <b>{game.spin_points} за букву</b>",
        f"📝 Буквы: {' '.join(sorted(game.guessed_letters)) or '—'}",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]
    return "\n".join(lines)

def build_duel_status(duel: DuelGame, uid: int) -> str:
    guessed = duel.p1_guessed if uid == duel.p1_id else duel.p2_guessed
    opp_guessed = duel.p2_guessed if uid == duel.p1_id else duel.p1_guessed
    opp_name = duel.p2_name if uid == duel.p1_id else duel.p1_name
    display  = format_word_display(duel.word, guessed)
    opp_disp = format_word_display(duel.word, opp_guessed)
    elapsed  = int(time.time() - duel.started_at)
    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"⚔️ <b>ДУЭЛЬ</b>  {DIFFICULTY_SETTINGS[duel.difficulty]['label']}",
        f"📚 {duel.category}  💬 <i>{duel.hint}</i>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"👤 Ты:    <code>{display}</code>",
        f"👻 {opp_name}: <code>{opp_disp}</code>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"⏱ Время: {elapsed}с",
    ]
    return "\n".join(lines)

def _find_room_by_player(uid: int) -> Optional[GameRoom]:
    for room in rooms.values():
        if uid in room.player_ids and room.active:
            return room
    return None

def _find_any_room_by_player(uid: int) -> Optional[GameRoom]:
    for room in rooms.values():
        if uid in room.player_ids:
            return room
    return None

# ===========================================================================
# TURN TIMER
# ===========================================================================

def _cancel_turn_timer(room_id: str):
    task = turn_timer_tasks.pop(room_id, None)
    if task and not task.done():
        task.cancel()

def restart_turn_timer(room: GameRoom):
    _cancel_turn_timer(room.room_id)
    room.turn_timer_token += 1
    token = room.turn_timer_token
    uid   = room.current_player_id
    turn_timer_tasks[room.room_id] = asyncio.create_task(
        player_turn_timer(room.room_id, uid, token))

async def player_turn_timer(room_id: str, player_id: int, token: int):
    await asyncio.sleep(TURN_TIMEOUT_SEC)
    room = rooms.get(room_id)
    if not room or not room.active: return
    if room.current_player_id != player_id or room.turn_timer_token != token: return
    name = room.player_names[player_id]
    room.next_player()
    next_name = room.player_names[room.current_player_id]
    msg = f"⏰ <b>Время вышло!</b> {name} пропускает ход.\n👉 Ходит: <b>{next_name}</b>"
    if room.room_type == "group":
        try: await bot.send_message(room.group_chat_id, msg)
        except Exception: pass
    else:
        await notify_all_in_room(room, msg)
    await send_turn_message(room)

async def send_turn_message(room: GameRoom):
    status       = build_round_status(room)
    current_uid  = room.current_player_id
    current_name = room.player_names[current_uid]
    room.last_activity = time.time()
    if room.room_type == "group":
        try:
            sent = await bot.send_message(
                room.group_chat_id,
                status + f"\n\n👉 Ход: <b>{mention(current_uid, current_name)}</b>\n"
                         f"⏰ {TURN_TIMEOUT_SEC} секунд. Напишите букву в чат!",
                reply_markup=kb_group_active(room.room_id, current_uid),
            )
            room.group_message_id = sent.message_id
        except Exception as e:
            logger.warning(f"send_turn_message group error: {e}")
        u = get_user(current_uid)
        if u and u["free_hints"] > 0:
            try:
                await bot.send_message(current_uid,
                    f"💡 Твой ход в группе! У тебя <b>{u['free_hints']}</b> подсказок.\n"
                    f"Напиши /hint_{room.room_id} в группе.")
            except Exception: pass
    else:
        for uid in room.player_ids:
            try:
                if uid == current_uid:
                    await bot.send_message(uid,
                        status + f"\n\n🎡 <b>Ваш ход!</b> Крутите барабан!\n⏰ {TURN_TIMEOUT_SEC} секунд.",
                        reply_markup=kb_spin(room, uid))
                else:
                    await bot.send_message(uid, status + f"\n\n⏳ Ходит <b>{current_name}</b>...")
            except Exception as e:
                logger.warning(f"send_turn_message private error {uid}: {e}")
    restart_turn_timer(room)

# AFK timer
AFK_TIMEOUT = 3600
AFK_CHECK_INTERVAL = 600

async def afk_game_timer(room_id: str):
    while True:
        await asyncio.sleep(AFK_CHECK_INTERVAL)
        room = rooms.get(room_id)
        if not room or not room.active: return
        if time.time() - room.last_activity >= AFK_TIMEOUT:
            msg = "⏰ <b>Игра завершена из-за бездействия (1 час).</b>"
            if room.room_type == "group":
                try: await bot.send_message(room.group_chat_id, msg)
                except Exception: pass
            else:
                await notify_all_in_room(room, msg)
            room.active = False
            return

# ===========================================================================
# DAILY CHECKIN & ACHIEVEMENTS HELPER
# ===========================================================================

async def do_checkin(uid: int, message_or_call):
    info = daily_checkin(uid)
    if not info.get("is_new"):
        return
    streak = info["streak"]
    coins  = info["bonus_coins"]
    msg    = f"📅 <b>Ежедневный бонус!</b>\n🔥 Серия: <b>{streak} дней</b>\n💰 +<b>{coins}</b> монет"
    if info.get("streak_msg"):
        msg += f"\n\n{info['streak_msg']}"
    try:
        if hasattr(message_or_call, "answer"):
            await message_or_call.answer(msg)
        else:
            await bot.send_message(uid, msg)
    except Exception: pass
    # Достижения серий
    if streak >= 3:  grant_achievement(uid, "streak_3")
    if streak >= 7:  grant_achievement(uid, "streak_7")
    # Проверка монет
    u = get_user(uid)
    if u and u["coins"] >= 10000: grant_achievement(uid, "rich")

async def check_achievements(uid: int, score: int = 0, words_total: int = 0,
                              perfect: bool = False):
    u = get_user(uid)
    if not u: return
    new_ones = []
    if u["words_guessed"] >= 1 and grant_achievement(uid, "first_word"):
        new_ones.append("first_word")
    if u["words_guessed"] >= 10 and grant_achievement(uid, "words_10"):
        new_ones.append("words_10")
    if u["words_guessed"] >= 50 and grant_achievement(uid, "words_50"):
        new_ones.append("words_50")
    if u["words_guessed"] >= 100 and grant_achievement(uid, "words_100"):
        new_ones.append("words_100")
    if score >= 1000 and grant_achievement(uid, "score_1000"):
        new_ones.append("score_1000")
    if score >= 5000 and grant_achievement(uid, "score_5000"):
        new_ones.append("score_5000")
    if perfect and grant_achievement(uid, "perfect_word"):
        new_ones.append("perfect_word")
    if u["coins"] >= 10000 and grant_achievement(uid, "rich"):
        new_ones.append("rich")
    for key in new_ones:
        ach = ACHIEVEMENTS.get(key, {})
        try:
            await bot.send_message(uid, f"🏅 <b>Достижение получено!</b>\n{ach.get('name','')}\n<i>{ach.get('desc','')}</i>")
        except Exception: pass

# ===========================================================================
# /start /menu /single /multi
# ===========================================================================

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    uid   = message.from_user.id
    uname = message.from_user.full_name
    ensure_user(uid, uname)
    await do_checkin(uid, message)
    if message.chat.type in ("group", "supergroup"):
        await message.answer(
            "🎡 <b>Поле Чудес</b> — готов к игре!\n\n"
            "🎮 /single — одиночная игра (в ЛС)\n"
            "👥 /multi — мультиплеер в этой группе",
            reply_markup=kb_group_menu())
        return
    u    = get_user(uid)
    rank = get_rank_for_xp(u["xp"])
    await message.answer(
        f"🎡 <b>Поле Чудес!</b>\n\n"
        f"Привет, <b>{uname}</b>! {rank['name']}\n\n"
        f"Угадывай слова, зарабатывай монеты, бейся с друзьями!\n\n"
        f"Выбери режим:",
        reply_markup=kb_main_menu())

@dp.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    await state.clear()
    if message.chat.type in ("group", "supergroup"):
        await message.answer("🎡 <b>Поле Чудес</b>", reply_markup=kb_group_menu())
    else:
        await message.answer("🏠 <b>Главное меню</b>", reply_markup=kb_main_menu())

@dp.message(Command("single"))
async def cmd_single(message: Message, state: FSMContext):
    uid = message.from_user.id
    ensure_user(uid, message.from_user.full_name)
    if message.chat.type in ("group", "supergroup"):
        me = await bot.get_me()
        await message.answer(
            f"🎮 Одиночная игра запускается в ЛС!\n"
            f"👉 <a href='https://t.me/{me.username}?start=single'>Перейти в ЛС</a>")
        return
    await state.set_state(SinglePlay.choosing_rounds)
    await message.answer("🎮 <b>Одиночная игра</b>\n\nСколько слов?", reply_markup=kb_single_rounds())

@dp.message(Command("multi"))
async def cmd_multi(message: Message, state: FSMContext):
    uid = message.from_user.id
    ensure_user(uid, message.from_user.full_name)
    if message.chat.type in ("group", "supergroup"):
        await state.set_state(CreateGroupRoom.waiting_rounds)
        await message.answer("🎯 <b>Создание игры в группе</b>\n\nСколько раундов?",
                             reply_markup=kb_rounds("grrooms"))
        return
    await state.clear()
    await message.answer("👥 <b>Мультиплеер (ЛС)</b>", reply_markup=kb_multi_menu())

@dp.message(F.text.regexp(r'^/hint_([A-Z0-9]{6})$'))
async def cmd_hint_group(message: Message):
    if message.chat.type not in ("group", "supergroup"): return
    room_id = message.text.split("_")[1]
    room = rooms.get(room_id)
    if not room or not room.active: return
    uid = message.from_user.id
    if room.current_player_id != uid:
        await message.reply("⚠️ Сейчас не твой ход!"); return
    u = get_user(uid)
    if not u or u["free_hints"] <= 0:
        await message.reply("❌ У тебя нет бесплатных подсказок."); return
    hidden = [c for c in set(room.current_word) if c.isalpha() and c not in room.guessed_letters]
    if not hidden: await message.reply("Все буквы открыты!"); return
    letter = random.choice(hidden)
    room.guessed_letters.add(letter)
    use_free_hint(uid)
    await message.reply(f"💡 Буква <b>«{letter}»</b> открыта!")
    if room.is_round_complete(): await finish_round(room)
    else:
        try: await bot.send_message(room.group_chat_id, build_round_status(room))
        except Exception: pass

# ===========================================================================
# ПРОФИЛЬ
# ===========================================================================

@dp.callback_query(F.data == "profile")
async def cb_profile(call: CallbackQuery):
    uid = call.from_user.id
    u   = get_user(uid)
    if not u: await call.answer("Профиль не найден.", show_alert=True); return
    rank      = get_rank_for_xp(u["xp"])
    next_rank = get_next_rank(u["xp"])
    progress  = ""
    if next_rank:
        need = next_rank["xp_needed"] - rank["xp_needed"]
        have = u["xp"] - rank["xp_needed"]
        pct  = min(int(have / need * 10), 10)
        bar  = "█" * pct + "░" * (10 - pct)
        progress = f"\n📈 [{bar}] {have}/{need} XP"
    title_line = f"\n🏷 Титул: <b>{u['active_title']}</b>" if u.get("active_title") else ""
    streak_line = f"\n🔥 Серия входов: <b>{u['streak']} дней</b>" if u.get("streak") else ""
    ach_count = len(u.get("achievements", []))
    text = (
        f"👤 <b>Профиль</b>\n\n"
        f"Имя: <b>{u['username']}</b>{title_line}\n"
        f"Уровень: <b>{rank['level']}</b> — {rank['name']}\n"
        f"XP: <b>{u['xp']}</b>{progress}\n"
        f"💰 Монеты: <b>{u['coins']}</b>{streak_line}\n\n"
        f"🎮 Игр: <b>{u['games_played']}</b>  🔤 Слов: <b>{u['words_guessed']}</b>\n"
        f"📊 Очков всего: <b>{u['total_score']}</b>  🏅 Достижений: <b>{ach_count}</b>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏷 Сменить титул",  callback_data="change_title")],
        [InlineKeyboardButton(text="🏅 Достижения",     callback_data="achievements")],
        [InlineKeyboardButton(text="🏠 Меню",           callback_data="main_menu")],
    ])
    await call.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data == "change_title")
async def cb_change_title(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    u   = get_user(uid)
    if not u or not u["titles"]:
        await call.answer("У тебя пока нет титулов! Повышай уровень.", show_alert=True); return
    buttons = [[InlineKeyboardButton(text=t, callback_data=f"settitle_{t}")] for t in u["titles"]]
    buttons.append([InlineKeyboardButton(text="🚫 Убрать титул", callback_data="settitle_none")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад",        callback_data="profile")])
    await state.set_state(ProfileState.choosing_title)
    await call.message.edit_text("🏷 <b>Выбери активный титул:</b>",
                                 reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("settitle_"), ProfileState.choosing_title)
async def cb_set_title(call: CallbackQuery, state: FSMContext):
    await state.clear()
    uid   = call.from_user.id
    title = call.data[9:]
    if title == "none":
        import sqlite3 as _sq
        conn = _sq.connect(__import__("db").DB_PATH)
        conn.execute("UPDATE users SET active_title='' WHERE user_id=?", (uid,))
        conn.commit(); conn.close()
        await call.answer("Титул убран.")
    else:
        set_active_title(uid, title)
        await call.answer(f"Титул «{title}» активирован!")
    await cb_profile(call)

# ===========================================================================
# ИНВЕНТАРЬ
# ===========================================================================

@dp.callback_query(F.data == "inventory")
async def cb_inventory(call: CallbackQuery):
    uid = call.from_user.id
    u   = get_user(uid)
    if not u: await call.answer("Профиль не найден.", show_alert=True); return
    text = (
        f"🎒 <b>Инвентарь</b>\n\n"
        f"💡 Бесплатные подсказки: <b>{u['free_hints']}</b>\n"
        f"   └ Открывает случайную букву без штрафа\n\n"
        f"🛡 Защита от ПРОПУСКА: <b>{u['skip_skips']}</b>\n"
        f"   └ Автоматически спасает от сектора ПРОПУСК\n\n"
        f"💎 Защита от БАНКРОТА: <b>{u.get('bankrupt_shields', 0)}</b>\n"
        f"   └ Автоматически спасает от сектора БАНКРОТ\n\n"
        f"🔄 Замена слова: <b>{u.get('word_replaces', 0)}</b>\n"
        f"   └ Заменяет текущее слово на новое\n\n"
        f"💰 Монеты: <b>{u['coins']}</b>\n"
        f"   └ Трать в магазине на предметы\n\n"
        f"🏷 Титулы: {len(u['titles'])} шт.\n"
        f"   └ {', '.join(u['titles']) if u['titles'] else 'пока нет'}\n\n"
        f"<i>Монеты = очки из игр. Предметы — за уровни или в магазине!</i>"
    )
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏪 Магазин", callback_data="shop")],
        [InlineKeyboardButton(text="🎁 Подарить предмет", callback_data="gift_start")],
        [InlineKeyboardButton(text="🏠 Меню",    callback_data="main_menu")],
    ]))

# ===========================================================================
# МАГАЗИН
# ===========================================================================

@dp.callback_query(F.data == "shop")
async def cb_shop(call: CallbackQuery):
    uid = call.from_user.id
    u   = get_user(uid)
    coins = u["coins"] if u else 0
    text = f"🏪 <b>Магазин</b>\n💰 У тебя: <b>{coins}</b> монет\n\n"
    for key, item in SHOP_ITEMS.items():
        text += f"{item['name']} — <b>{item['price']}</b> монет\n   └ {item['desc']}\n\n"
    buttons = [[InlineKeyboardButton(
        text=f"{item['name']} ({item['price']} 💰)",
        callback_data=f"buy_{key}")] for key, item in SHOP_ITEMS.items()]
    buttons.append([InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu")])
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("buy_"))
async def cb_buy(call: CallbackQuery):
    uid  = call.from_user.id
    key  = call.data[4:]
    item = SHOP_ITEMS.get(key)
    if not item: await call.answer("Неизвестный товар.", show_alert=True); return
    if not spend_coins(uid, item["price"]):
        await call.answer(f"❌ Недостаточно монет! Нужно {item['price']}.", show_alert=True); return
    if key == "hint":            add_free_hints(uid, 1)
    elif key == "shield":          add_skip_skips(uid, 1)
    elif key == "bankrupt_shield": add_bankrupt_shields(uid, 1)
    elif key == "replace":         add_word_replaces(uid, 1)
    u = get_user(uid)
    await call.answer(f"✅ {item['name']} куплен! Осталось монет: {u['coins']}", show_alert=True)
    await cb_shop(call)

# ===========================================================================
# ДОСТИЖЕНИЯ
# ===========================================================================

@dp.callback_query(F.data == "achievements")
async def cb_achievements(call: CallbackQuery):
    uid = call.from_user.id
    u   = get_user(uid)
    if not u: await call.answer("Профиль не найден.", show_alert=True); return
    owned = u.get("achievements", [])
    lines = ["🏅 <b>Достижения</b>\n"]
    for key, ach in ACHIEVEMENTS.items():
        mark = "✅" if key in owned else "🔒"
        lines.append(f"{mark} {ach['name']}\n   └ <i>{ach['desc']}</i>")
    await call.message.edit_text("\n".join(lines), reply_markup=kb_back_menu())

# ===========================================================================
# ПОДАРОК ПРЕДМЕТА
# ===========================================================================

@dp.callback_query(F.data == "gift_start")
async def cb_gift_start(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    u   = get_user(uid)
    if not u: return
    buttons = []
    if u["free_hints"] > 0:
        buttons.append([InlineKeyboardButton(text=f"💡 Подсказка (у тебя: {u['free_hints']})", callback_data="gift_item_hint")])
    if u["skip_skips"] > 0:
        buttons.append([InlineKeyboardButton(text=f"🛡 Защита (у тебя: {u['skip_skips']})", callback_data="gift_item_shield")])
    if u.get("bankrupt_shields", 0) > 0:
        buttons.append([InlineKeyboardButton(text=f"💎 Защита от банкрота (у тебя: {u['bankrupt_shields']})", callback_data="gift_item_bankrupt_shield")])
    if u.get("word_replaces", 0) > 0:
        buttons.append([InlineKeyboardButton(text=f"🔄 Замена слова (у тебя: {u['word_replaces']})", callback_data="gift_item_replace")])
    if not buttons:
        await call.answer("У тебя нет предметов для подарка!", show_alert=True); return
    buttons.append([InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu")])
    await state.set_state(GiftState.choosing_item)
    await call.message.edit_text("🎁 <b>Что подарить?</b>",
                                 reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("gift_item_"), GiftState.choosing_item)
async def cb_gift_choose_item(call: CallbackQuery, state: FSMContext):
    item = call.data[10:]
    await state.update_data(gift_item=item)
    await state.set_state(GiftState.entering_user)
    await call.message.edit_text(
        "🎁 Напиши юзернейм получателя (без @) или его Telegram ID:", reply_markup=kb_back_menu())

@dp.message(GiftState.entering_user)
async def msg_gift_user(message: Message, state: FSMContext):
    data = await state.get_data()
    item = data.get("gift_item")
    sender_uid = message.from_user.id
    text = message.text.strip().lstrip("@")
    # Search by username
    import sqlite3 as _sq
    from db import DB_PATH as _dbp
    conn = _sq.connect(_dbp)
    c = conn.cursor()
    if text.isdigit():
        c.execute("SELECT user_id, username FROM users WHERE user_id=?", (int(text),))
    else:
        c.execute("SELECT user_id, username FROM users WHERE LOWER(username)=LOWER(?)", (text,))
    row = c.fetchone(); conn.close()
    if not row:
        await message.answer("❌ Пользователь не найден. Убедись что он зарегистрирован в боте."); return
    target_uid, target_name = row
    if target_uid == sender_uid:
        await message.answer("❌ Нельзя подарить самому себе!"); return
    sender_u = get_user(sender_uid)
    item_map = {"hint": ("💡 Подсказку", use_free_hint, add_free_hints, "free_hints"),
                "shield": ("🛡 Защиту от пропуска", use_skip_skip, add_skip_skips, "skip_skips"),
                "bankrupt_shield": ("💎 Защиту от банкрота", use_bankrupt_shield, add_bankrupt_shields, "bankrupt_shields"),
                "replace": ("🔄 Замену слова", use_word_replace, add_word_replaces, "word_replaces")}
    if item not in item_map:
        await state.clear(); return
    item_name, use_fn, add_fn, field = item_map[item]
    if not sender_u or sender_u.get(field, 0) <= 0:
        await message.answer("❌ У тебя нет этого предмета!")
        await state.clear(); return
    use_fn(sender_uid)
    add_fn(target_uid, 1)
    await state.clear()
    await message.answer(f"✅ Ты подарил <b>{item_name}</b> игроку <b>{target_name}</b>! 🎁")
    try:
        await bot.send_message(target_uid,
            f"🎁 <b>{message.from_user.full_name}</b> подарил тебе {item_name}!")
    except Exception: pass
    grant_achievement(sender_uid, "gift_sent")
    ach = ACHIEVEMENTS.get("gift_sent", {})
    u = get_user(sender_uid)
    if ach and u and len(u.get("achievements",[])) == 1 and "gift_sent" in u["achievements"]:
        await message.answer(f"🏅 Достижение: {ach['name']}\n<i>{ach['desc']}</i>")

# ===========================================================================
# РЕЙТИНГ
# ===========================================================================

LEADERBOARD_PAGE_SIZE = 20

@dp.callback_query(F.data == "leaderboard")
async def cb_leaderboard(call: CallbackQuery):
    await call.message.edit_text("📊 <b>Рейтинг</b>\n\nВыбери:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏆 Топ XP",    callback_data="lb_xp10"),
         InlineKeyboardButton(text="💰 Топ очки",  callback_data="lb_score10")],
        [InlineKeyboardButton(text="🌍 XP глобально",    callback_data="lb_xp_page_1"),
         InlineKeyboardButton(text="🌍 Очки глобально",  callback_data="lb_score_page_1")],
        [InlineKeyboardButton(text="🏠 Меню",      callback_data="main_menu")],
    ]))

async def _show_lb(call: CallbackQuery, metric: str, limit: int, offset: int, page: Optional[int] = None):
    uid = call.from_user.id
    if metric == "xp":
        rows = get_leaderboard_xp(limit=limit, offset=offset)
        pos  = get_user_position_xp(uid)
        title = "XP"
    else:
        rows = get_leaderboard_score(limit=limit, offset=offset)
        pos  = get_user_position_score(uid)
        title = "очкам"
    lines = [f"📊 <b>{'Топ-10' if page is None else f'Глобальный рейтинг'} по {title}</b>\n"]
    if page is not None:
        total = get_users_count()
        total_pages = max(1, (total + LEADERBOARD_PAGE_SIZE - 1) // LEADERBOARD_PAGE_SIZE)
        lines[0] += f" Стр. <b>{page}/{total_pages}</b>\n"
    medals = ["🥇","🥈","🥉"]
    for i, p in enumerate(rows):
        mark = " 👈" if p["user_id"] == uid else ""
        prefix = medals[i] if page is None and i < 3 else f"{offset+i+1}."
        if metric == "xp":
            rank = get_rank_for_xp(p["xp"])
            lines.append(f"{prefix} {p['username']} — <b>{p['xp']}</b> XP  {rank['name']}{mark}")
        else:
            lines.append(f"{prefix} {p['username']} — <b>{p['total_score']}</b> очков{mark}")
    if pos: lines.append(f"\n👤 Твоё место: <b>#{pos}</b>")
    if page is None:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="↩️ Назад", callback_data="leaderboard")]])
    else:
        total = get_users_count()
        total_pages = max(1, (total + LEADERBOARD_PAGE_SIZE - 1) // LEADERBOARD_PAGE_SIZE)
        nav = []
        if page > 1: nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"lb_{metric}_page_{page-1}"))
        if page < total_pages: nav.append(InlineKeyboardButton(text="➡️", callback_data=f"lb_{metric}_page_{page+1}"))
        rows_kb = []
        if nav: rows_kb.append(nav)
        rows_kb.append([InlineKeyboardButton(text="↩️ Назад", callback_data="leaderboard")])
        kb = InlineKeyboardMarkup(inline_keyboard=rows_kb)
    await call.message.edit_text("\n".join(lines), reply_markup=kb)

@dp.callback_query(F.data == "lb_xp10")
async def cb_lb_xp10(call: CallbackQuery): await _show_lb(call, "xp", 10, 0)
@dp.callback_query(F.data == "lb_score10")
async def cb_lb_score10(call: CallbackQuery): await _show_lb(call, "score", 10, 0)
@dp.callback_query(F.data.startswith("lb_xp_page_"))
async def cb_lb_xp_page(call: CallbackQuery):
    try: page = int(call.data.split("_")[-1])
    except Exception: page = 1
    await _show_lb(call, "xp", LEADERBOARD_PAGE_SIZE, (page-1)*LEADERBOARD_PAGE_SIZE, page)
@dp.callback_query(F.data.startswith("lb_score_page_"))
async def cb_lb_score_page(call: CallbackQuery):
    try: page = int(call.data.split("_")[-1])
    except Exception: page = 1
    await _show_lb(call, "score", LEADERBOARD_PAGE_SIZE, (page-1)*LEADERBOARD_PAGE_SIZE, page)

# ===========================================================================
# ГЛАВНОЕ МЕНЮ (callback)
# ===========================================================================

@dp.callback_query(F.data == "main_menu")
async def cb_main_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    if call.message.chat.type in ("group", "supergroup"):
        await call.message.edit_text("🎡 <b>Поле Чудес</b>", reply_markup=kb_group_menu())
    else:
        await call.message.edit_text("🎡 <b>Поле Чудес</b> — Главное меню", reply_markup=kb_main_menu())

@dp.callback_query(F.data == "rules")
async def cb_rules(call: CallbackQuery):
    text = (
        "📖 <b>Правила Поля Чудес</b>\n\n"
        "🎯 Угадывай слова по буквам и зарабатывай монеты!\n\n"
        "<b>🎮 Режимы:</b>\n"
        "• Одиночная — угадывай слова сам, каждое слово = рандомные очки за букву\n"
        "• Мультиплеер — крути барабан, называй буквы, соревнуйся с друзьями\n"
        "• ⚔️ Дуэль — 1 на 1, одно слово, кто быстрее угадает\n"
        "• 🔍 Поиск игры — автоматический подбор соперника\n\n"
        "<b>🎡 Барабан (мультиплеер):</b>\n"
        "• Очки (50-700) — за угаданные буквы\n"
        "• ⭐ ПРИЗ — удвоение очков раунда\n"
        "• 🔥 ДВОЙНОЙ — следующий раунд за двойные очки!\n"
        "• 🦊 ВОРОВСТВО — кража монет у соперника\n"
        "• 🎁 БОНУС — +200 очков\n"
        "• 🛡 ЩИТ — +1 защита\n"
        "• 🎰 ДЖЕКПОТ — +500 за завершение\n"
        "• 💀 БАНКРОТ — теряешь очки раунда (💎 Защита от банкрота спасёт!)\n"
        "• ⏩ ПРОПУСК — пропускаешь ход\n\n"
        "<b>💰 Монеты = очки из игр</b>\n"
        "Трать в 🏪 Магазине на подсказки, защиты и замены слов!\n\n"
        "<b>🏅 Достижения</b> — выполняй задания и получай значки!\n"
        "<b>🔥 Серии входов</b> — заходи каждый день за монеты!\n"
        f"<b>⏰ {TURN_TIMEOUT_SEC} секунд</b> на ход!\n\n"
        "📈 100 очков = 10 XP. Повышай уровень — получай предметы!"
    )
    await call.message.edit_text(text, reply_markup=kb_back_menu())

# ===========================================================================
# ОДИНОЧНАЯ ИГРА
# ===========================================================================

@dp.callback_query(F.data == "single_play")
async def cb_single_play(call: CallbackQuery, state: FSMContext):
    await state.set_state(SinglePlay.choosing_rounds)
    await call.message.edit_text("🎮 <b>Одиночная игра</b>\n\nСколько слов?", reply_markup=kb_single_rounds())

@dp.callback_query(F.data.startswith("srounds_"))
async def cb_s_rounds(call: CallbackQuery, state: FSMContext):
    rounds = int(call.data.split("_")[1])
    await state.update_data(single_rounds=rounds)
    await state.set_state(SinglePlay.choosing_difficulty)
    await call.message.edit_text(f"✅ Слов: <b>{rounds}</b>\n\nВыбери сложность:", reply_markup=kb_difficulty("sdiff"))

@dp.callback_query(F.data.startswith("sdiff_"))
async def cb_s_difficulty(call: CallbackQuery, state: FSMContext):
    diff = call.data[6:]
    await state.update_data(difficulty=diff)
    await state.set_state(SinglePlay.choosing_category)
    await call.message.edit_text(
        f"Сложность: <b>{DIFFICULTY_SETTINGS[diff]['label']}</b>\n\nВыбери категорию:",
        reply_markup=kb_categories("scat"))

@dp.callback_query(F.data.startswith("scat_"))
async def cb_s_category(call: CallbackQuery, state: FSMContext):
    cat_raw    = call.data[5:]
    data       = await state.get_data()
    difficulty = data.get("difficulty", "medium")
    if cat_raw == "random":
        category = random.choice(ALL_CATEGORIES)
    else:
        category = CATEGORY_ID_TO_NAME.get(cat_raw, cat_raw)
    total_words = data.get("single_rounds", 5)
    uid   = call.from_user.id
    uname = call.from_user.full_name
    ensure_user(uid, uname)
    game = SinglePlayerGame(uid, difficulty, category)
    game.total_words = total_words
    if not game.load_words():
        await call.message.edit_text("❌ Нет слов для этого выбора.", reply_markup=kb_back_menu()); return
    single_games[uid] = game
    last_single_settings[uid] = (difficulty, category, total_words)
    await state.set_state(SinglePlay.playing)
    u = get_user(uid)
    has_free = u and u["free_hints"] > 0
    has_replace = u and u.get("word_replaces", 0) > 0
    status = build_single_status(game)
    await call.message.edit_text(
        f"🚀 <b>Игра началась!</b>\n\n{status}\n\nНажми букву:",
        reply_markup=kb_single_alphabet(game.guessed_letters, has_free, has_replace))

@dp.callback_query(F.data.startswith("sletter_"), SinglePlay.playing)
async def cb_s_letter(call: CallbackQuery, state: FSMContext):
    uid  = call.from_user.id
    game = single_games.get(uid)
    if not game: await call.answer("Игра не найдена. /start", show_alert=True); return
    letter = call.data[8:]
    if letter in game.guessed_letters: await call.answer("Уже называл!"); return
    count = game.guess_letter(letter)
    if count > 0:
        await call.answer(f"✅ «{letter}» — {count} раз(а)! +{count * game.spin_points} очков")
    else:
        await call.answer(f"❌ «{letter}» — нет такой буквы")
    await _s_update(call, game, state)

@dp.callback_query(F.data == "shint", SinglePlay.playing)
async def cb_s_hint(call: CallbackQuery, state: FSMContext):
    uid  = call.from_user.id
    game = single_games.get(uid)
    if not game: await call.answer("Игра не найдена.", show_alert=True); return
    if game.score < 50: await call.answer("❌ Нужно 50 очков!", show_alert=True); return
    letter = game.use_hint(free=False)
    if not letter: await call.answer("Все буквы открыты!", show_alert=True); return
    await call.answer(f"💡 «{letter}» (-50 очков)")
    await _s_update(call, game, state)

@dp.callback_query(F.data == "sfree_hint", SinglePlay.playing)
async def cb_s_free_hint(call: CallbackQuery, state: FSMContext):
    uid  = call.from_user.id
    game = single_games.get(uid)
    if not game: await call.answer("Игра не найдена.", show_alert=True); return
    u = get_user(uid)
    if not u or u["free_hints"] <= 0: await call.answer("❌ Бесплатных подсказок нет!", show_alert=True); return
    letter = game.use_hint(free=True)
    if not letter: await call.answer("Все буквы открыты!", show_alert=True); return
    use_free_hint(uid)
    await call.answer(f"💡 «{letter}» (без штрафа!)", show_alert=True)
    await _s_update(call, game, state)

@dp.callback_query(F.data == "sword_replace", SinglePlay.playing)
async def cb_s_word_replace(call: CallbackQuery, state: FSMContext):
    uid  = call.from_user.id
    game = single_games.get(uid)
    if not game: await call.answer("Игра не найдена.", show_alert=True); return
    if not use_word_replace(uid): await call.answer("❌ Замен слова нет!", show_alert=True); return
    if not game.next_word(replace=True):
        await call.answer("Нет слов для замены.", show_alert=True)
        add_word_replaces(uid, 1); return
    await call.answer("🔄 Слово заменено!", show_alert=True)
    u = get_user(uid)
    status = build_single_status(game)
    await call.message.edit_text(
        f"🔄 <b>Слово заменено!</b>\n\n{status}\n\nНажми букву:",
        reply_markup=kb_single_alphabet(game.guessed_letters,
                                        u and u["free_hints"] > 0,
                                        u and u.get("word_replaces", 0) > 0))

@dp.callback_query(F.data == "sguess_word", SinglePlay.playing)
async def cb_s_guess_word_prompt(call: CallbackQuery):
    await call.answer()
    await call.message.answer("🔤 Напиши слово целиком:")

@dp.message(SinglePlay.playing)
async def msg_s_guess_word(message: Message, state: FSMContext):
    uid  = message.from_user.id
    game = single_games.get(uid)
    if not game: return
    guess = message.text.strip().upper()
    if guess == game.word:
        game.score += 100; game.word_guessed = True
        await message.answer("🎉 <b>Верно! +100 очков!</b>")
        await _s_next_or_finish(message, game, state)
    else:
        game.lives -= 1
        if game.lives <= 0:
            await message.answer(f"💀 Слово было: <b>{game.word}</b>")
            await _s_next_or_finish(message, game, state)
        else:
            u = get_user(uid)
            await message.answer(
                f"❌ Неверно!\n\n{build_single_status(game)}",
                reply_markup=kb_single_alphabet(game.guessed_letters,
                                                u and u["free_hints"] > 0,
                                                u and u.get("word_replaces", 0) > 0))

async def _s_update(call: CallbackQuery, game: SinglePlayerGame, state: FSMContext):
    if game.is_word_complete():
        game.score += 50; game.word_guessed = True
        await call.message.edit_text(f"🎊 <b>Слово угадано! +50 бонус</b>\nСлово: <b>{game.word}</b>")
        await _s_next_or_finish(call.message, game, state)
        return
    if game.lives <= 0:
        await call.message.edit_text(f"💀 <b>Жизни кончились!</b>\nСлово: <b>{game.word}</b>")
        await _s_next_or_finish(call.message, game, state)
        return
    uid = game.user_id; u = get_user(uid)
    await call.message.edit_text(
        build_single_status(game) + "\n\nНажми букву:",
        reply_markup=kb_single_alphabet(game.guessed_letters,
                                        u and u["free_hints"] > 0,
                                        u and u.get("word_replaces", 0) > 0))

async def _s_next_or_finish(message: Message, game: SinglePlayerGame, state: FSMContext):
    await asyncio.sleep(2)
    if game.word_guessed:
        game.words_guessed += 1
    perfect = game.word_guessed and game.errors_this_word == 0
    if game.next_word():
        uid = game.user_id; u = get_user(uid)
        await message.answer(
            f"➡️ <b>Следующее слово!</b>\n\n{build_single_status(game)}\n\nНажми букву:",
            reply_markup=kb_single_alphabet(game.guessed_letters,
                                            u and u["free_hints"] > 0,
                                            u and u.get("word_replaces", 0) > 0))
    else:
        uid = game.user_id
        single_games.pop(uid, None)
        await state.clear()
        result = add_score_and_xp(uid, game.score, game.words_guessed)
        await check_achievements(uid, game.score, game.words_guessed, perfect)
        stars = "⭐" * min(game.score // 100, 5)
        reward_text = ""
        if result.get("leveled_up"):
            rewards = result.get("rewards", {})
            reward_text = (f"\n\n🎉 <b>НОВЫЙ УРОВЕНЬ {result['new_level']}!</b>\n"
                           f"{result['new_rank_name']}\n")
            if rewards.get("hints"):     reward_text += f"💡 +{rewards['hints']} подсказок\n"
            if rewards.get("skip_skips"): reward_text += f"🛡 +{rewards['skip_skips']} защит\n"
            if rewards.get("word_replaces"): reward_text += f"🔄 +{rewards['word_replaces']} замен слова\n"
            if rewards.get("titles"):    reward_text += f"🏷 {', '.join(rewards['titles'])}\n"
        ec = result.get("earned_coins", 0)
        await message.answer(
            f"🏁 <b>Игра окончена!</b>\n\n"
            f"🎯 Слов: {game.words_guessed}/{game.total_words}\n"
            f"💰 Счёт: <b>{game.score}</b>  +{ec} монет\n"
            f"📈 +{result.get('gained_xp', 0)} XP\n"
            f"{stars}{reward_text}",
            reply_markup=kb_single_rematch())

@dp.callback_query(F.data == "used_letter")
async def cb_used_letter(call: CallbackQuery): await call.answer("Уже названа!")

@dp.callback_query(F.data == "single_rematch")
async def cb_single_rematch(call: CallbackQuery, state: FSMContext):
    uid      = call.from_user.id
    settings = last_single_settings.get(uid)
    if not settings: await call.answer("Нет сохранённых условий.", show_alert=True); return
    diff, cat, total = settings[0], settings[1], settings[2] if len(settings) > 2 else 5
    ensure_user(uid, call.from_user.full_name)
    game = SinglePlayerGame(uid, diff, cat)
    game.total_words = total
    if not game.load_words(): await call.message.edit_text("❌ Не удалось загрузить слова.", reply_markup=kb_back_menu()); return
    single_games[uid] = game
    await state.set_state(SinglePlay.playing)
    u = get_user(uid)
    await call.message.edit_text(
        f"🚀 <b>Игра началась!</b>\n\n{build_single_status(game)}\n\nНажми букву:",
        reply_markup=kb_single_alphabet(game.guessed_letters,
                                        u and u["free_hints"] > 0,
                                        u and u.get("word_replaces", 0) > 0))

# ===========================================================================
# ДУЭЛЬ
# ===========================================================================

@dp.callback_query(F.data == "duel_menu")
async def cb_duel_menu(call: CallbackQuery):
    uid = call.from_user.id
    # Если уже в дуэли
    duel_id = user_duel.get(uid)
    if duel_id and duels.get(duel_id) and duels[duel_id].active:
        await call.answer("Ты уже в дуэли!", show_alert=True); return
    await call.message.edit_text(
        "⚔️ <b>Дуэль</b>\n\nОдно слово, два игрока — кто быстрее угадает, тот победил!\n\n"
        "Выбери режим:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Найти соперника автоматически", callback_data="duel_find")],
            [InlineKeyboardButton(text="🤝 Вызвать по Telegram ID",         callback_data="duel_challenge")],
            [InlineKeyboardButton(text="🏠 Меню",                           callback_data="main_menu")],
        ]))

@dp.callback_query(F.data == "duel_find")
async def cb_duel_find(call: CallbackQuery):
    uid   = call.from_user.id
    uname = call.from_user.full_name
    ensure_user(uid, uname)
    if uid in matchmaking_pool:
        await call.answer("Ты уже ищешь соперника!", show_alert=True); return
    # Check if opponent available
    if matchmaking_pool:
        opp_uid = matchmaking_pool.pop(0)
        opp_u   = get_user(opp_uid)
        opp_name = opp_u["username"] if opp_u else "Соперник"
        await _start_duel(uid, uname, opp_uid, opp_name)
        await call.answer("Соперник найден!")
    else:
        matchmaking_pool.append(uid)
        await call.message.edit_text(
            "🔍 <b>Поиск соперника...</b>\n\nЖди, скоро найдём! Можешь отменить:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отменить поиск", callback_data="duel_cancel_search")],
            ]))
        asyncio.create_task(_duel_search_timeout(uid, call.message.chat.id))

@dp.callback_query(F.data == "duel_cancel_search")
async def cb_duel_cancel_search(call: CallbackQuery):
    uid = call.from_user.id
    if uid in matchmaking_pool:
        matchmaking_pool.remove(uid)
    await call.message.edit_text("❌ Поиск отменён.", reply_markup=kb_back_menu())

async def _duel_search_timeout(uid: int, chat_id: int):
    await asyncio.sleep(120)
    if uid in matchmaking_pool:
        matchmaking_pool.remove(uid)
        try: await bot.send_message(chat_id, "⏰ Соперник не найден. Попробуй снова позже.", reply_markup=kb_back_menu())
        except Exception: pass

@dp.callback_query(F.data == "duel_challenge")
async def cb_duel_challenge(call: CallbackQuery, state: FSMContext):
    await state.set_state(DuelState.waiting_opponent)
    await call.message.edit_text("⚔️ Напиши Telegram ID соперника:", reply_markup=kb_back_menu())

@dp.message(DuelState.waiting_opponent)
async def msg_duel_opponent(message: Message, state: FSMContext):
    uid = message.from_user.id
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ Введи числовой Telegram ID."); return
    opp_uid = int(text)
    if opp_uid == uid:
        await message.answer("❌ Нельзя вызвать самого себя!"); return
    opp_u = get_user(opp_uid)
    if not opp_u:
        await message.answer("❌ Пользователь не найден. Убедись что он зарегистрирован."); return
    opp_name = opp_u["username"]
    await state.clear()
    # Send challenge
    duel = DuelGame(uid, message.from_user.full_name, opp_uid, opp_name)
    duels[duel.duel_id] = duel
    pending_duels[uid]   = duel.duel_id
    await message.answer(f"⚔️ Вызов отправлен игроку <b>{opp_name}</b>! Ждём ответа...")
    try:
        await bot.send_message(opp_uid,
            f"⚔️ <b>{message.from_user.full_name}</b> вызывает тебя на дуэль!\n\n"
            f"📚 Категория: <b>{duel.category}</b>  {DIFFICULTY_SETTINGS[duel.difficulty]['label']}\n\n"
            f"Принять?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Принять",   callback_data=f"duel_accept_{duel.duel_id}")],
                [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"duel_decline_{duel.duel_id}")],
            ]))
    except Exception:
        await message.answer("❌ Не удалось отправить сообщение сопернику. Возможно он заблокировал бота.")
        duels.pop(duel.duel_id, None)
        pending_duels.pop(uid, None)

@dp.callback_query(F.data.startswith("duel_accept_"))
async def cb_duel_accept(call: CallbackQuery):
    duel_id = call.data[12:]
    duel    = duels.get(duel_id)
    if not duel: await call.answer("Дуэль не найдена.", show_alert=True); return
    if not duel.active: await call.answer("Дуэль уже завершена.", show_alert=True); return
    opp_uid = call.from_user.id
    if opp_uid != duel.p2_id: await call.answer("Это не твой вызов!", show_alert=True); return
    user_duel[duel.p1_id] = duel_id
    user_duel[duel.p2_id] = duel_id
    await call.message.edit_text("⚔️ Дуэль начинается!")
    await _send_duel_state(duel)
    asyncio.create_task(_duel_timeout(duel_id))

@dp.callback_query(F.data.startswith("duel_decline_"))
async def cb_duel_decline(call: CallbackQuery):
    duel_id = call.data[13:]
    duel    = duels.get(duel_id)
    if not duel: return
    duels.pop(duel_id, None)
    pending_duels.pop(duel.p1_id, None)
    await call.message.edit_text("❌ Ты отклонил вызов.")
    try: await bot.send_message(duel.p1_id, f"❌ <b>{duel.p2_name}</b> отклонил вызов на дуэль.")
    except Exception: pass

async def _start_duel(uid1: int, name1: str, uid2: int, name2: str):
    duel = DuelGame(uid1, name1, uid2, name2)
    duels[duel.duel_id] = duel
    user_duel[uid1] = duel.duel_id
    user_duel[uid2] = duel.duel_id
    await _send_duel_state(duel)
    asyncio.create_task(_duel_timeout(duel.duel_id))

async def _send_duel_state(duel: DuelGame):
    for uid in (duel.p1_id, duel.p2_id):
        guessed = duel.p1_guessed if uid == duel.p1_id else duel.p2_guessed
        try:
            await bot.send_message(uid,
                build_duel_status(duel, uid) + "\n\nНажимай буквы!",
                reply_markup=kb_duel_alphabet(guessed))
        except Exception: pass

async def _duel_timeout(duel_id: str):
    await asyncio.sleep(300)  # 5 minutes
    duel = duels.get(duel_id)
    if not duel or not duel.active: return
    duel.active = False
    for uid in (duel.p1_id, duel.p2_id):
        user_duel.pop(uid, None)
        try: await bot.send_message(uid, "⏰ Дуэль завершена по таймауту. Ничья!")
        except Exception: pass
    duels.pop(duel_id, None)

@dp.callback_query(F.data.startswith("dletter_"))
async def cb_duel_letter(call: CallbackQuery):
    uid    = call.from_user.id
    letter = call.data[8:]
    duel_id = user_duel.get(uid)
    if not duel_id: await call.answer("Дуэль не найдена.", show_alert=True); return
    duel = duels.get(duel_id)
    if not duel or not duel.active: await call.answer("Дуэль завершена.", show_alert=True); return
    guessed = duel.p1_guessed if uid == duel.p1_id else duel.p2_guessed
    if letter in guessed: await call.answer("Уже называл!"); return
    count = duel.guess_letter(uid, letter)
    if count > 0:
        await call.answer(f"✅ «{letter}» — {count} раз(а)!")
    else:
        await call.answer(f"❌ «{letter}» нет!")
    # Update board for this player
    guessed = duel.p1_guessed if uid == duel.p1_id else duel.p2_guessed
    await call.message.edit_text(
        build_duel_status(duel, uid) + "\n\nНажимай буквы!",
        reply_markup=kb_duel_alphabet(guessed))
    # Notify opponent of their board update
    opp_uid = duel.p2_id if uid == duel.p1_id else duel.p1_id
    try:
        opp_guessed = duel.p2_guessed if uid == duel.p1_id else duel.p1_guessed
        await bot.send_message(opp_uid, build_duel_status(duel, opp_uid))
    except Exception: pass
    # Check win
    if duel.is_complete(uid):
        await _duel_finish(duel, uid)

@dp.callback_query(F.data == "duel_guess_word")
async def cb_duel_guess_word_prompt(call: CallbackQuery):
    await call.answer()
    await call.message.answer("🔤 Напиши слово целиком:")

@dp.message(DuelState.playing)
async def msg_duel_word(message: Message, state: FSMContext):
    uid     = message.from_user.id
    duel_id = user_duel.get(uid)
    if not duel_id: return
    duel = duels.get(duel_id)
    if not duel or not duel.active: return
    if duel.guess_word(uid, message.text.strip()):
        await _duel_finish(duel, uid)
    else:
        await message.answer("❌ Неверно!")

async def _duel_finish(duel: DuelGame, winner_uid: int):
    duel.set_winner(winner_uid)
    loser_uid  = duel.p2_id if winner_uid == duel.p1_id else duel.p1_id
    winner_name = duel.p1_name if winner_uid == duel.p1_id else duel.p2_name
    elapsed = int(time.time() - duel.started_at)
    user_duel.pop(duel.p1_id, None)
    user_duel.pop(duel.p2_id, None)
    duels.pop(duel.duel_id, None)
    pending_duels.pop(duel.p1_id, None)
    win_msg = (f"🏆 <b>{winner_name} победил в дуэли!</b>\n\n"
               f"🔤 Слово было: <b>{duel.word}</b>\n"
               f"⏱ Время: {elapsed}с\n\n"
               f"Победитель получает +300 монет!")
    lose_msg = win_msg + "\n\nНе унывай — реванш?"
    add_coins(winner_uid, 300)
    add_score_and_xp(winner_uid, 300, 1)
    grant_achievement(winner_uid, "duel_win")
    try: await bot.send_message(winner_uid, win_msg, reply_markup=kb_back_menu())
    except Exception: pass
    try: await bot.send_message(loser_uid, lose_msg, reply_markup=kb_back_menu())
    except Exception: pass

# ===========================================================================
# MATCHMAKING (поиск рандомной комнаты)
# ===========================================================================

@dp.callback_query(F.data == "matchmaking")
async def cb_matchmaking(call: CallbackQuery):
    uid   = call.from_user.id
    uname = call.from_user.full_name
    ensure_user(uid, uname)
    # Ищем публичную комнату в ожидании
    public_room = None
    for room in rooms.values():
        if room.is_public and not room.active and not room.is_full and uid not in room.player_ids:
            public_room = room
            break
    if public_room:
        public_room.add_player(uid, uname)
        await call.message.edit_text(
            f"✅ Найдена комната! Код: <code>{public_room.room_id}</code>\n"
            f"👥 Игроков: {len(public_room.player_ids)}/{public_room.max_players or '∞'}\n\n"
            f"Хост начнёт игру когда соберётся команда.",
            reply_markup=kb_player_room(public_room.room_id))
        for existing_uid in public_room.player_ids:
            if existing_uid == uid: continue
            try:
                await bot.send_message(existing_uid,
                    f"👋 <b>{uname}</b> присоединился к игре!\n"
                    f"👥 {len(public_room.player_ids)}/{public_room.max_players or '∞'}")
            except Exception: pass
        if public_room.is_full:
            await asyncio.sleep(1)
            await start_multi_game(public_room)
    else:
        # Create new public room
        room = GameRoom(
            host_id=uid, host_name=uname,
            total_rounds=3, max_players=4,
            category=random.choice(ALL_CATEGORIES),
            difficulty="medium",
            room_type="private",
            is_public=True,
        )
        rooms[room.room_id] = room
        await call.message.edit_text(
            f"🔍 <b>Поиск игры...</b>\n\n"
            f"Комната создана! Ждём других игроков.\n"
            f"Код: <code>{room.room_id}</code>\n\n"
            f"Или поделись ссылкой с другом!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="▶️ Начать (1 игрок)", callback_data=f"start_game_{room.room_id}")],
                [InlineKeyboardButton(text="❌ Отменить",          callback_data=f"delete_room_{room.room_id}")],
            ]))
        asyncio.create_task(_public_room_deadline(room.room_id))

async def _public_room_deadline(room_id: str):
    await asyncio.sleep(180)  # 3 min
    room = rooms.get(room_id)
    if not room or room.active: return
    if len(room.player_ids) >= 1:
        await start_multi_game(room)

# ===========================================================================
# МУЛЬТИПЛЕЕР В ЛС — СОЗДАНИЕ КОМНАТЫ
# ===========================================================================

@dp.callback_query(F.data == "multi_play")
async def cb_multi_play(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("👥 <b>Мультиплеер (ЛС)</b>", reply_markup=kb_multi_menu())

@dp.callback_query(F.data == "create_room")
async def cb_create_room(call: CallbackQuery, state: FSMContext):
    await state.set_state(CreateRoom.waiting_rounds)
    await call.message.edit_text("🎯 <b>Создание комнаты</b>\n\nСколько раундов?", reply_markup=kb_rounds("mrooms"))

@dp.callback_query(F.data.startswith("mrooms_"))
async def cb_m_rounds(call: CallbackQuery, state: FSMContext):
    rounds = int(call.data.split("_")[1])
    await state.update_data(rounds=rounds)
    await state.set_state(CreateRoom.waiting_players)
    await call.message.edit_text(
        f"✅ Раундов: <b>{rounds}</b>\n\nСколько игроков?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="2", callback_data="mplayers_2"),
             InlineKeyboardButton(text="3", callback_data="mplayers_3"),
             InlineKeyboardButton(text="4", callback_data="mplayers_4")],
            [InlineKeyboardButton(text="5", callback_data="mplayers_5"),
             InlineKeyboardButton(text="6", callback_data="mplayers_6"),
             InlineKeyboardButton(text="10", callback_data="mplayers_10")],
            [InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu")],
        ]))

@dp.callback_query(F.data.startswith("mplayers_"))
async def cb_m_players_btn(call: CallbackQuery, state: FSMContext):
    await state.update_data(max_players=int(call.data.split("_")[1]))
    await state.set_state(CreateRoom.waiting_difficulty)
    await call.message.edit_text("🎯 Выбери сложность:", reply_markup=kb_difficulty("mdiff"))

@dp.message(CreateRoom.waiting_players)
async def msg_m_players(message: Message, state: FSMContext):
    try:
        n = int(message.text.strip())
        if n < 2 or n > 100: raise ValueError()
    except ValueError:
        await message.answer("❌ Введи число от 2 до 100."); return
    await state.update_data(max_players=n)
    await state.set_state(CreateRoom.waiting_difficulty)
    await message.answer("🎯 Выбери сложность:", reply_markup=kb_difficulty("mdiff"))

@dp.callback_query(F.data.startswith("mdiff_"))
async def cb_m_difficulty(call: CallbackQuery, state: FSMContext):
    diff = call.data[6:]
    await state.update_data(difficulty=diff)
    await state.set_state(CreateRoom.waiting_category)
    await call.message.edit_text(
        f"Сложность: <b>{DIFFICULTY_SETTINGS[diff]['label']}</b>\n\nВыбери категорию:",
        reply_markup=kb_categories("mcat"))

@dp.callback_query(F.data.startswith("mcat_"))
async def cb_m_category(call: CallbackQuery, state: FSMContext):
    cat_raw  = call.data[5:]
    if cat_raw == "random":
        category = random.choice(ALL_CATEGORIES)
    else:
        category = CATEGORY_ID_TO_NAME.get(cat_raw, cat_raw)
    data     = await state.get_data()
    uid      = call.from_user.id
    uname    = call.from_user.full_name
    ensure_user(uid, uname)
    rounds = data.get("rounds", 3)
    max_players = data.get("max_players", 2)
    difficulty = data.get("difficulty", "medium")
    room = GameRoom(host_id=uid, host_name=uname, total_rounds=rounds,
                    max_players=max_players, category=category,
                    difficulty=difficulty, room_type="private")
    rooms[room.room_id] = room
    await state.clear()
    await call.message.edit_text(
        f"🏠 <b>Комната создана!</b>\n\n"
        f"🔑 Код: <code>{room.room_id}</code>\n"
        f"📚 Категория: <b>{category}</b>\n"
        f"🎯 Раундов: <b>{room.total_rounds}</b>\n"
        f"👥 Игроков: 1/{room.max_players}\n"
        f"🎮 Сложность: {DIFFICULTY_SETTINGS[room.difficulty]['label']}\n\n"
        f"Поделись кодом с друзьями!",
        reply_markup=kb_host_room(room.room_id))

@dp.callback_query(F.data == "join_room")
async def cb_join_room(call: CallbackQuery, state: FSMContext):
    await state.set_state(JoinRoom.waiting_room_id)
    await call.message.edit_text("🚪 Введи код комнаты:", reply_markup=kb_back_menu())

@dp.message(JoinRoom.waiting_room_id)
async def msg_join_room(message: Message, state: FSMContext):
    room_id = message.text.strip().upper()
    room    = rooms.get(room_id)
    if not room: await message.answer("❌ Комната не найдена."); return
    if room.active: await message.answer("❌ Игра уже началась!"); return
    if room.room_type != "private": await message.answer("❌ Это групповая комната."); return
    uid   = message.from_user.id
    uname = message.from_user.full_name
    ensure_user(uid, uname)
    if uid in room.player_ids: await message.answer("⚠️ Ты уже в этой комнате!"); await state.clear(); return
    if room.is_full: await message.answer("❌ Комната заполнена!"); return
    room.add_player(uid, uname)
    await state.clear()
    players_list = "\n".join([f"{i+1}. {room.player_names[p]}" for i, p in enumerate(room.player_ids)])
    for existing_uid in room.player_ids:
        try:
            kb = kb_host_room(room.room_id) if existing_uid == room.host_id else kb_player_room(room.room_id)
            await bot.send_message(existing_uid,
                f"👋 <b>{uname}</b> вошёл!\n\n👥 {len(room.player_ids)}/{room.max_players}:\n{players_list}",
                reply_markup=kb)
        except Exception: pass
    if room.is_full:
        await asyncio.sleep(1)
        await start_multi_game(room)

@dp.callback_query(F.data.startswith("start_game_"))
async def cb_start_game(call: CallbackQuery):
    room_id = call.data[11:]
    room    = rooms.get(room_id)
    if not room: await call.answer("Комната не найдена!", show_alert=True); return
    if call.from_user.id != room.host_id: await call.answer("Только создатель может начать!", show_alert=True); return
    if len(room.player_ids) < 1: await call.answer("Нужен хотя бы 1 игрок!", show_alert=True); return
    await call.answer()
    await start_multi_game(room)

@dp.callback_query(F.data.startswith("delete_room_"))
async def cb_delete_room(call: CallbackQuery):
    room_id = call.data[12:]
    room    = rooms.get(room_id)
    if not room: await call.answer("Комната не найдена!", show_alert=True); return
    if call.from_user.id != room.host_id: await call.answer("Только создатель!", show_alert=True); return
    await notify_all_in_room(room, "❌ Создатель удалил комнату.")
    rooms.pop(room_id, None)
    await call.answer("Комната удалена.")
    await call.message.edit_text("❌ Комната удалена.", reply_markup=kb_back_menu())

@dp.callback_query(F.data.startswith("leave_room_"))
async def cb_leave_room(call: CallbackQuery):
    room_id = call.data[11:]
    room    = rooms.get(room_id)
    uid     = call.from_user.id
    if not room or uid not in room.player_ids: await call.answer("Ты не в этой комнате.", show_alert=True); return
    if room.active: await call.answer("Нельзя выйти из активной игры.", show_alert=True); return
    uname = room.player_names[uid]
    room.remove_player(uid)
    await call.answer("Ты вышел.")
    await call.message.edit_text("🚪 Ты вышел.", reply_markup=kb_back_menu())
    for other in room.player_ids:
        try: await bot.send_message(other, f"🚪 <b>{uname}</b> вышел из комнаты.")
        except Exception: pass

# ===========================================================================
# ГРУППОВЫЕ КОМНАТЫ
# ===========================================================================

@dp.callback_query(F.data == "group_create_room")
async def cb_group_create_start(call: CallbackQuery, state: FSMContext):
    if call.message.chat.type not in ("group","supergroup"):
        await call.answer("Только в группах!", show_alert=True); return
    await state.set_state(CreateGroupRoom.waiting_rounds)
    await call.message.edit_text("🎯 <b>Создание игры</b>\n\nСколько раундов?", reply_markup=kb_rounds("grrooms"))

@dp.callback_query(F.data.startswith("grrooms_"))
async def cb_gr_rounds(call: CallbackQuery, state: FSMContext):
    rounds = int(call.data.split("_")[1])
    await state.update_data(rounds=rounds)
    await state.set_state(CreateGroupRoom.waiting_players)
    await call.message.edit_text(
        f"✅ Раундов: <b>{rounds}</b>\n\nМаксимум игроков?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="∞ Без ограничений", callback_data="grplayers_0")],
            [InlineKeyboardButton(text="4", callback_data="grplayers_4"),
             InlineKeyboardButton(text="6", callback_data="grplayers_6"),
             InlineKeyboardButton(text="10", callback_data="grplayers_10")],
            [InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu")],
        ]))

@dp.callback_query(F.data.startswith("grplayers_"))
async def cb_gr_players_btn(call: CallbackQuery, state: FSMContext):
    await state.update_data(max_players=int(call.data.split("_")[1]))
    await state.set_state(CreateGroupRoom.waiting_difficulty)
    await call.message.edit_text("🎯 Выбери сложность:", reply_markup=kb_difficulty("grdiff"))

@dp.message(CreateGroupRoom.waiting_players)
async def msg_gr_players(message: Message, state: FSMContext):
    if message.chat.type not in ("group","supergroup"): return
    try:
        n = int(message.text.strip())
        if n < 0 or n > 100: raise ValueError()
    except ValueError:
        await message.reply("❌ Введи число от 0 до 100 (0 = без ограничений)."); return
    await state.update_data(max_players=n)
    await state.set_state(CreateGroupRoom.waiting_difficulty)
    await message.answer("🎯 Выбери сложность:", reply_markup=kb_difficulty("grdiff"))

@dp.callback_query(F.data.startswith("grdiff_"))
async def cb_gr_difficulty(call: CallbackQuery, state: FSMContext):
    diff = call.data[7:]
    await state.update_data(difficulty=diff)
    await state.set_state(CreateGroupRoom.waiting_category)
    await call.message.edit_text(
        f"Сложность: <b>{DIFFICULTY_SETTINGS[diff]['label']}</b>\n\nВыбери категорию:",
        reply_markup=kb_categories("grcat"))

@dp.callback_query(F.data.startswith("grcat_"))
async def cb_gr_category(call: CallbackQuery, state: FSMContext):
    cat_raw  = call.data[6:]
    if cat_raw == "random":
        category = random.choice(ALL_CATEGORIES)
    else:
        category = CATEGORY_ID_TO_NAME.get(cat_raw, cat_raw)
    data     = await state.get_data()
    uid      = call.from_user.id
    uname    = call.from_user.full_name
    chat_id  = call.message.chat.id
    ensure_user(uid, uname)
    if chat_id in group_rooms:
        old = group_rooms[chat_id]
        if old in rooms:
            await call.message.edit_text(f"❌ В группе уже есть комната! <code>{old}</code>")
            await state.clear(); return
    rounds = data.get("rounds", 3)
    max_players = data.get("max_players", 0)
    difficulty = data.get("difficulty", "medium")
    room = GameRoom(host_id=uid, host_name=uname, total_rounds=rounds,
                    max_players=max_players, category=category,
                    difficulty=difficulty, room_type="group", group_chat_id=chat_id)
    rooms[room.room_id]  = room
    group_rooms[chat_id] = room.room_id
    await state.clear()
    max_text = str(room.max_players) if room.max_players > 0 else "∞"
    sent = await call.message.edit_text(
        f"🎡 <b>Игра создана!</b>\n\n"
        f"🔑 Код: <code>{room.room_id}</code>\n"
        f"📚 Категория: <b>{category}</b>\n"
        f"🎯 Раундов: <b>{room.total_rounds}</b>\n"
        f"👥 1/{max_text}  |  {DIFFICULTY_SETTINGS[room.difficulty]['label']}\n\n"
        f"⏰ 5 минут на вход.",
        reply_markup=kb_group_lobby(room.room_id))
    room.group_message_id = sent.message_id
    await _notify_player_ls(uid, uname, room, is_host=True)
    asyncio.create_task(_group_room_deadline(room.room_id, chat_id))

async def _notify_player_ls(uid: int, uname: str, room: GameRoom, is_host: bool):
    role = "создатель комнаты" if is_host else "участник"
    kb   = kb_host_ls(room.room_id) if is_host else kb_player_ls(room.room_id)
    try:
        await bot.send_message(uid,
            f"🎡 <b>Ты {'создал' if is_host else 'вошёл в'} игру в группе!</b>\n\n"
            f"🔑 Комната: <code>{room.room_id}</code>\n"
            f"📚 {room.current_category}  |  {DIFFICULTY_SETTINGS[room.difficulty]['label']}\n"
            f"Роль: <b>{role}</b>",
            reply_markup=kb)
    except Exception as e:
        logger.warning(f"Не удалось отправить ЛС {uid}: {e}")

async def _group_room_deadline(room_id: str, chat_id: int):
    await asyncio.sleep(300)
    room = rooms.get(room_id)
    if not room or room.active: return
    if len(room.player_ids) < 2:
        await bot.send_message(chat_id, "⏰ Время набора вышло. Недостаточно игроков.")
        rooms.pop(room_id, None)
        group_rooms.pop(chat_id, None)
        return
    await bot.send_message(chat_id, "⏰ Время набора истекло! Начинаем...")
    await start_multi_game(room)

@dp.callback_query(F.data.startswith("gjoin_"))
async def cb_group_join(call: CallbackQuery):
    room_id = call.data[6:]
    room    = rooms.get(room_id)
    if not room: await call.answer("Комната не найдена!", show_alert=True); return
    if room.active: await call.answer("Игра уже началась!", show_alert=True); return
    uid   = call.from_user.id
    uname = call.from_user.full_name
    ensure_user(uid, uname)
    if uid in room.player_ids: await call.answer("Ты уже в игре!"); return
    if room.is_full: await call.answer("Комната заполнена!", show_alert=True); return
    room.add_player(uid, uname)
    await call.answer(f"✅ {uname} вошёл!")
    max_text = str(room.max_players) if room.max_players > 0 else "∞"
    players_list = "\n".join([f"{i+1}. {room.player_names[p]}" for i, p in enumerate(room.player_ids)])
    try:
        await call.message.edit_text(
            f"🎡 <b>Ожидаем...</b>\n\n"
            f"🔑 <code>{room.room_id}</code>  |  {room.current_category}\n"
            f"👥 {len(room.player_ids)}/{max_text}:\n{players_list}",
            reply_markup=kb_group_lobby(room.room_id))
    except Exception: pass
    await _notify_player_ls(uid, uname, room, is_host=False)
    if room.is_full:
        await asyncio.sleep(1)
        await start_multi_game(room)

@dp.callback_query(F.data.startswith("gstart_"))
async def cb_group_start(call: CallbackQuery):
    room_id = call.data[7:]
    room    = rooms.get(room_id)
    if not room: await call.answer("Комната не найдена!", show_alert=True); return
    if call.from_user.id != room.host_id: await call.answer("Только создатель!", show_alert=True); return
    if len(room.player_ids) < 2: await call.answer("Нужно минимум 2 игрока!", show_alert=True); return
    await call.answer()
    await start_multi_game(room)

@dp.callback_query(F.data.startswith("gcancel_ls_"))
async def cb_group_cancel_ls(call: CallbackQuery):
    room_id = call.data[11:]
    room    = rooms.get(room_id)
    if not room: await call.answer("Комната не найдена!", show_alert=True); return
    if call.from_user.id != room.host_id: await call.answer("Только создатель!", show_alert=True); return
    if room.active: await call.answer("Игра уже идёт.", show_alert=True); return
    try: await bot.send_message(room.group_chat_id, "❌ Хост отменил игру.")
    except Exception: pass
    for uid in room.player_ids:
        if uid == room.host_id: continue
        try: await bot.send_message(uid, f"❌ Хост отменил игру <code>{room_id}</code>.")
        except Exception: pass
    rooms.pop(room_id, None)
    group_rooms.pop(room.group_chat_id, None)
    await call.answer("Игра отменена.")
    await call.message.edit_text("❌ Игра отменена.", reply_markup=kb_back_menu())

@dp.callback_query(F.data.startswith("gcancel_"))
async def cb_group_cancel(call: CallbackQuery):
    room_id = call.data[8:]
    if room_id.startswith("ls_"): return
    room = rooms.get(room_id)
    if not room: await call.answer("Комната не найдена!", show_alert=True); return
    if call.from_user.id != room.host_id: await call.answer("Только создатель!", show_alert=True); return
    for uid in room.player_ids:
        try: await bot.send_message(uid, "❌ Игра отменена хостом.")
        except Exception: pass
    rooms.pop(room_id, None)
    group_rooms.pop(room.group_chat_id, None)
    await call.message.edit_text("❌ Игра отменена.")
    await call.answer("Игра отменена.")

@dp.callback_query(F.data.startswith("gleave_"))
async def cb_group_leave_ls(call: CallbackQuery):
    room_id = call.data[7:]
    room    = rooms.get(room_id)
    uid     = call.from_user.id
    if not room or uid not in room.player_ids: await call.answer("Ты не в этой игре.", show_alert=True); return
    if room.active: await call.answer("Нельзя выйти из активной игры.", show_alert=True); return
    uname = room.player_names[uid]
    room.remove_player(uid)
    await call.answer("Ты покинул игру.")
    await call.message.edit_text("🚪 Ты покинул игру.", reply_markup=kb_back_menu())
    try: await bot.send_message(room.group_chat_id, f"🚪 <b>{uname}</b> покинул игру.")
    except Exception: pass

# ===========================================================================
# СДАТЬСЯ
# ===========================================================================

@dp.callback_query(F.data.startswith("surrender_"))
async def cb_surrender(call: CallbackQuery):
    room_id = call.data[10:]
    room    = rooms.get(room_id)
    uid     = call.from_user.id
    if not room or not room.active: await call.answer("Игра уже завершена.", show_alert=True); return
    if uid not in room.player_ids: await call.answer("Ты не в этой игре.", show_alert=True); return
    uname = room.player_names[uid]
    room.player_ids.remove(uid)
    room.player_names.pop(uid, None)
    surrender_msg = f"🏳️ <b>{uname}</b> сдался."
    if len(room.player_ids) == 1:
        winner_uid  = room.player_ids[0]
        winner_name = room.player_names[winner_uid]
        win_msg = surrender_msg + f"\n\n🏆 <b>{winner_name}</b> — победитель!"
        if room.room_type == "group":
            try: await bot.send_message(room.group_chat_id, win_msg)
            except Exception: pass
        else: await notify_all_in_room(room, win_msg)
        sc = room.scores.get(winner_uid, 0)
        result = add_score_and_xp(winner_uid, sc, 0)
        if result.get("leveled_up"):
            try: await bot.send_message(winner_uid, f"🎉 <b>НОВЫЙ УРОВЕНЬ {result['new_level']}!</b> {result['new_rank_name']}")
            except Exception: pass
        room.active = False
        await call.answer("Ты сдался. Игра завершена.", show_alert=True)
        return
    elif len(room.player_ids) == 0:
        if room.room_type == "group":
            try: await bot.send_message(room.group_chat_id, surrender_msg + "\n\nВсе покинули игру.")
            except Exception: pass
        room.active = False
        await call.answer("Ты сдался.", show_alert=True)
        return
    if room.current_player_id == uid:
        room.current_player_idx = room.current_player_idx % len(room.player_ids)
    else:
        try:
            idx = room.player_ids.index(room.current_player_id)
            room.current_player_idx = idx
        except ValueError:
            room.current_player_idx = 0
    cont_msg = surrender_msg + f"\n\n👥 Игра продолжается! Осталось: {len(room.player_ids)}"
    if room.room_type == "group":
        try: await bot.send_message(room.group_chat_id, cont_msg)
        except Exception: pass
    else: await notify_all_in_room(room, cont_msg)
    await call.answer("Ты сдался. Игра продолжается.", show_alert=True)
    await asyncio.sleep(1)
    await send_turn_message(room)

# ===========================================================================
# ЗАПУСК МУЛЬТИПЛЕЕРНОЙ ИГРЫ
# ===========================================================================

async def start_multi_game(room: GameRoom):
    room.start_game()
    players_list = "\n".join([f"{i+1}. {room.player_names[p]}" for i, p in enumerate(room.player_ids)])
    msg = (f"🎉 <b>Игра началась!</b>\n\n"
           f"👥:\n{players_list}\n\n"
           f"🎯 Раундов: {room.total_rounds}  |  {DIFFICULTY_SETTINGS[room.difficulty]['label']}\n"
           f"📚 {room.current_category}")
    if room.room_type == "group":
        try: await bot.send_message(room.group_chat_id, msg)
        except Exception: pass
        try:
            await bot.send_message(room.group_chat_id,
                f"ℹ️ Буквы — текстом в чат (одна русская буква).\n"
                f"💡 Подсказка: /hint_{room.room_id}")
        except Exception: pass
        for uid in room.player_ids:
            try:
                await bot.send_message(uid, f"▶️ <b>Игра началась!</b> Следи в группе.")
            except Exception: pass
    else:
        await notify_all_in_room(room, msg)
    await asyncio.sleep(2)
    await send_turn_message(room)
    asyncio.create_task(afk_game_timer(room.room_id))

# ===========================================================================
# AFK TIMER
# ===========================================================================

async def afk_game_timer(room_id: str):
    while True:
        await asyncio.sleep(AFK_CHECK_INTERVAL)
        room = rooms.get(room_id)
        if not room or not room.active: return
        if time.time() - room.last_activity >= AFK_TIMEOUT:
            msg = "⏰ <b>Игра завершена из-за бездействия (1 час).</b>"
            if room.room_type == "group":
                try: await bot.send_message(room.group_chat_id, msg)
                except Exception: pass
            else: await notify_all_in_room(room, msg)
            room.active = False
            return

# ===========================================================================
# ВВОД БУКВ (group + private)
# ===========================================================================

@dp.message(F.text & ~F.via_bot)
async def msg_letter_input(message: Message, state: FSMContext):
    fsm_state = await state.get_state()
    if fsm_state in (
        SinglePlay.playing, SinglePlay.choosing_difficulty, SinglePlay.choosing_category,
        SinglePlay.choosing_rounds,
        CreateRoom.waiting_players, CreateRoom.waiting_rounds,
        CreateRoom.waiting_difficulty, CreateRoom.waiting_category,
        CreateGroupRoom.waiting_players, CreateGroupRoom.waiting_rounds,
        CreateGroupRoom.waiting_difficulty, CreateGroupRoom.waiting_category,
        JoinRoom.waiting_room_id, ProfileState.choosing_title,
        GiftState.entering_user, DuelState.waiting_opponent, DuelState.playing,
    ):
        return
    uid  = message.from_user.id
    text = message.text.strip().upper()
    if message.chat.type in ("group","supergroup"):
        room_id = group_rooms.get(message.chat.id)
        room    = rooms.get(room_id) if room_id else None
        if not room or not room.active: return
        if room.current_player_id != uid: return
        if len(text) == 1:
            if text not in ALPHABET: return
        elif text.isalpha() and all(c in ALPHABET for c in text):
            pass
        else:
            return
        if len(text) == 1 and room.spin_points is None and not room.prize_active:
            room.spin_points = random.choice([50,100,150,200,250,300,350,400,450,500])
    else:
        room = _find_room_by_player(uid)
    if not room or not room.active: return
    if room.current_player_id != uid: return
    cd = room.check_cooldown(uid)
    if cd > 0: return
    if len(text) > 1 and text.isalpha() and all(c in ALPHABET for c in text):
        room.last_activity = time.time()
        restart_turn_timer(room)
        await _handle_multi_word_guess(message, room, uid, text)
        return
    if len(text) != 1 or text not in ALPHABET: return
    if room.room_type == "private" and room.spin_points is None and not room.prize_active:
        await message.reply("🎡 Сначала крутни барабан!"); return
    if text in room.guessed_letters: await message.reply("Уже называлась!"); return
    room.apply_cooldown(uid)
    room.last_activity = time.time()
    restart_turn_timer(room)
    await _handle_multi_letter(message, room, uid, text)

async def _handle_multi_letter(message: Message, room: GameRoom, uid: int, letter: str):
    count = room.guess_letter(letter)
    uname = room.player_names[uid]
    if count > 0:
        base_pts   = room.spin_points if room.spin_points else 100
        earned     = base_pts * count
        multiplier = 2 if room.double_round else 1
        earned    *= multiplier
        if room.prize_active:
            room.round_scores[uid] = (room.round_scores.get(uid, 0) + earned) * 2
            room.prize_active = False
            prize_text = " 🎉 ПРИЗ — очки удвоены!"
        else:
            room.round_scores[uid] = room.round_scores.get(uid, 0) + earned
            prize_text = "  🔥x2" if room.double_round else ""
        if room.room_type == "group":
            await message.reply(f"✅ <b>«{letter}»</b> — {count} раз(а)! <b>+{earned}</b>{prize_text}")
        else:
            await notify_all_in_room(room,
                f"✅ <b>{uname}</b>: «{letter}» — {count} раз(а)! +{earned}{prize_text}")
        room.spin_points  = None
        room.prize_active = False
        if room.is_round_complete():
            if getattr(room,"jackpot_active",False):
                room.round_scores[uid] = room.round_scores.get(uid,0) + 500
                room.jackpot_active = False
                await notify_all_in_room(room, f"🎰 <b>ДЖЕКПОТ!</b> {uname} +500!")
            await asyncio.sleep(1)
            await finish_round(room)
        else:
            status = build_round_status(room)
            if room.room_type == "group":
                await bot.send_message(room.group_chat_id,
                    f"{status}\n\n👉 Ходит {mention(uid,uname)} — ещё букву или слово!")
            else:
                await bot.send_message(uid, f"{status}\n\n🎡 Ещё букву или крути барабан!",
                                       reply_markup=kb_spin(room, uid))
    else:
        if room.room_type == "group":
            await message.reply(f"❌ <b>«{letter}»</b> нет!")
        else:
            await notify_all_in_room(room, f"❌ <b>{uname}</b>: «{letter}» нет, ход переходит!")
        room.spin_points  = None
        room.prize_active = False
        room.next_player()
        await asyncio.sleep(1)
        await send_turn_message(room)

async def _handle_multi_word_guess(message: Message, room: GameRoom, uid: int, guess: str):
    uname = room.player_names[uid]
    room.apply_cooldown(uid)
    if guess == room.current_word:
        bonus = 200
        multiplier = 2 if room.double_round else 1
        earned = (room.round_scores.get(uid, 0) + bonus) * multiplier
        room.round_scores[uid] = earned
        room.scores[uid] += earned
        if room.room_type == "group":
            await message.reply(f"🎊 <b>{uname}</b> угадал: <b>{room.current_word}</b>! +{earned}")
        else:
            await notify_all_in_room(room, f"🎊 <b>{uname}</b> угадал: <b>{room.current_word}</b>! +{earned}")
        if getattr(room,"jackpot_active",False):
            room.round_scores[uid] += 500
            room.jackpot_active = False
            await notify_all_in_room(room, f"🎰 <b>ДЖЕКПОТ!</b> {uname} +500!")
        await asyncio.sleep(2)
        await finish_round(room)
    else:
        room.spin_points = None
        room.next_player()
        next_name = room.player_names[room.current_player_id]
        if room.room_type == "group":
            await message.reply(f"❌ Неверно! Ход к <b>{next_name}</b>.")
        else:
            await notify_all_in_room(room, f"❌ <b>{uname}</b> — неверно! Ход к <b>{next_name}</b>.")
        await asyncio.sleep(1)
        await send_turn_message(room)

# ===========================================================================
# БАРАБАН (ЛС-мультиплеер)
# ===========================================================================

@dp.callback_query(F.data == "spin_wheel")
async def cb_spin_wheel(call: CallbackQuery):
    uid  = call.from_user.id
    room = _find_room_by_player(uid)
    if not room or room.room_type != "private": await call.answer("Игра не найдена!", show_alert=True); return
    if room.current_player_id != uid: await call.answer("Сейчас не твой ход!", show_alert=True); return
    await call.answer()
    room.last_activity = time.time()
    restart_turn_timer(room)
    sector = spin_wheel()
    room.current_sector = sector
    uname  = room.player_names[uid]

    if sector == "БАНКРОТ":
        u_bk = get_user(uid)
        if u_bk and u_bk.get("bankrupt_shields", 0) > 0:
            use_bankrupt_shield(uid)
            status = build_round_status(room)
            await notify_all_in_room(room, f"💎 <b>БАНКРОТ!</b> {uname} — но сработала <b>Защита от банкрота</b>! Очки сохранены.")
            await call.message.edit_text(
                f"💎 <b>БАНКРОТ — защита сработала!</b>\n\n{status}\n\nМожешь крутить ещё!",
                reply_markup=kb_spin(room, uid)
            )
        else:
            old = room.round_scores[uid]
            room.round_scores[uid] = 0
            await call.message.edit_text(f"💀 <b>БАНКРОТ!</b> {uname} теряет {old} очков раунда!")
            room.next_player()
            await asyncio.sleep(2)
            await send_turn_message(room)

    elif sector == "ПРОПУСК":
        u = get_user(uid)
        if u and u["skip_skips"] > 0:
            use_skip_skip(uid)
            await call.message.edit_text(f"⏩ ПРОПУСК — <b>🛡 Защита сработала!</b>",
                                         reply_markup=kb_spin(room, uid))
        else:
            await call.message.edit_text(f"⏩ <b>ПРОПУСК!</b> {uname} пропускает ход.")
            room.next_player()
            await asyncio.sleep(2)
            await send_turn_message(room)

    elif sector == "ПРИЗ":
        room.prize_active = True
        status = build_round_status(room)
        await notify_all_in_room(room, f"⭐ <b>ПРИЗ!</b> {uname} угадает букву — очки удвоятся!")
        await call.message.edit_text(f"⭐ <b>ПРИЗ!</b> Угадай букву — очки x2!\n\n{status}\n\nНапиши букву:")

    elif sector == "ДВОЙНОЙ":
        room.double_round = True
        status = build_round_status(room)
        await notify_all_in_room(room, f"🔥 <b>ДВОЙНОЙ РАУНД!</b> {uname} выбил двойной — весь следующий раунд x2!")
        await call.message.edit_text(f"🔥 <b>ДВОЙНОЙ РАУНД!</b> Очки раунда x2!\n\n{status}\n\nНапиши букву:")
        grant_achievement(uid, "double_win")

    elif sector == "ВОРОВСТВО":
        # Steal from random opponent
        opponents = [p for p in room.player_ids if p != uid and room.round_scores.get(p, 0) > 0]
        if not opponents:
            status = build_round_status(room)
            await call.message.edit_text(f"🦊 <b>ВОРОВСТВО!</b> Некого грабить — у соперников 0 очков раунда.\n\n{status}",
                                         reply_markup=kb_spin(room, uid))
        else:
            victim_uid  = random.choice(opponents)
            victim_name = room.player_names[victim_uid]
            stolen = room.round_scores[victim_uid] // 2
            room.round_scores[victim_uid] -= stolen
            room.round_scores[uid]        = room.round_scores.get(uid, 0) + stolen
            grant_achievement(uid, "thief")
            status = build_round_status(room)
            await notify_all_in_room(room,
                f"🦊 <b>ВОРОВСТВО!</b> {uname} украл <b>{stolen}</b> очков раунда у {victim_name}!")
            await call.message.edit_text(
                f"🦊 <b>ВОРОВСТВО!</b> Украдено {stolen} очков у {victim_name}!\n\n{status}\n\nМожешь крутить ещё!",
                reply_markup=kb_spin(room, uid))

    elif sector == "БОНУС":
        room.round_scores[uid] = room.round_scores.get(uid, 0) + 200
        status = build_round_status(room)
        await notify_all_in_room(room, f"🎁 <b>БОНУС!</b> {uname} +200 очков раунда!")
        await call.message.edit_text(f"🎁 <b>БОНУС!</b> +200 очков.\n\n{status}\n\nМожешь крутить ещё!",
                                     reply_markup=kb_spin(room, uid))

    elif sector == "МИНУС":
        room.round_scores[uid] = max(0, room.round_scores.get(uid, 0) - 200)
        status = build_round_status(room)
        await notify_all_in_room(room, f"🧨 <b>МИНУС!</b> {uname} -200 очков раунда.")
        await call.message.edit_text(f"🧨 <b>МИНУС!</b> -200 очков.\n\n{status}\n\nМожешь крутить ещё!",
                                     reply_markup=kb_spin(room, uid))

    elif sector == "ПОДСКАЗКА":
        add_free_hints(uid, 1)
        u2 = get_user(uid)
        status = build_round_status(room)
        await notify_all_in_room(room, f"💡 <b>ПОДСКАЗКА!</b> {uname} +1 подсказка.")
        await call.message.edit_text(
            f"💡 <b>ПОДСКАЗКА!</b> Теперь: <b>{u2['free_hints'] if u2 else 0}</b>.\n\n{status}\n\nМожешь крутить ещё!",
            reply_markup=kb_spin(room, uid))

    elif sector == "ЩИТ":
        add_skip_skips(uid, 1)
        u2 = get_user(uid)
        status = build_round_status(room)
        await notify_all_in_room(room, f"🛡 <b>ЩИТ!</b> {uname} +1 защита от ПРОПУСКА.")
        await call.message.edit_text(
            f"🛡 <b>ЩИТ!</b> Теперь: <b>{u2['skip_skips'] if u2 else 0}</b>.\n\n{status}\n\nМожешь крутить ещё!",
            reply_markup=kb_spin(room, uid))

    elif sector == "ДЖЕКПОТ":
        room.jackpot_active = True
        room.spin_points    = 300
        status = build_round_status(room)
        await notify_all_in_room(room,
            f"🎰 <b>ДЖЕКПОТ!</b> {uname} — 300 очков за букву + 500 за слово!")
        await call.message.edit_text(f"🎰 <b>ДЖЕКПОТ!</b> 300/букву + 500 за слово!\n\n{status}\n\nНапиши букву:")

    else:
        points = int(sector)
        room.spin_points = points
        status = build_round_status(room)
        await call.message.edit_text(f"🎡 <b>Барабан: {points} очков!</b>\n\n{status}\n\nНапиши букву:")

@dp.callback_query(F.data == "use_free_hint_multi")
async def cb_use_free_hint_multi(call: CallbackQuery):
    uid  = call.from_user.id
    room = _find_room_by_player(uid)
    if not room: await call.answer("Игра не найдена!", show_alert=True); return
    if room.current_player_id != uid: await call.answer("Не твой ход!", show_alert=True); return
    u = get_user(uid)
    if not u or u["free_hints"] <= 0: await call.answer("Подсказок нет!", show_alert=True); return
    room.last_activity = time.time()
    restart_turn_timer(room)
    hidden = [c for c in set(room.current_word) if c.isalpha() and c not in room.guessed_letters]
    if not hidden: await call.answer("Все буквы открыты!", show_alert=True); return
    letter = random.choice(hidden)
    room.guessed_letters.add(letter)
    use_free_hint(uid)
    await call.answer(f"💡 «{letter}» открыта!")
    uname = room.player_names[uid]
    await notify_all_in_room(room, f"💡 <b>{uname}</b> использовал подсказку: «{letter}»!")
    if room.is_round_complete():
        if getattr(room,"jackpot_active",False):
            room.round_scores[uid] += 500
            room.jackpot_active = False
        await finish_round(room)
    else:
        status = build_round_status(room)
        await call.message.edit_text(f"{status}\n\nЕщё букву или крути барабан!", reply_markup=kb_spin(room, uid))

@dp.callback_query(F.data.startswith("word_replace_multi_"))
async def cb_word_replace_multi(call: CallbackQuery):
    uid     = call.from_user.id
    room_id = call.data[len("word_replace_multi_"):]
    room    = rooms.get(room_id)
    if not room or not room.active: await call.answer("Игра не найдена.", show_alert=True); return
    if room.current_player_id != uid: await call.answer("Не твой ход!", show_alert=True); return
    if not use_word_replace(uid): await call.answer("❌ Замен слова нет!", show_alert=True); return
    room._load_round()
    room.last_activity = time.time()
    restart_turn_timer(room)
    uname  = room.player_names[uid]
    await notify_all_in_room(room, f"🔄 <b>{uname}</b> заменил слово!\n\n{build_round_status(room)}")
    await call.answer("🔄 Слово заменено!", show_alert=True)
    await send_turn_message(room)

@dp.callback_query(F.data.startswith("word_replace_group_"))
async def cb_word_replace_group(call: CallbackQuery):
    uid     = call.from_user.id
    room_id = call.data[len("word_replace_group_"):]
    room    = rooms.get(room_id)
    if not room or not room.active: await call.answer("Игра не найдена.", show_alert=True); return
    if room.current_player_id != uid: await call.answer("Не твой ход!", show_alert=True); return
    if not use_word_replace(uid): await call.answer("❌ Замен слова нет!", show_alert=True); return
    room._load_round()
    room.last_activity = time.time()
    restart_turn_timer(room)
    uname  = room.player_names[uid]
    await call.answer("🔄 Слово заменено!", show_alert=True)
    try:
        await bot.send_message(room.group_chat_id,
            f"🔄 <b>{uname}</b> заменил слово!\n\n{build_round_status(room)}\n\n"
            f"👉 Ход: <b>{mention(uid, uname)}</b>\n⏰ {TURN_TIMEOUT_SEC} секунд. Напишите букву!",
            reply_markup=kb_group_active(room.room_id, uid))
    except Exception as e:
        logger.warning(f"word_replace_group error: {e}")

@dp.callback_query(F.data == "guess_word_multi")
async def cb_guess_word_multi(call: CallbackQuery):
    uid  = call.from_user.id
    room = _find_room_by_player(uid)
    if not room: await call.answer("Игра не найдена!", show_alert=True); return
    if room.current_player_id != uid: await call.answer("Не твой ход!", show_alert=True); return
    await call.answer()
    room.last_activity = time.time()
    restart_turn_timer(room)
    await call.message.answer("🔤 Напиши слово целиком:")

# ===========================================================================
# ЗАВЕРШЕНИЕ РАУНДА / ИГРЫ
# ===========================================================================

async def finish_round(room: GameRoom):
    for uid in room.player_ids:
        room.scores[uid] = room.scores.get(uid, 0) + room.round_scores.get(uid, 0)
    winner_uid  = max(room.round_scores, key=lambda x: room.round_scores.get(x, 0))
    winner_name = room.player_names[winner_uid]
    w_score     = room.round_scores[winner_uid]
    scores_text = "\n".join([
        f"{'🥇' if i == 0 else '  '} {room.player_names[uid]}: {room.scores[uid]}"
        for i, uid in enumerate(sorted(room.player_ids, key=lambda x: room.scores[x], reverse=True))
    ])
    msg = (f"🏁 <b>Раунд {room.current_round} завершён!</b>\n\n"
           f"🔤 Слово: <b>{room.current_word}</b>\n"
           f"🏆 Лучший: <b>{winner_name}</b> (+{w_score})\n\n"
           f"💰 Счёт:\n{scores_text}")
    if room.room_type == "group":
        try: await bot.send_message(room.group_chat_id, msg)
        except Exception: pass
    else: await notify_all_in_room(room, msg)
    await asyncio.sleep(3)
    if room.has_next_round():
        room.next_round()
        next_msg = f"🎯 <b>Раунд {room.current_round}/{room.total_rounds}</b>  {room.current_category}"
        if room.room_type == "group":
            try: await bot.send_message(room.group_chat_id, next_msg)
            except Exception: pass
        else: await notify_all_in_room(room, next_msg)
        await asyncio.sleep(2)
        await send_turn_message(room)
    else:
        await finish_game(room)

async def finish_game(room: GameRoom):
    sorted_players = sorted(room.player_ids, key=lambda x: room.scores.get(x, 0), reverse=True)
    champion_uid   = sorted_players[0]
    champion_name  = room.player_names[champion_uid]
    medals = ["🥇","🥈","🥉"] + [f"{i}." for i in range(4, 20)]
    results = [f"{medals[i]} {room.player_names[uid]}: <b>{room.scores.get(uid, 0)}</b> очков"
               for i, uid in enumerate(sorted_players)]
    final_msg = (f"🎊 <b>ИГРА ОКОНЧЕНА!</b>\n\n"
                 f"🏆 <b>ПОБЕДИТЕЛЬ: {champion_name}!</b>\n\n"
                 f"📊 Итог:\n" + "\n".join(results) + "\n\nСпасибо за игру! /menu")
    if room.room_type == "group":
        try: await bot.send_message(room.group_chat_id, final_msg, reply_markup=kb_rematch(room.room_id))
        except Exception: pass
    else:
        await notify_all_in_room(room, final_msg, reply_markup=kb_rematch(room.room_id))
    for uid in room.player_ids:
        sc     = room.scores.get(uid, 0)
        result = add_score_and_xp(uid, sc, 0)
        await check_achievements(uid, sc)
        if result.get("leveled_up"):
            rewards = result.get("rewards", {})
            lv_txt  = f"🎉 <b>НОВЫЙ УРОВЕНЬ {result['new_level']}!</b> {result['new_rank_name']}\n"
            if rewards.get("hints"):        lv_txt += f"💡 +{rewards['hints']} подсказок\n"
            if rewards.get("skip_skips"):   lv_txt += f"🛡 +{rewards['skip_skips']} защит\n"
            if rewards.get("word_replaces"):lv_txt += f"🔄 +{rewards['word_replaces']} замен слова\n"
            if rewards.get("titles"):       lv_txt += f"🏷 {', '.join(rewards['titles'])}\n"
            ec = result.get("earned_coins", 0)
            lv_txt += f"💰 +{ec} монет за игру"
            try: await bot.send_message(uid, lv_txt)
            except Exception: pass
    _cancel_turn_timer(room.room_id)
    room.active = False

def _reset_room_for_rematch(room: GameRoom):
    _cancel_turn_timer(room.room_id)
    room.active = False
    room.current_round = 0
    room.current_player_idx = 0
    room.turn_counter = 0
    room.turn_timer_token = 0
    room.current_category = room.base_category
    room.guessed_letters = set()
    room.used_words.clear()
    room.spin_points = None
    room.prize_active = False
    room.jackpot_active = False
    room.double_round = False
    for uid in room.player_ids:
        room.scores[uid] = 0
        room.round_scores[uid] = 0

@dp.callback_query(F.data.startswith("rematch_"))
async def cb_rematch(call: CallbackQuery):
    room_id = call.data.split("_", 1)[1]
    room    = rooms.get(room_id)
    if not room: await call.answer("Комната не найдена.", show_alert=True); return
    if room.active: await call.answer("Игра уже идёт.", show_alert=True); return
    if call.from_user.id != room.host_id: await call.answer("Только хост.", show_alert=True); return
    _reset_room_for_rematch(room)
    if room.room_type == "group":
        group_rooms[room.group_chat_id] = room.room_id
    await call.answer("Запускаю рематч!")
    await start_multi_game(room)

# ===========================================================================
# ЗАПУСК
# ===========================================================================

async def main():
    init_db()
    logger.info("Запуск Поле Чудес бота...")
    await bot.set_my_commands([
        BotCommand(command="start",  description="Главное меню"),
        BotCommand(command="menu",   description="Главное меню"),
        BotCommand(command="single", description="🎮 Одиночная игра"),
        BotCommand(command="multi",  description="👥 Мультиплеер"),
    ])
    await dp.start_polling(bot, skip_updates=True,
                           allowed_updates=["message","callback_query","my_chat_member","chat_member"])

if __name__ == "__main__":
    asyncio.run(main())
