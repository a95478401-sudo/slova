import random
import uuid
import time
from typing import Optional
from words import WORDS_BY_CATEGORY, ALL_CATEGORIES

ALPHABET = list("АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ")

WHEEL_SECTORS = [
    "50","100","150","200","250","300","350","400","450","500","600","700",
    "100","150","200","250","300","400","500",
    "ПРИЗ","ПРИЗ",
    "БОНУС","БОНУС",
    "ПОДСКАЗКА",
    "ЩИТ",
    "ДЖЕКПОТ",
    "МИНУС",
    "ВОРОВСТВО",
    "ДВОЙНОЙ",
    "ПРОПУСК","ПРОПУСК",
    "БАНКРОТ","БАНКРОТ",
]

DIFFICULTY_SETTINGS = {
    "easy":   {"min_len": 3,  "max_len": 5,  "lives": 7, "label": "🟢 Лёгкий"},
    "medium": {"min_len": 6,  "max_len": 8,  "lives": 5, "label": "🟡 Средний"},
    "hard":   {"min_len": 9,  "max_len": 99, "lives": 4, "label": "🔴 Сложный"},
}

def spin_wheel() -> str:
    return random.choice(WHEEL_SECTORS)

def format_word_display(word: str, guessed: set) -> str:
    result = []
    for char in word:
        if char == " ":
            result.append("  ")
        elif char == "-":
            result.append("-")
        elif char.upper() in guessed:
            result.append(char.upper())
        else:
            result.append("_")
    return " ".join(result)

# ---------------------------------------------------------------------------
# Одиночная игра
# ---------------------------------------------------------------------------
class SinglePlayerGame:
    def __init__(self, user_id: int, difficulty: str, category: str):
        self.user_id    = user_id
        self.difficulty = difficulty
        self.category   = category
        cfg             = DIFFICULTY_SETTINGS[difficulty]
        self.min_len    = cfg["min_len"]
        self.max_len    = cfg["max_len"]
        self.max_lives  = cfg["lives"]
        self.total_words = 5

        self.score         = 0
        self.words_guessed = 0
        self.word_index    = 0
        self.word_list: list = []

        self.word            = ""
        self.hint            = ""
        self.guessed_letters: set = set()
        self.lives           = self.max_lives
        self.word_guessed    = False
        self.spin_points: int = 0
        self.errors_this_word = 0  # для достижения perfect_word

    def load_words(self) -> bool:
        pool = WORDS_BY_CATEGORY.get(self.category, [])
        filtered = [
            w for w in pool
            if self.min_len <= len(w["word"].replace(" ","").replace("-","")) <= self.max_len
        ]
        if not filtered:
            filtered = pool[:]
        if not filtered:
            return False
        unique: dict = {}
        for entry in filtered:
            key = entry.get("word","").strip().upper()
            if key and key not in unique:
                unique[key] = entry
        filtered = list(unique.values())
        if not filtered:
            return False
        random.shuffle(filtered)
        self.word_list   = filtered[:self.total_words] if len(filtered) >= self.total_words else filtered
        self.total_words = len(self.word_list)
        self._load_current_word()
        return True

    def _load_current_word(self):
        entry                = self.word_list[self.word_index]
        self.word            = entry["word"].upper()
        self.hint            = entry["hint"]
        self.guessed_letters = set()
        self.lives           = self.max_lives
        self.word_guessed    = False
        self.errors_this_word = 0
        self.word_index     += 1
        self.spin_points = random.choice([50,100,100,150,150,200,200,250,300,350,400,500])

    def guess_letter(self, letter: str) -> int:
        letter = letter.upper()
        self.guessed_letters.add(letter)
        count = self.word.count(letter)
        if count == 0:
            self.lives -= 1
            self.errors_this_word += 1
        else:
            self.score += count * self.spin_points
        return count

    def use_hint(self, free: bool = False) -> Optional[str]:
        hidden = [c for c in set(self.word) if c.isalpha() and c not in self.guessed_letters]
        if not hidden:
            return None
        letter = random.choice(hidden)
        if not free:
            self.score = max(0, self.score - 50)
        self.guessed_letters.add(letter)
        return letter

    def is_word_complete(self) -> bool:
        return all(c in self.guessed_letters or c in (" ","-") for c in self.word)

    def next_word(self, replace: bool = False) -> bool:
        if replace:
            used = {e["word"].upper() for e in self.word_list[:self.word_index - 1]}
            pool = WORDS_BY_CATEGORY.get(self.category, [])
            filtered = [w for w in pool
                        if self.min_len <= len(w["word"].replace(" ","").replace("-","")) <= self.max_len
                        and w["word"].upper() not in used and w["word"].upper() != self.word]
            if not filtered:
                filtered = [w for w in pool if w["word"].upper() != self.word]
            if not filtered:
                return False
            replacement = random.choice(filtered)
            self.word_list[self.word_index - 1] = replacement
            self.word_index -= 1
            self._load_current_word()
            return True
        if self.word_index >= len(self.word_list):
            return False
        self._load_current_word()
        return True

