import os
import json
import re
import traceback
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai

app = Flask(__name__, static_folder='.', static_url_path='')
app.secret_key = os.urandom(24)
CORS(app)

# ═══════════════════════════════════════════════════════════════
# ✏️  나라별 챗봇 설정 — 이 블록만 바꾸면 다른 나라 챗봇 완성!
# ═══════════════════════════════════════════════════════════════

# 캐릭터 기본 정보
CHARACTER_NAME    = "Luca"          # 챗봇 이름
CHARACTER_COUNTRY = "Italy"         # 출신 나라 (영어)
CHARACTER_AGE     = 10              # 나이
CHARACTER_GENDER  = "boy"           # boy / girl

# 스몰톡 — 나라 확인 후 첫 핵심 질문
FOOD_QUESTION_1   = "Do you like Kimbap?"        # 루카가 먼저 묻는 한국 음식
FOOD_KEYWORD_1    = ["kimbap", "kim bap"]        # 위 질문의 키워드 (판정용, 필요 시)

# 핵심 질문 1: 학생이 루카에게 물어봐야 하는 것
ASK_FOOD_1        = "pizza"                      # 학생이 물어볼 음식 키워드
ASK_FOOD_1_KO     = "피자"                       # 팝업에 표시할 한국어
LUCA_ANSWER_1     = "Yes, I do. I like pizza!"   # 루카의 대답

# 핵심 질문 2: 학생이 루카에게 물어봐야 하는 것
ASK_FOOD_2        = "ice"                        # 학생이 물어볼 음식 키워드 ('ice cream'의 일부)
ASK_FOOD_2_ALT    = "cream"                      # 보조 키워드
ASK_FOOD_2_KO     = "아이스크림"                  # 팝업에 표시할 한국어
LUCA_ANSWER_2     = "No, I don't. I don't like ice cream. How about you? Do you like ice cream?"

# 구글 시트 ID (나라별로 다른 시트 사용 가능)
SPREADSHEET_ID    = "1GrSDc23pBeeLZnEh3oeQwjEcOIAxH-cZPDBYPr8c3oY"
SHEET_TAB         = "Sheet1"   # 시트 탭 이름 (기본값 Sheet1)

# ═══════════════════════════════════════════════════════════════
# 여기서부터는 공통 코드 — 수정 불필요
# ═══════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────
# 🔑 Gemini API 설정
# ─────────────────────────────────────────────────────────────
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
else:
    print("⚠️  GEMINI_API_KEY 없음")

def make_model(system_instruction=None):
    kwargs = {"model_name": "gemini-2.5-flash"}
    if system_instruction:
        kwargs["system_instruction"] = system_instruction
    return genai.GenerativeModel(**kwargs)

# ─────────────────────────────────────────────────────────────
# 📊 구글 스프레드시트 연동
# ─────────────────────────────────────────────────────────────
sheet = None
try:
    raw_creds = os.environ.get("GOOGLE_SERVICE_ACCOUNT")
    if not raw_creds:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT 없음")
    service_account_info = json.loads(raw_creds)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
    gc    = gspread.authorize(creds)
    sheet = gc.open_by_key(SPREADSHEET_ID).worksheet(SHEET_TAB)
    print(f"✅ 구글 시트 연동 성공: {service_account_info.get('client_email')}")
except Exception as e:
    print(f"❌ 구글 시트 연동 실패: {e}")
    sheet = None

# ─────────────────────────────────────────────────────────────
# 🌍 캐릭터 페르소나 (설정 블록 값으로 자동 생성)
# ─────────────────────────────────────────────────────────────
BASE_PERSONA = f"""
You are {CHARACTER_NAME}, a cheerful {CHARACTER_AGE}-year-old {CHARACTER_GENDER} from {CHARACTER_COUNTRY}.
You are talking with a Korean 3rd-grade student who is a complete English beginner (CEFR A1).

STRICT RULES — never break these:
1. Reply in 1-2 short, complete sentences ONLY. Never leave a sentence unfinished.
2. Use only the simplest English words: colors, animals, food, feelings, numbers, school items.
3. NO emojis, NO emoticons, NO special symbols. Plain text only (TTS reads this aloud).
4. Be warm, encouraging, and patient. Even a one-word answer from the student is fine.
5. If the student says only one word, accept it and continue naturally.
6. If the student says "I don't know", give a gentle hint or move on with a simple answer.
7. Always finish your sentence completely. Never cut off mid-sentence.
"""

# ─────────────────────────────────────────────────────────────
# 🛠️  공통 유틸리티
# ─────────────────────────────────────────────────────────────
EMOJI_PATTERN = re.compile(
    "[" "\U0001F1E6-\U0001F1FF" "\U0001F300-\U0001FAFF"
    "\u2600-\u27BF" "\u2B00-\u2BFF" "]+", flags=re.UNICODE
)

def strip_emoji(text):
    return EMOJI_PATTERN.sub('', text or '').strip()

