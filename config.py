"""
config.py

AI English Chatbot의 공통 설정을 관리합니다.

이 파일에서는 다음 내용을 설정합니다.

1. 대화 단계
2. 캐릭터와 국가 정보
3. 한국어 힌트
4. GPT 모델 설정
5. 음식 대화 횟수
6. Yes/No 응답 패턴 설정
7. JSON 데이터 파일 위치

음식, 이름, 국가 표현, Yes/No 패턴의 실제 목록은
data 폴더의 JSON 파일에서 따로 관리합니다.
"""

from enum import Enum
from pathlib import Path


# =========================================================
# 1. 프로젝트 경로
# =========================================================

# config.py가 들어 있는 프로젝트의 최상위 폴더
BASE_DIR = Path(__file__).resolve().parent

# 수정 가능한 데이터 파일이 들어 있는 폴더
DATA_DIR = BASE_DIR / "data"

FOODS_FILE = DATA_DIR / "foods.json"
NAMES_FILE = DATA_DIR / "names.json"
COUNTRIES_FILE = DATA_DIR / "countries.json"
ANSWER_PATTERNS_FILE = DATA_DIR / "answer_patterns.json"


# =========================================================
# 2. 대화 단계
# =========================================================

class Stage(str, Enum):
    """
    현재 학생이 어떤 대화 단계에 있는지를 나타냅니다.

    str을 함께 상속하므로 Flask 세션이나 JSON에도
    문자열 형태로 안전하게 저장할 수 있습니다.
    """

    WAIT_GREETING = "WAIT_GREETING"
    WAIT_NAME = "WAIT_NAME"
    WAIT_COUNTRY = "WAIT_COUNTRY"

    FOOD_QUESTION_1 = "FOOD_QUESTION_1"
    FOOD_ANSWER_1 = "FOOD_ANSWER_1"

    FOOD_QUESTION_2 = "FOOD_QUESTION_2"
    FOOD_ANSWER_2 = "FOOD_ANSWER_2"

    FOOD_QUESTION_3 = "FOOD_QUESTION_3"
    FOOD_ANSWER_3 = "FOOD_ANSWER_3"

    FREE_CHAT = "FREE_CHAT"
    END = "END"


# 챗봇을 처음 시작했을 때의 단계
INITIAL_STAGE = Stage.WAIT_GREETING


# =========================================================
# 3. 캐릭터와 국가 설정
# =========================================================

CHARACTER = {
    # 학생과 대화하는 캐릭터의 이름
    "name": "Luca",

    # 캐릭터가 사는 나라
    "country": "Italy",

    # 화면에 사용할 수 있는 국기 또는 캐릭터 이모지
    "emoji": "🇮🇹",

    # 챗봇 첫 화면에 표시할 문장
    "welcome_message": "Welcome to Italy!",

    # 학생이 인사하면 캐릭터가 말할 문장
    "greeting_reply": "Hi, I'm Luca. What's your name?",

    # 학생이 이름을 말한 뒤 사용할 문장
    # {student_name} 자리에 학생 이름이 들어갑니다.
    "name_reply": (
        "Oh! Hello, {student_name}! "
        "Nice to meet you. Where are you from?"
    ),

    # 학생이 한국에서 왔다고 말한 뒤 사용할 문장
    "country_reply": (
        "I'm from Italy! "
        "Now ask me any questions."
    ),

    # 대화 종료 문장
    "ending_message": (
        "It was nice to meet you. "
        "See you next time! Bye."
    ),
}


# =========================================================
# 4. 화면의 한국어 힌트
# =========================================================

HINTS = {
    Stage.WAIT_GREETING:
        "인사를 나눠보세요.",

    Stage.WAIT_NAME:
        "내 이름을 소개해 보세요.",

    Stage.WAIT_COUNTRY:
        "한국에서 온 것을 표현해 보세요.",

    Stage.FOOD_QUESTION_1:
        "루카에게 궁금한 것을 물어보세요.",

    Stage.FOOD_ANSWER_1:
        "루카의 질문에 네 또는 아니요로 답해 보세요.",

    Stage.FOOD_QUESTION_2:
        "루카에게 또 궁금한 것을 물어보세요.",

    Stage.FOOD_ANSWER_2:
        "루카의 질문에 네 또는 아니요로 답해 보세요.",

    Stage.FOOD_QUESTION_3:
        "루카에게 마지막으로 궁금한 것을 물어보세요.",

    Stage.FOOD_ANSWER_3:
        "루카의 질문에 네 또는 아니요로 답해 보세요.",

    Stage.FREE_CHAT:
        (
            "루카에게 더 궁금한 것이 있나요? "
            "없다면 'No, thank you.'라고 말해 보세요."
        ),

    Stage.END:
        "",
}


# =========================================================
# 5. 음식 대화 설정
# =========================================================

# 학생이 수행해야 하는 음식 질문 횟수
FOOD_ROUND_COUNT = 3

# 캐릭터가 학생에게 되물을 때 기본적으로 사용할 음식
#
# 예:
# Yes, I do.
# I like pizza.
# Do you like pizza?
CHARACTER_FAVORITE_FOOD = "pizza"

# 각 음식 대화가 끝난 뒤 사용할 질문
FOOD_ROUND_CLOSING_MESSAGES = {
    1: "Any questions?",
    2: "Any other questions?",
    3: "Do you have more questions?",
}


# =========================================================
# 6. 캐릭터의 Yes/No 응답 방식
# =========================================================

# True:
# data/answer_patterns.json에서 패턴 하나를 무작위로 선택합니다.
#
# False:
# FIXED_ANSWER_PATTERN을 항상 사용합니다.
USE_RANDOM_ANSWER_PATTERN = True

# USE_RANDOM_ANSWER_PATTERN이 False일 때 사용하는 고정 패턴
#
# 음식 질문이 세 번이므로 값도 세 개여야 합니다.
# 필요에 따라 순서를 직접 바꿀 수 있습니다.
FIXED_ANSWER_PATTERN = ["yes", "no", "yes"]


# =========================================================
# 7. GPT 설정
# =========================================================

# 사용하려는 OpenAI 모델
MODEL_NAME = "gpt-4o-mini"

# 답변의 창의성 정도
# 낮을수록 짧고 일정한 답변을 만드는 데 유리합니다.
TEMPERATURE = 0.3

# GPT가 한 번에 생성할 최대 토큰 수
MAX_RESPONSE_TOKENS = 120

# 자유 대화에서 한 번에 말할 최대 문장 수
MAX_FREE_CHAT_SENTENCES = 2


# =========================================================
# 8. 학생 수준과 GPT 응답 원칙
# =========================================================

STUDENT_LEVEL = {
    "grade": 3,
    "cefr": "A1",
    "native_language": "Korean",
}

GPT_RESPONSE_RULES = {
    # GPT가 학생에게 보내는 답변에는 한국어를 사용하지 않음
    "english_only": True,

    # 짧고 쉬운 문장 사용
    "use_short_sentences": True,

    # 초등학교 3학년 수준의 어휘 사용
    "use_beginner_vocabulary": True,

    # 이모지 사용 여부
    "allow_emojis": False,
}


# =========================================================
# 9. 입력 및 대화 제한
# =========================================================

# 빈 입력을 허용하지 않음
ALLOW_EMPTY_INPUT = False

# 학생이 한 번에 입력할 수 있는 최대 글자 수
MAX_USER_INPUT_LENGTH = 300

# 자유 대화가 너무 길어지는 것을 막기 위한 최대 횟수
MAX_FREE_CHAT_TURNS = 5