# ---------------------------------------------------------------------------
# Дуэль (1 на 1, одно слово, кто быстрее)
# ---------------------------------------------------------------------------
class DuelGame:
    def __init__(self, player1_id: int, player1_name: str,
                 player2_id: int, player2_name: str,
                 difficulty: str = "medium", category: str = "random"):
        self.duel_id      = uuid.uuid4().hex[:6].upper()
        self.p1_id        = player1_id
        self.p1_name      = player1_name
        self.p2_id        = player2_id
        self.p2_name      = player2_name
        self.difficulty   = difficulty
        self.category     = category
        self.active       = True
        self.winner_id: Optional[int] = None
        self.started_at   = time.time()

        self.word = ""
        self.hint = ""
        self.p1_guessed: set = set()
        self.p2_guessed: set = set()
        self.p1_errors  = 0
        self.p2_errors  = 0

        cfg = DIFFICULTY_SETTINGS[difficulty]
        self.min_len = cfg["min_len"]
        self.max_len = cfg["max_len"]
        self._load_word()

    def _load_word(self):
        from words import WORDS_BY_CATEGORY, ALL_CATEGORIES
        cat = self.category if self.category != "random" else random.choice(ALL_CATEGORIES)
        self.category = cat
        pool = WORDS_BY_CATEGORY.get(cat, [])
        filtered = [w for w in pool
                    if self.min_len <= len(w["word"].replace(" ","").replace("-","")) <= self.max_len]
        if not filtered:
            filtered = pool or [{"word":"СЛОВО","hint":"Загаданное слово"}]
        entry = random.choice(filtered)
        self.word = entry["word"].upper()
        self.hint = entry["hint"]

    def guess_letter(self, player_id: int, letter: str) -> int:
        letter = letter.upper()
        if player_id == self.p1_id:
            self.p1_guessed.add(letter)
        else:
            self.p2_guessed.add(letter)
        count = self.word.count(letter)
        if count == 0:
            if player_id == self.p1_id: self.p1_errors += 1
            else: self.p2_errors += 1
        return count

    def is_complete(self, player_id: int) -> bool:
        guessed = self.p1_guessed if player_id == self.p1_id else self.p2_guessed
        return all(c in guessed or c in (" ","-") for c in self.word)

    def guess_word(self, player_id: int, word: str) -> bool:
        return word.upper() == self.word

    def set_winner(self, player_id: int):
        self.winner_id = player_id
        self.active = False

