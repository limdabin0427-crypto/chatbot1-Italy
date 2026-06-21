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
from pydantic import BaseModel, Field

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

# ─────────────────────────────────────────────────────────────
# 🔑 Gemini API 설정
# ─────────────────────────────────────────────────────────────
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    text_model = genai.GenerativeModel("gemini-2.5-flash")
else:
    text_model = None
    print("⚠️ GEMINI_API_KEY 없음")

# ─────────────────────────────────────────────────────────────
# 📊 구글 스프레드시트 연동
# ─────────────────────────────────────────────────────────────
sheet = None
try:
    raw_creds = os.environ.get("GOOGLE_SERVICE_ACCOUNT")
    if not raw_creds:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT 환경변수가 비어있습니다.")
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
# 🇮🇹 루카 페르소나
# ─────────────────────────────────────────────────────────────
BASE_PERSONA = """
You are Luca, a friendly 10-year-old boy from Italy.
You are talking with a 3rd-grade elementary school student in South Korea
who just started learning English (CEFR A1 level).

Rules you must ALWAYS follow:
- Reply in 1-2 short sentences only. Never longer.
- Use only the simplest English words (colors, animals, food, feelings, school words).
- Never use emojis, emoticons, or special symbols. Plain text only.
  Your reply is read aloud by text-to-speech, so emojis sound terrible.
- Be warm, encouraging, and patient. Never criticize short answers.
- A one-word answer like "Yes", "Good", "Korea" is perfectly fine.
"""

# 이모지 제거 패턴
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"
    "\U0001F300-\U0001FAFF"
    "\u2600-\u27BF"
    "\u2B00-\u2BFF"
    "]+", flags=re.UNICODE
)

def strip_emoji(text):
    return EMOJI_PATTERN.sub('', text or '').strip()

def call_gemini_text(user_prompt, max_tokens=80):
    """자유 텍스트 1~2문장 생성."""
    if not text_model:
        return ""
    persona_model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=BASE_PERSONA
    )
    config = genai.types.GenerationConfig(max_output_tokens=max_tokens, temperature=0.7)
    response = persona_model.generate_content(user_prompt, generation_config=config)
    return strip_emoji(response.text.strip())

class EvaluationResult(BaseModel):
    outcome: str = Field(description="'matched' or 'retry'")
    reply: str = Field(description="if retry: ONE short warm English nudge (max 1 sentence); if matched: empty string")

def call_gemini_json(system_prompt, user_prompt):
    """학생 발화 판정 - JSON 구조화 출력."""
    json_model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=system_prompt
    )
    config = genai.types.GenerationConfig(
        temperature=0.3,
        response_mime_type="application/json",
        response_schema=EvaluationResult
    )
    response = json_model.generate_content(user_prompt, generation_config=config)
    return json.loads(response.text.strip())

def judge(target_desc, user_message, fallback_reply):
    """공통 판정 함수. matched/retry 반환."""
    try:
        system_prompt = (
            "You are judging a young Korean EFL beginner's spoken English attempt, "
            "transcribed by speech recognition (may have typos or odd grammar). "
            "Be very lenient: judge by intent and key words only."
        )
        user_prompt = (
            f"Target: the student should be {target_desc}.\n"
            f"Student said: \"{user_message}\"\n\n"
            "Decide:\n"
            "- \"matched\": recognizable attempt at the target, even with grammar mistakes.\n"
            "- \"retry\": clearly unrelated or unrecognizable."
        )
        return call_gemini_json(system_prompt, user_prompt)
    except Exception:
        return {"outcome": "retry", "reply": fallback_reply}

