import os
import json
import re
import traceback
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

# ─────────────────────────────────────────────────────────────
# 🔑 Gemini API 설정
# ─────────────────────────────────────────────────────────────
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
else:
    print("⚠️ GEMINI_API_KEY 없음")

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
    gc = gspread.authorize(creds)
    SPREADSHEET_ID = "1GrSDc23pBeeLZnEh3oeQwjEcOIAxH-cZPDBYPr8c3oY"
    sheet = gc.open_by_key(SPREADSHEET_ID).sheet1
    print(f"✅ 구글 시트 연동 성공: {service_account_info.get('client_email')}")
except Exception as e:
    print(f"❌ 구글 시트 연동 실패: {e}")
    sheet = None

# ─────────────────────────────────────────────────────────────
# 🇮🇹 페르소나
# ─────────────────────────────────────────────────────────────
BASE_PERSONA = """
You are Luca, a cheerful 10-year-old Italian boy chatting with a Korean 3rd-grade student
who is a complete English beginner (CEFR A1).

STRICT RULES — never break these:
1. Reply in EXACTLY 1 complete sentence. Never start a new sentence you cannot finish.
2. Use only the simplest words: colors, animals, food, feelings, numbers, school items.
3. NO emojis, NO emoticons, NO special symbols. Plain text only (TTS reads this aloud).
4. Be warm and encouraging. Short answers from students are perfectly fine.
5. NEVER cut off mid-sentence. If unsure, say something simple and complete.
"""

EMOJI_PATTERN = re.compile(
    "[" "\U0001F1E6-\U0001F1FF" "\U0001F300-\U0001FAFF"
    "\u2600-\u27BF" "\u2B00-\u2BFF" "]+", flags=re.UNICODE
)

def strip_emoji(text):
    return EMOJI_PATTERN.sub('', text or '').strip()

def call_gemini(prompt, max_tokens=60):
    """완전한 문장 1개를 반드시 반환."""
    if not GEMINI_KEY:
        return ""
    try:
        model = make_model(BASE_PERSONA)
        config = genai.types.GenerationConfig(
            max_output_tokens=max_tokens,
            temperature=0.7,
            stop_sequences=[".", "!", "?"]   # 첫 문장 끝에서 멈춤
        )
        response = model.generate_content(prompt, generation_config=config)
        raw = strip_emoji(response.text.strip())
        # 문장 끝 부호가 없으면 붙여주기
        if raw and raw[-1] not in ".!?":
            raw += "."
        return raw
    except Exception as e:
        print(f"Gemini 에러: {e}")
        return ""

def judge_pizza(t):
    """피자 질문 판정 - 키워드 기반 (AI 불필요)"""
    return 'pizza' in t

def judge_icecream(t):
    """아이스크림 질문 판정 - 키워드 기반 (AI 불필요)"""
    return 'ice' in t or 'cream' in t or 'icecream' in t

def has_yes(t):
    return any(w in t for w in ['yes', 'i do', 'yep', 'yeah', 'sure', 'of course'])

def has_no(t):
    return any(w in t for w in ['no', "don't", 'dont', 'nope', 'not really', 'nah'])