# ---------------------------------------------------------------------------
# Мультиплеерная комната
# ---------------------------------------------------------------------------
class GameRoom:
    def __init__(self, host_id: int, host_name: str, total_rounds: int,
                 max_players: int, category: str, difficulty: str = "medium",
                 room_type: str = "private", group_chat_id: int = 0,
                 is_public: bool = False):
        self.room_id        = self._gen_room_id()
        self.host_id        = host_id
        self.total_rounds   = total_rounds
        self.max_players    = max_players
        self.base_category  = category
        self.difficulty     = difficulty
        self.room_type      = room_type
        self.group_chat_id  = group_chat_id
        self.group_message_id: Optional[int] = None
        self.is_public      = is_public  # True = поиск рандомов

        self.player_ids:   list  = []
        self.player_names: dict  = {}
        self.scores:       dict  = {}
        self.round_scores: dict  = {}

        self.active             = False
        self.current_round      = 0
        self.current_player_idx = 0
        self.turn_counter       = 0
        self.turn_timer_token   = 0
        self.last_activity      = 0.0
        self.double_round       = False  # активен ли двойной раунд

        self.current_word     = ""
        self.current_hint     = ""
        self.current_category = category
        self.guessed_letters: set = set()
        self.used_words: set = set()

        self.spin_points:    Optional[int] = None
        self.prize_active:   bool          = False
        self.jackpot_active: bool          = False
        self.current_sector: str           = ""

        self.letter_cooldowns: dict = {}
        self.COOLDOWN_SEC = 0.5
        self.join_deadline: float = time.time() + 300

        self.add_player(host_id, host_name)

    @staticmethod
    def _gen_room_id() -> str:
        return uuid.uuid4().hex[:6].upper()

    def add_player(self, uid: int, name: str):
        self.player_ids.append(uid)
        self.player_names[uid] = name
        self.scores[uid]       = 0
        self.round_scores[uid] = 0

    def remove_player(self, uid: int):
        if uid in self.player_ids:
            self.player_ids.remove(uid)
            self.player_names.pop(uid, None)
            self.scores.pop(uid, None)
            self.round_scores.pop(uid, None)
            if self.current_player_idx >= len(self.player_ids):
                self.current_player_idx = 0

    @property
    def current_player_id(self) -> int:
        if not self.player_ids: return 0
        return self.player_ids[self.current_player_idx % len(self.player_ids)]

    def check_cooldown(self, uid: int) -> float:
        last = self.letter_cooldowns.get(uid, 0)
        diff = time.time() - last
        if diff < self.COOLDOWN_SEC:
            return self.COOLDOWN_SEC - diff
        return 0

    def apply_cooldown(self, uid: int):
        self.letter_cooldowns[uid] = time.time()

    def next_player(self):
        self.current_player_idx = (self.current_player_idx + 1) % max(1, len(self.player_ids))
        self.spin_points  = None
        self.prize_active = False
        self.jackpot_active = False
        self.turn_counter += 1

    def start_game(self):
        self.active        = True
        self.current_round = 1
        self._load_round()

    def _get_word_pool(self) -> list:
        cfg  = DIFFICULTY_SETTINGS[self.difficulty]
        pool = WORDS_BY_CATEGORY.get(self.current_category, [])
        if not pool:
            for cat_words in WORDS_BY_CATEGORY.values():
                pool.extend(cat_words)
        filtered = [w for w in pool
                    if cfg["min_len"] <= len(w["word"].replace(" ","").replace("-","")) <= cfg["max_len"]
                    and w.get("word","").upper() not in self.used_words]
        if not filtered:
            self.used_words.clear()
            filtered = [w for w in pool
                        if cfg["min_len"] <= len(w["word"].replace(" ","").replace("-","")) <= cfg["max_len"]]
        if not filtered:
            filtered = pool[:]
        seen: set = set()
        deduped = []
        for w in filtered:
            key = w.get("word","").strip().upper()
            if key and key not in seen:
                seen.add(key)
                deduped.append(w)
        return deduped

    def _load_round(self):
        pool      = self._get_word_pool()
        available = [w for w in pool if w.get("word","").upper() not in self.used_words] if pool else []
        if not available and pool:
            self.used_words.clear()
            available = pool
        entry     = random.choice(available) if available else {"word":"СЛОВО","hint":"Загаданное слово"}
        word_upper = entry.get("word","СЛОВО").upper()
        self.used_words.add(word_upper)
        self.current_word    = word_upper
        self.current_hint    = entry["hint"]
        self.guessed_letters = set()
        self.double_round    = False
        for uid in self.player_ids:
            self.round_scores[uid] = 0
        self.spin_points    = None
        self.prize_active   = False
        self.jackpot_active = False
        self.turn_counter  += 1

    def guess_letter(self, letter: str) -> int:
        letter = letter.upper()
        self.guessed_letters.add(letter)
        return self.current_word.count(letter)

    def is_round_complete(self) -> bool:
        return all(c in self.guessed_letters or c in (" ","-") for c in self.current_word)

    def has_next_round(self) -> bool:
        return self.current_round < self.total_rounds

    def next_round(self):
        self.current_round     += 1
        self.current_player_idx = (self.current_round - 1) % max(1, len(self.player_ids))
        self._load_round()

    @property
    def is_full(self) -> bool:
        if self.max_players == 0: return False
        return len(self.player_ids) >= self.max_players