def call_gemini(prompt, max_tokens=80):
    """Gemini로 자유 응답 1~2문장 생성."""
    if not GEMINI_KEY:
        return ""
    try:
        model  = make_model(BASE_PERSONA)
        config = genai.types.GenerationConfig(
            max_output_tokens=max_tokens,
            temperature=0.7,
        )
        response = model.generate_content(prompt, generation_config=config)
        raw = strip_emoji(response.text.strip())
        # 문장이 잘리면 마침표 추가
        if raw and raw[-1] not in ".!?":
            raw += "."
        return raw
    except Exception as e:
        print(f"Gemini 에러: {e}")
        return ""

def has_yes(t):
    return any(w in t for w in ['yes', 'i do', 'yep', 'yeah', 'sure', 'of course', 'good', 'great'])

def has_no(t):
    return any(w in t for w in ['no', "don't", 'dont', 'nope', 'not really', 'nah'])

def judge_keyword(t, *keywords):
    """키워드 중 하나라도 포함되면 True."""
    return any(kw in t for kw in keywords)

# ─────────────────────────────────────────────────────────────
# 🌐 라우트
# ─────────────────────────────────────────────────────────────
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    data         = request.get_json(force=True, silent=True) or {}
    student_info = data.get('student', 'Unknown')
    user_message = (data.get('message') or '').strip()
    stage        = (data.get('stage')   or 'await_greeting').strip()

    # 대화 히스토리 (세션 유지)
    if 'chat_history' not in session:
        session['chat_history'] = []
    history = session['chat_history']
    history.append({"role": "user", "content": user_message})

    reply      = ""
    popup      = None
    next_stage = stage
    fireworks  = False

    if not GEMINI_KEY:
        reply = "Sorry, I cannot talk right now. Please ask your teacher."
        return _respond(reply, popup, next_stage, fireworks, student_info, user_message, history)

    try:
        t = user_message.lower()

        # ════════════════════════════════════════════════════
        # STAGE 1 : 인사 — 학생: Hi / Hello
        # ════════════════════════════════════════════════════
        if stage == 'await_greeting':
            greet_words = ['hi', 'hello', 'hey', 'nice to meet', 'good morning', 'good afternoon']
            if any(w in t for w in greet_words):
                reply      = f"Oh, hi! Nice to meet you. How are you?"
                next_stage = 'await_feeling'
                popup      = "오늘의 기분을 영어로 표현해보세요."
            else:
                reply      = f"Hi! Can you say hello to me?"
                next_stage = 'await_greeting'
                popup      = f"{CHARACTER_NAME}에게 인사를 영어로 해주세요."

        # ════════════════════════════════════════════════════
        # STAGE 2 : 기분 — 학생: I'm happy / Good 등
        # ════════════════════════════════════════════════════
        elif stage == 'await_feeling':
            # 모르면 바로 넘어가기
            if judge_keyword(t, "don't know", "idk", "모르", "몰라"):
                feeling_reply = "Okay!"
            else:
                feeling_reply = call_gemini(
                    f'The student answered "How are you?" with: "{user_message}". '
                    f'React warmly in ONE short sentence using their feeling word. '
                    f'Do NOT ask another question.'
                ) or "Oh, great!"
            reply      = f"{feeling_reply} I am from {CHARACTER_COUNTRY}. Where are you from?"
            next_stage = 'await_country'
            popup      = "'한국'을 영어로 말해보세요."

        # ════════════════════════════════════════════════════
        # STAGE 3 : 나라 — 학생: Korea
        # ════════════════════════════════════════════════════
        elif stage == 'await_country':
            if judge_keyword(t, 'korea', 'korean', 'south korea'):
                reply      = f"Oh! You are Korean. {FOOD_QUESTION_1}"
                next_stage = 'await_food1_answer'
                popup      = "네 또는 아니오로 답해보세요."
            elif judge_keyword(t, "don't know", "idk", "모르", "몰라"):
                # 모르면 힌트 주고 바로 넘어가기
                reply      = f"That's okay! I am from {CHARACTER_COUNTRY}. {FOOD_QUESTION_1}"
                next_stage = 'await_food1_answer'
                popup      = "네 또는 아니오로 답해보세요."
            else:
                reply      = "Hmm, try to say the name of your country in English!"
                next_stage = 'await_country'
                popup      = "'한국'을 영어로 말해보세요."

        # ════════════════════════════════════════════════════
        # STAGE 4 : 음식1 Yes/No — 예: Do you like Kimbap?
        # ════════════════════════════════════════════════════
        elif stage == 'await_food1_answer':
            if has_yes(t):
                reply = f"Great! Now ask me a question!"
            elif has_no(t):
                reply = f"Oh, okay! Now ask me a question!"
            elif judge_keyword(t, "don't know", "idk", "모르", "몰라"):
                reply = f"That's fine! Now ask me a question!"
            else:
                reply      = f"Hmm, you can just say Yes or No!"
                next_stage = 'await_food1_answer'
                popup      = "네 또는 아니오로 답해보세요."
                return _respond(reply, popup, next_stage, fireworks, student_info, user_message, history)
            next_stage = 'await_ask_food1'
            popup      = f"{ASK_FOOD_1_KO}를 좋아하는지 영어로 물어보세요."

        # ════════════════════════════════════════════════════
        # STAGE 5 : 학생이 루카에게 음식1 질문
        #           예: Do you like pizza?
        # ════════════════════════════════════════════════════
        elif stage == 'await_ask_food1':
            if judge_keyword(t, ASK_FOOD_1):
                reply      = LUCA_ANSWER_1
                next_stage = 'await_ask_food2'
                popup      = f"{ASK_FOOD_2_KO}를 좋아하는지 영어로 물어보세요."
            else:
                reply      = f"Hmm, try asking me: Do you like {ASK_FOOD_1}?"
                next_stage = 'await_ask_food1'
                popup      = f"{ASK_FOOD_1_KO}를 좋아하는지 영어로 물어보세요."

        # ════════════════════════════════════════════════════
        # STAGE 6 : 학생이 루카에게 음식2 질문
        #           예: Do you like ice cream?
        # ════════════════════════════════════════════════════
        elif stage == 'await_ask_food2':
            if judge_keyword(t, ASK_FOOD_2, ASK_FOOD_2_ALT):
                reply      = LUCA_ANSWER_2
                next_stage = 'await_food2_answer'
                popup      = "네 또는 아니오로 답해보세요."
            else:
                reply      = f"Hmm, try asking me: Do you like {ASK_FOOD_2_KO} in English?"
                next_stage = 'await_ask_food2'
                popup      = f"{ASK_FOOD_2_KO}를 좋아하는지 영어로 물어보세요."

        # ════════════════════════════════════════════════════
        # STAGE 7 : 음식2 답변 — Yes / No
        # ════════════════════════════════════════════════════
        elif stage == 'await_food2_answer':
            if has_yes(t):
                reaction = f"Oh, you like {ASK_FOOD_2_KO}!"
            elif has_no(t):
                reaction = f"Oh, you don't like {ASK_FOOD_2_KO} either!"
            else:
                reaction = call_gemini(
                    f'Student replied to a yes/no question about {ASK_FOOD_2_KO} with: "{user_message}". '
                    f'React warmly in ONE short sentence.'
                ) or "I see!"
            reply      = f"{reaction} Do you have any questions?"
            next_stage = 'free_talk'
            popup      = "자유롭게 원하는 질문을 해보세요. 질문이 없다면 No, thank you. 라고 말해주세요."

        # ════════════════════════════════════════════════════
        # STAGE 8 : 자유 대화 (반복) — No → 종료 + 폭죽
        # ════════════════════════════════════════════════════
        elif stage == 'free_talk':
            no_phrases = ['no thank', 'no, thank', 'no thanks', 'nope', '없어', '없음', '아니']
            is_no = any(p in t for p in no_phrases) or re.fullmatch(r'no[.!]?', t.strip())
            if is_no:
                reply      = f"Okay! It was a nice talk. Good bye!"
                next_stage = 'done'
                popup      = None
                fireworks  = True
            else:
                answer = call_gemini(
                    f'A Korean 3rd-grade student asked {CHARACTER_NAME} from {CHARACTER_COUNTRY}: "{user_message}". '
                    f'Answer in 1-2 short, complete sentences at A1 English level. '
                    f'Use only very simple words. Then ask: Do you have any questions?',
                    max_tokens=100
                ) or "That is a great question! Do you have any questions?"
                # Gemini가 "Do you have any questions?"를 안 붙이면 강제 추가
                if "any questions" not in answer.lower():
                    answer = f"{answer} Do you have any questions?"
                reply      = answer
                next_stage = 'free_talk'
                popup      = "자유롭게 원하는 질문을 해보세요. 질문이 없다면 No, thank you. 라고 말해주세요."

        # ════════════════════════════════════════════════════
        # STAGE 9 : 대화 종료 후
        # ════════════════════════════════════════════════════
        else:
            reply      = f"Okay! It was a nice talk. Good bye!"
            next_stage = 'done'
            fireworks  = True

    except Exception as e:
        print(f"❌ 에러: {e}")
        traceback.print_exc()
        reply      = "I am a little shy today. Can you say that again?"
        next_stage = stage

    return _respond(reply, popup, next_stage, fireworks, student_info, user_message, history)


# ─────────────────────────────────────────────────────────────
# 📦 공통 응답 함수 (구글 시트 저장 포함)
# ─────────────────────────────────────────────────────────────
def _respond(reply, popup, next_stage, fireworks, student_info, user_message, history):
    # 히스토리에 어시스턴트 응답 추가
    history.append({"role": "assistant", "content": reply})
    session['chat_history'] = history[-20:]   # 최근 20턴만 유지

    # 구글 시트 기록
    if sheet:
        try:
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            sheet.append_row([now, student_info, user_message, reply, next_stage])
        except Exception as e:
            print(f"시트 저장 실패: {e}")
    else:
        print("⚠️  구글 시트 미연결 - 기록 생략")

    return jsonify({
        'reply'    : reply,
        'popup'    : popup,
        'stage'    : next_stage,
        'fireworks': fireworks,
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