# ─────────────────────────────────────────────────────────────
# 📋 대화 흐름 정의
#
# 전체 스테이지 순서:
#   await_greeting         → 학생: Hi / Hello
#   await_feeling          → 학생: I'm happy / Good 등
#   await_country          → 학생: Korea 포함 응답
#   await_kimbap_answer    → 학생: Yes I do / No I don't
#   await_pizza_question   → 학생: Do you like pizza?
#   await_icecream_question→ 학생: Do you like ice cream?
#   await_icecream_answer  → 학생: Yes I do / No I don't
#   free_talk              → 자유 질문 (반복), No → 종료
# ─────────────────────────────────────────────────────────────

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json(force=True, silent=True) or {}
    student_info = data.get('student', 'Unknown Student')
    user_message = (data.get('message') or '').strip()
    stage = data.get('stage') or 'await_greeting'

    reply = ""
    popup = None
    next_stage = stage

    if not text_model:
        reply = "Sorry, I cannot talk right now. Please ask your teacher to check my settings."
        return jsonify({'reply': reply, 'popup': popup, 'stage': next_stage})

    try:
        t = user_message.lower()

        # ── 1. 인사 단계 ──────────────────────────────────────────
        if stage == 'await_greeting':
            # "hi", "hello", "hey" 등 인사말 감지
            greet_words = ['hi', 'hello', 'hey', 'nice to meet you', 'nice to meet']
            if any(w in t for w in greet_words):
                reply = "Oh, hi! Nice to meet you. How are you?"
                next_stage = 'await_feeling'
                popup = "오늘의 기분을 영어로 표현해보세요."
            else:
                reply = "Hi! Can you say hello to me?"
                next_stage = 'await_greeting'
                popup = "루카에게 인사를 영어로 해주세요."

        # ── 2. 기분 단계 ──────────────────────────────────────────
        elif stage == 'await_feeling':
            feedback = call_gemini_text(
                f'The student answered "How are you?" with: "{user_message}". '
                f'Write ONE warm short reaction (max 1 sentence) reflecting what they said. '
                f'Then say: I am from Italy. Where are you from?'
            )
            reply = feedback if feedback else f"Oh, great! I am from Italy. Where are you from?"
            next_stage = 'await_country'
            popup = "'한국'을 영어로 말해보세요."

        # ── 3. 나라 단계 ──────────────────────────────────────────
        elif stage == 'await_country':
            if 'korea' in t or 'korean' in t:
                reply = "Oh! You are Korean. Do you like Kimbap?"
                next_stage = 'await_kimbap_answer'
                popup = "네 또는 아니오로 답해보세요."
            else:
                reply = "Hmm, where are you from? Try to say the name of your country!"
                next_stage = 'await_country'
                popup = "'한국'을 영어로 말해보세요."

        # ── 4. 김밥 좋아해? (Yes/No 답변) ────────────────────────
        elif stage == 'await_kimbap_answer':
            yes_words = ['yes', 'i do', 'like', 'yep', 'yeah']
            no_words  = ['no', "don't", 'dont', 'nope', 'not']
            if any(w in t for w in yes_words):
                reply = "Great! Now, ask me! Do you have a question for me?"
                next_stage = 'await_pizza_question'
                popup = "피자를 좋아하는지 영어로 물어보세요."
            elif any(w in t for w in no_words):
                reply = "Oh, okay! Now, ask me! Do you have a question for me?"
                next_stage = 'await_pizza_question'
                popup = "피자를 좋아하는지 영어로 물어보세요."
            else:
                reply = "Hmm, do you like Kimbap? You can just say Yes or No!"
                next_stage = 'await_kimbap_answer'
                popup = "네 또는 아니오로 답해보세요."

        # ── 5. 피자 질문 단계 (학생이 질문) ──────────────────────
        elif stage == 'await_pizza_question':
            result = judge(
                'asking whether Luca likes pizza (e.g. "Do you like pizza?")',
                user_message,
                "Try asking: Do you like pizza?"
            )
            if result.get('outcome') == 'matched':
                reply = "Yes, I do. I like pizza!"
                next_stage = 'await_icecream_question'
                popup = "아이스크림을 좋아하는지 영어로 물어보세요."
            else:
                reply = strip_emoji(result.get('reply') or "Try asking: Do you like pizza?")
                next_stage = 'await_pizza_question'
                popup = "피자를 좋아하는지 영어로 물어보세요."

        # ── 6. 아이스크림 질문 단계 (학생이 질문) ────────────────
        elif stage == 'await_icecream_question':
            result = judge(
                'asking whether Luca likes ice cream (e.g. "Do you like ice cream?")',
                user_message,
                "Try asking: Do you like ice cream?"
            )
            if result.get('outcome') == 'matched':
                reply = "No, I don't. I don't like ice cream. How about you? Do you like ice cream?"
                next_stage = 'await_icecream_answer'
                popup = "네 또는 아니오로 답해보세요."
            else:
                reply = strip_emoji(result.get('reply') or "Try asking: Do you like ice cream?")
                next_stage = 'await_icecream_question'
                popup = "아이스크림을 좋아하는지 영어로 물어보세요."

        # ── 7. 아이스크림 답변 단계 ───────────────────────────────
        elif stage == 'await_icecream_answer':
            yes_words = ['yes', 'i do', 'like', 'yep', 'yeah']
            no_words  = ['no', "don't", 'dont', 'nope', 'not']
            if any(w in t for w in yes_words):
                feedback = "Oh, you like ice cream!"
            elif any(w in t for w in no_words):
                feedback = "Oh, you don't like ice cream either!"
            else:
                feedback = call_gemini_text(
                    f'Student answered whether they like ice cream with: "{user_message}". '
                    f'ONE warm short reaction.'
                ) or "I see!"
            reply = f"{feedback} Do you have any questions?"
            next_stage = 'free_talk'
            popup = "자유롭게 원하는 질문을 해보세요. 질문이 없다면 No, thank you. 라고 말해주세요."

        # ── 8. 자유 대화 (반복) ───────────────────────────────────
        elif stage == 'free_talk':
            no_words = ['no', 'no thank', 'no thanks', 'no, thank you', 'nope', '없어', '없음']
            if any(w in t for w in no_words):
                reply = "Okay! It was a nice talk. Good bye!"
                next_stage = 'done'
                popup = None
            else:
                answer = call_gemini_text(
                    f'A Korean 3rd grade student asked Luca: "{user_message}". '
                    f'Answer warmly and simply in 1-2 sentences at A1 English level. '
                    f'Then ask: Do you have any questions?'
                )
                reply = answer if answer else "That is a great question! Do you have any questions?"
                next_stage = 'free_talk'
                popup = "자유롭게 원하는 질문을 해보세요. 질문이 없다면 No, thank you. 라고 말해주세요."

        # ── 9. 종료 후 ────────────────────────────────────────────
        else:
            reply = "Okay! It was a nice talk. Good bye!"
            next_stage = 'done'
            popup = None

    except Exception as e:
        print(f"❌ Gemini 에러: {e}")
        traceback.print_exc()
        reply = "I am a little shy today. Can you say that again?"
        next_stage = stage

    # 📊 구글 시트 기록
    if sheet:
        try:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            sheet.append_row([current_time, student_info, user_message, reply, stage])
        except Exception as e:
            print(f"구글 시트 저장 실패: {e}")
    else:
        print("⚠️ 구글 시트 미연결 - 기록 생략")

    return jsonify({'reply': reply, 'popup': popup, 'stage': next_stage})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
