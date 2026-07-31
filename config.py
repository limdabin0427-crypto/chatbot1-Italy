"""
config.py

AI English Chatbot 프로젝트의 공통 설정을 관리합니다.

이 파일은 백엔드와 프론트엔드에서 함께 사용할
기본 설정을 한곳에 모아 둡니다.

이 파일에서 관리하는 내용:

1. 프로젝트 폴더와 데이터 파일 위치
2. 현재 사용할 챗봇 지역
3. OpenAI 모델 설정
4. 학생 수준과 답변 원칙
5. 음성 인식과 음성 출력 설정
6. 입력 및 대화 안전장치
7. 구글 스프레드시트 설정
8. 프론트엔드 화면 설정

캐릭터의 이름, 나라, 성별, 이미지, 인사말 등은
data/characters.json에서 관리합니다.

음식 이름과 여러 발음·표현은
data/foods.json에서 관리합니다.

나라별 고정 음식 선호는
data/answer_patterns.json에서 관리합니다.
"""

from enum import Enum
from pathlib import Path


# =========================================================
# 1. 프로젝트 폴더와 파일 위치
# =========================================================

# config.py가 있는 프로젝트 최상위 폴더
BASE_DIR = Path(__file__).resolve().parent

# JSON 데이터 파일을 저장할 폴더
DATA_DIR = BASE_DIR / "data"

# HTML 파일을 저장할 폴더
TEMPLATES_DIR = BASE_DIR / "templates"

# 이미지와 GIF 파일을 저장할 폴더
STATIC_DIR = BASE_DIR / "static"


# JSON 데이터 파일
CHARACTERS_FILE = DATA_DIR / "characters.json"
FOODS_FILE = DATA_DIR / "foods.json"
ANSWER_PATTERNS_FILE = DATA_DIR / "answer_patterns.json"


# =========================================================
# 2. 현재 사용할 챗봇
# =========================================================

# 현재 실행할 챗봇의 지역 이름입니다.
#
# characters.json과 answer_patterns.json에 있는 이름과
# 정확히 같아야 합니다.
#
# 현재 사용할 예정인 값:
# Italy
# America
# Mexico
# Hawaii

CHATBOT_ID = "Italy"


# =========================================================
# 3. 대화 단계
# =========================================================

class Stage(str, Enum):
    """
    학생이 현재 어느 대화 단계에 있는지를 나타냅니다.

    음식 질문 횟수는 단계로 나누지 않습니다.
    학생은 자유 대화 단계에서 여러 음식을 묻거나
    다른 열린 질문을 할 수 있습니다.
    """

    # 챗봇의 첫인사가 끝난 뒤
    # 학생의 인사를 기다리는 단계
    WAIT_GREETING = "WAIT_GREETING"

    # 학생의 기분 표현을 기다리는 단계
    WAIT_FEELING = "WAIT_FEELING"

    # 학생이 챗봇에게 자유롭게 질문하는 단계
    FREE_CHAT = "FREE_CHAT"

    # 대화가 종료된 단계
    END = "END"


# 처음 대화를 시작할 때의 단계
INITIAL_STAGE = Stage.WAIT_GREETING


# =========================================================
# 4. OpenAI 설정
# =========================================================

# 사용할 OpenAI API 모델
MODEL_NAME = "gpt-4o-mini"

# 답변의 창의성 정도
#
# 값이 낮을수록 답변 표현이 더 일정해집니다.
# 수업용 챗봇이므로 비교적 낮게 설정합니다.
TEMPERATURE = 0.3

# GPT가 한 번에 생성할 수 있는 최대 토큰 수
MAX_RESPONSE_TOKENS = 120

# GPT의 일반 답변은 최대 두 문장으로 제한
MAX_RESPONSE_SENTENCES = 2


# =========================================================
# 5. 학생 수준
# =========================================================

STUDENT_LEVEL = {
    # 대상 학년
    "grade": 3,

    # 영어 숙달도
    "cefr": "A1",

    # 학생의 모국어
    "native_language": "Korean",
}


# =========================================================
# 6. GPT 답변 원칙
# =========================================================

GPT_RESPONSE_RULES = {
    # 챗봇의 답변은 영어로만 제공
    "english_only": True,

    # 초등학생이 이해하기 쉬운 짧은 문장 사용
    "use_short_sentences": True,

    # 초급 수준의 쉬운 단어 사용
    "use_beginner_vocabulary": True,

    # 문법을 길게 설명하지 않음
    "do_not_explain_grammar": True,

    # 선택한 캐릭터의 설정을 유지
    "stay_in_character": True,

    # TTS가 자연스럽게 읽도록 이모지를 사용하지 않음
    "allow_emojis": False,

    # 한 번에 두 가지 질문을 하지 않음
    "ask_only_one_question_at_a_time": True,

    # 학생의 한 단어 답변도 받아들임
    "accept_one_word_answers": True,

    # 한국어 또는 한영 혼합 입력의 의도는 이해하되
    # 답변은 영어로 제공
    "understand_mixed_language": True,
}


# =========================================================
# 7. 음식 질문 처리 원칙
# =========================================================