# ─────────────────────────────────────────────────────────────
# 라우트
# ─────────────────────────────────────────────────────────────
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json(force=True, silent=True) or {}
    student_info = data.get('student', 'Unknown')
    user_message  = (data.get('message') or '').strip()
    stage         = (data.get('stage') or 'await_greeting').strip()

    reply      = ""
    popup      = None
    next_stage = stage
    fireworks  = False   # 🎆 폭죽 신호

    if not GEMINI_KEY:
        reply = "Sorry, I cannot talk right now. Please ask your teacher."
        return jsonify({'reply': reply, 'popup': popup, 'stage': next_stage, 'fireworks': fireworks})

    try:
        t = user_message.lower()

        # ════════════════════════════════════════════════════
        # 1) 인사 단계 — 학생: Hi / Hello
        # ════════════════════════════════════════════════════
        if stage == 'await_greeting':
            greet_words = ['hi', 'hello', 'hey', 'nice to meet', 'good morning', 'good afternoon']
            if any(w in t for w in greet_words):
                reply      = "Oh, hi! Nice to meet you. How are you?"
                next_stage = 'await_feeling'
                popup      = "오늘의 기분을 영어로 표현해보세요."
            else:
                reply      = "Hi! Can you say hello to me?"
                next_stage = 'await_greeting'
                popup      = "루카에게 인사를 영어로 해주세요."

        # ════════════════════════════════════════════════════
        # 2) 기분 단계 — 학생: I'm happy / Good 등 자유응답
        # ════════════════════════════════════════════════════
        elif stage == 'await_feeling':
            feeling_reply = call_gemini(
                f'The student answered "How are you?" with: "{user_message}". '
                f'React warmly in ONE complete sentence using their feeling word. '
                f'End your sentence. Do NOT ask a new question.'
            ) or "Oh, great!"
            reply      = f"{feeling_reply} I am from Italy. Where are you from?"
            next_stage = 'await_country'
            popup      = "'한국'을 영어로 말해보세요."

        # ════════════════════════════════════════════════════
        # 3) 나라 단계 — 학생: Korea
        # ════════════════════════════════════════════════════
        elif stage == 'await_country':
            if 'korea' in t or 'korean' in t or 'south korea' in t:
                reply      = "Oh! You are Korean. Do you like Kimbap?"
                next_stage = 'await_kimbap_answer'
                popup      = "네 또는 아니오로 답해보세요."
            else:
                reply      = "Hmm, try to say the name of your country in English!"
                next_stage = 'await_country'
                popup      = "'한국'을 영어로 말해보세요."

        # ════════════════════════════════════════════════════
        # 4) 김밥 답변 — Yes / No
        # ════════════════════════════════════════════════════
        elif stage == 'await_kimbap_answer':
            if has_yes(t):
                reply = "Great! Now ask me a question!"
            elif has_no(t):
                reply = "Oh, okay! Now ask me a question!"
            else:
                reply      = "Hmm, do you like Kimbap? You can say Yes or No!"
                next_stage = 'await_kimbap_answer'
                popup      = "네 또는 아니오로 답해보세요."
                return _respond(reply, popup, next_stage, fireworks, student_info, user_message)
            next_stage = 'await_pizza_question'
            popup      = "피자를 좋아하는지 영어로 물어보세요."

        # ════════════════════════════════════════════════════
        # 5) 피자 질문 — 학생: Do you like pizza?
        # ════════════════════════════════════════════════════
        elif stage == 'await_pizza_question':
            if judge_pizza(t):
                reply      = "Yes, I do. I like pizza!"
                next_stage = 'await_icecream_question'
                popup      = "아이스크림을 좋아하는지 영어로 물어보세요."
            else:
                reply      = "Hmm, try asking me: Do you like pizza?"
                next_stage = 'await_pizza_question'
                popup      = "피자를 좋아하는지 영어로 물어보세요."

        # ════════════════════════════════════════════════════
        # 6) 아이스크림 질문 — 학생: Do you like ice cream?
        # ════════════════════════════════════════════════════
        elif stage == 'await_icecream_question':
            if judge_icecream(t):
                reply      = "No, I don't. I don't like ice cream. How about you? Do you like ice cream?"
                next_stage = 'await_icecream_answer'
                popup      = "네 또는 아니오로 답해보세요."
            else:
                reply      = "Hmm, try asking me: Do you like ice cream?"
                next_stage = 'await_icecream_question'
                popup      = "아이스크림을 좋아하는지 영어로 물어보세요."

        # ════════════════════════════════════════════════════
        # 7) 아이스크림 답변 — Yes / No
        # ════════════════════════════════════════════════════
        elif stage == 'await_icecream_answer':
            if has_yes(t):
                ice_reply = "Oh, you like ice cream!"
            elif has_no(t):
                ice_reply = "Oh, you don't like ice cream either!"
            else:
                ice_reply = call_gemini(
                    f'Student replied to "Do you like ice cream?" with: "{user_message}". '
                    f'React warmly in ONE complete sentence.'
                ) or "I see!"
            reply      = f"{ice_reply} Do you have any questions?"
            next_stage = 'free_talk'
            popup      = "자유롭게 원하는 질문을 해보세요. 질문이 없다면 No, thank you. 라고 말해주세요."

        # ════════════════════════════════════════════════════
        # 8) 자유 대화 — 반복. No → 종료 + 폭죽
        # ════════════════════════════════════════════════════
        elif stage == 'free_talk':
            no_phrases = ['no thank', 'no, thank', 'no thanks', 'nope', '없어', '없음', '아니']
            # "no" 단독 (앞뒤 단어 없이)
            is_no = any(p in t for p in no_phrases) or re.fullmatch(r'no[.!]?', t.strip())
            if is_no:
                reply      = "Okay! It was a nice talk. Good bye!"
                next_stage = 'done'
                popup      = None
                fireworks  = True
            else:
                answer = call_gemini(
                    f'A Korean 3rd-grade student asked Luca: "{user_message}". '
                    f'Answer in ONE complete, simple sentence (A1 level). '
                    f'Use only basic words. Finish the sentence completely.',
                    max_tokens=80
                ) or "That is a great question!"
                reply      = f"{answer} Do you have any questions?"
                next_stage = 'free_talk'
                popup      = "자유롭게 원하는 질문을 해보세요. 질문이 없다면 No, thank you. 라고 말해주세요."

        # ════════════════════════════════════════════════════
        # 9) 종료 후
        # ════════════════════════════════════════════════════
        else:
            reply      = "Okay! It was a nice talk. Good bye!"
            next_stage = 'done'
            fireworks  = True

    except Exception as e:
        print(f"❌ 에러: {e}")
        traceback.print_exc()
        reply      = "I am a little shy today. Can you say that again?"
        next_stage = stage

    return _respond(reply, popup, next_stage, fireworks, student_info, user_message)


def _respond(reply, popup, next_stage, fireworks, student_info, user_message):
    if sheet:
        try:
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            sheet.append_row([now, student_info, user_message, reply, next_stage])
        except Exception as e:
            print(f"시트 저장 실패: {e}")
    return jsonify({'reply': reply, 'popup': popup, 'stage': next_stage, 'fireworks': fireworks})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
