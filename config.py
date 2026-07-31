import os
from enum import Enum
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TEMPLATES_DIR = BASE_DIR / "templates"

CHARACTERS_FILE = DATA_DIR / "characters.json"
FOODS_FILE = DATA_DIR / "foods.json"
ANSWER_PATTERNS_FILE = DATA_DIR / "answer_patterns.json"

CHATBOT_ID = "Italy"

class Stage(str, Enum):
    WAIT_GREETING = "WAIT_GREETING"
    WAIT_NAME = "WAIT_NAME"
    WAIT_COUNTRY = "WAIT_COUNTRY"
    FOOD_Q1 = "FOOD_Q1"
    FOOD_A1 = "FOOD_A1"
    FOOD_Q2 = "FOOD_Q2"
    FOOD_A2 = "FOOD_A2"
    FOOD_Q3 = "FOOD_Q3"
    FOOD_A3 = "FOOD_A3"
    FREE_CHAT = "FREE_CHAT"
    END = "END"

INITIAL_STAGE = Stage.WAIT_GREETING
MODEL_NAME = "gpt-4o-mini"
TEMPERATURE = 0.3
MAX_RESPONSE_TOKENS = 100
MAX_HISTORY_MESSAGES = 30

ENABLE_GOOGLE_SHEETS = True
SPREADSHEET_ID = "1D1xcyBiIOtBE3QfrPMx84RVIREf-8kq5XDqTZWCrDMU"
GOOGLE_SERVICE_ACCOUNT_ENV = "GOOGLE_SERVICE_ACCOUNT"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "italy-chatbot-secret-key")

ENDING_EXPRESSIONS = [
    "no", "no thank you", "no thanks", "nothing", "that's all",
    "that is all", "bye", "goodbye", "see you", "없어요", "없어"
]

KOREAN_NAME_EXAMPLES = [
    "민수", "정훈", "하빈", "다빈", "다영", "지은", "우빈", "다정",
    "연준", "하준", "서준", "형준", "연서", "은서", "선영", "근환", "지환"
]