# 학생이 질문할 수 있는 음식 개수는 제한하지 않습니다.
LIMIT_FOOD_QUESTION_COUNT = False

# 학생이 "Do you like pizza?"처럼 물으면
# answer_patterns.json의 고정값을 우선 사용합니다.
USE_FIXED_FOOD_PREFERENCES = True

# 고정 음식에 대한 답변은 반드시
# Yes 또는 No로 시작하게 합니다.
FIXED_FOOD_ANSWER_STARTS_WITH_YES_OR_NO = True

# answer_patterns.json에 없는 음식을 질문했을 때
# GPT가 캐릭터에 맞춰 자연스럽게 답하는 것을 허용합니다.
ALLOW_UNLISTED_FOOD_QUESTIONS = True

# "What is your favorite food?"와 같은
# 열린 음식 질문도 허용합니다.
ALLOW_OPEN_FOOD_QUESTIONS = True

# 음식 이외의 일상적인 질문도 허용합니다.
ALLOW_GENERAL_QUESTIONS = True


# =========================================================
# 8. 대화 종료 설정
# =========================================================

# 학생이 다음과 같은 표현을 사용하면
# 대화를 끝내려는 것으로 판단합니다.
ENDING_EXPRESSIONS = [
    "bye",
    "goodbye",
    "see you",
    "no thank you",
    "no, thank you",
    "no thanks",
    "that's all",
    "that is all",
]


# 대화 종료 시 화면의 피날레 효과 사용 여부
SHOW_FINALE_EFFECT = True


# =========================================================
# 9. 학생 입력 제한
# =========================================================

# 빈 입력을 허용하지 않음
ALLOW_EMPTY_INPUT = False

# 학생이 한 번에 입력할 수 있는 최대 글자 수
MAX_USER_INPUT_LENGTH = 300

# 세션에 보관할 최근 대화 메시지 개수
MAX_HISTORY_MESSAGES = 30

# 전체 자유 질문 횟수는 제한하지 않음
MAX_FREE_CHAT_TURNS = None


# =========================================================
# 10. 음성 인식 설정
# =========================================================

SPEECH_RECOGNITION = {
    # 학생의 음성을 영어로 인식
    "language": "en-US",

    # 말하는 중간 결과는 사용하지 않음
    "interim_results": False,

    # 가장 가능성이 높은 인식 결과 하나만 사용
    "max_alternatives": 1,
}


# =========================================================
# 11. 음성 출력 설정
# =========================================================

TEXT_TO_SPEECH = {
    # 영어 음성 사용
    "language": "en-US",

    # 어린이처럼 들리도록 음높이를 조금 높임
    "child_mode": True,

    # 기본 말하기 속도
    "rate": 0.85,

    # child_mode에서 사용할 음높이
    "child_pitch": 1.35,
}


# =========================================================
# 12. 프론트엔드 화면 설정
# =========================================================

FRONTEND = {
    # 브라우저 탭의 기본 제목
    "page_title": "Let's Meet New Friends!",

    # 로그인 화면의 영어 제목
    "login_title": "Let's meet new friends!",

    # 로그인 화면의 영어 설명
    "login_subtitle": "Enter your number and name.",

    # 로그인 화면의 한국어 설명
    "login_help": "번호와 이름을 입력하세요.",

    # 로그인 입력 예시
    "login_placeholder": "예: 01 홍길동",

    # 로그인 버튼 문구
    "login_button": "Let's Go!",

    # 마이크 사용 전 기본 안내
    "ready_hint": "마이크 버튼을 누르고 영어로 말해보세요.",

    # 음성 인식 중 안내
    "listening_hint": "Listening... 듣고 있어요.",

    # 대화 종료 후 안내
    "finished_hint": "수고했어요!",
}


# =========================================================
# 13. 구글 스프레드시트 설정
# =========================================================

# 학생의 대화 기록을 구글 스프레드시트에 저장할지 결정
ENABLE_GOOGLE_SHEETS = True

# 현재 프로젝트에서 사용 중인 스프레드시트 ID
SPREADSHEET_ID = "1D1xcyBiIOtBE3QfrPMx84RVIREf-8kq5XDqTZWCrDMU"

# characters.json에 별도의 sheet_tab 값이 없을 때
# CHATBOT_ID를 탭 이름으로 사용합니다.
DEFAULT_SHEET_TAB = CHATBOT_ID

# 새 탭을 만들 때 사용할 첫 행
SHEET_HEADERS = [
    "시간",
    "학생정보",
    "학생발화",
    "챗봇응답",
    "단계",
    "지역",
]


# =========================================================
# 14. 오류 메시지
# =========================================================

ERROR_MESSAGES = {
    # OpenAI API를 사용할 수 없을 때
    "openai_unavailable":
        "Oh, I'm tired. I need some rest.",

    # 학생이 아무것도 입력하지 않았을 때
    "empty_input":
        "Please say something.",

    # 학생의 입력이 너무 길 때
    "input_too_long":
        "Please use a shorter sentence.",

    # 학생의 말을 이해하기 어려울 때
    "not_understood":
        "I'm sorry. Can you say that again?",

    # 서버 또는 데이터 오류가 발생했을 때
    "server_error":
        "Sorry, something went wrong. Please try again.",
}
