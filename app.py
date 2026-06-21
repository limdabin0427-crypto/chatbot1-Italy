import os
import json
import re
import traceback
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import gspread
from google.oauth2.service_account import Credentials

# 🔑 Google GenAI 공식 라이브러리 및 구조화 출력을 위한 Pydantic 추가
import google.generativeai as genai
from pydantic import BaseModel, Field

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

# 🔑 Render 환경변수에 등록한 Gemini API 키와 구글 키 가져오기
# (Render Dashboard -> Environment Variables에 GEMINI_API_KEY를 추가해주세요!)
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    # 일반 텍스트 대화용 기본 모델 설정
    text_model = genai.GenerativeModel("gemini-2.5-flash")
else:
    text_model = None
    print("⚠️ GEMINI_API_KEY 환경변수가 비어있습니다. AI 대화가 동작하지 않고 고정 안내 문구만 나갑니다. "
          "Render Dashboard > Environment에서 키를 정확히 등록해주세요.")

# 📊 구글 스프레드시트 연동 설정
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

    # ⚠️여기에 선생님의 구글 스프레드시트 ID(주소창 중간의 긴 문자열)를 꼭 넣어주세요!
    SPREADSHEET_ID = "1GrSDc23pBeeLZnEh3oeQwjEcOIAxH-cZPDBYPr8c3oY"
    sheet = gc.open_by_key(SPREADSHEET_ID).sheet1
    print(f"✅ 구글 시트 연동 성공. 서비스 계정: {service_account_info.get('client_email')}")
except Exception as e:
    print(f"❌ 구글 시트 연동 실패: {e}")
    traceback.print_exc()
    sheet = None

# ─────────────────────────────────────────────────────────────
# 🇮🇹 루카 페르소나 & 대화 규칙
# ─────────────────────────────────────────────────────────────
BASE_PERSONA = """
You are Luca, a friendly 10-year-old boy from Italy talking with a 3rd-grade elementary
school student in South Korea who just started learning English (CEFR A1 level, just learned the alphabet).

Always follow these rules in every reply:
- Your reply must always be just 1-2 short sentences. Never write more than that.
- Use only words a Korean 3rd grader would know (colors, animals, food, weather, school supplies, simple feelings).
- A single-word answer from the student (e.g. "Good", "Yes", "Pizza") is a complete, valid answer.
  Respond warmly and naturally - never criticize a short answer.
- Never use emojis, emoticons, or special symbols. Plain text only - your reply is read aloud by
  a text-to-speech voice, and emojis get read out as awkward English (e.g. "smiling face").
"""

# 모델이 그래도 이모지를 섞어 보낼 경우를 대비한 안전망 (루카의 대사에만 적용)
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


def looks_like_giveup(text):
    """학생이 '모르겠어요/못하겠어요' 류로 포기 의사를 밝혔는지 대략적으로 판별."""
    t = (text or '').strip().lower()
    if not t:
        return True
    giveup_phrases = [
        "i don't know", "i dont know", "idk", "i don't understand", "i dont understand",
        "i can't", "i cant", "모르겠어요", "몰라요", "모르겠어", "모름",
    ]
    return any(p in t for p in giveup_phrases)


def call_gemini_text(user_prompt, max_tokens=60):
    """자유 문장 1~2문장을 생성하는 일반 호출."""
    if not text_model:
        return ""
        
    # 페르소나를 system_instruction으로 주입하여 규칙을 강제합니다.
    persona_model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=BASE_PERSONA
    )
    
    config = genai.types.GenerationConfig(
        max_output_tokens=max_tokens,
        temperature=0.7
    )
    
    response = persona_model.generate_content(user_prompt, generation_config=config)
    return strip_emoji(response.text.strip())


# Gemini JSON 출력을 강제하기 위한 Pydantic 구조 정의
class EvaluationResult(BaseModel):
    outcome: str = Field(description="'matched' or 'retry'")
    reply: str = Field(description="if retry: ONE short warm English nudge from Luca (max 1 sentence), do NOT reveal the target sentence; if matched: empty string")


def call_gemini_json(system_prompt, user_prompt):
    """학생 발화가 목표 질문 의도와 맞는지 판정하는 구조화(JSON) 호출."""
    # JSON 평가 모델은 별도의 시스템 지침과 함께 정의합니다.
    json_model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=system_prompt
    )
    
    # response_mime_type과 response_schema를 사용하여 형식을 고정합니다.
    config = genai.types.GenerationConfig(
        temperature=0.3,
        response_mime_type="application/json",
        response_schema=EvaluationResult
    )
    
    response = json_model.generate_content(user_prompt, generation_config=config)
    raw = response.text.strip()
    return json.loads(raw)


# ─────────────────────────────────────────────────────────────
# 📋 수업 흐름 (state machine)
# ─────────────────────────────────────────────────────────────
ASK_STAGES = {
    'await_pizza_question': {
        'target_desc': 'asking whether Luca likes pizza (e.g. "Do you like pizza?")',
        'success_reply': "Yes, I do. I like pizza very much.",
        'popup': "피자를 좋아하는지 영어로 물어보세요.",
        'next_stage': 'await_icecream_question',
        'next_popup': "아이스크림을 좋아하는지 영어로 물어보세요.",
    },
    'await_icecream_question': {
        'target_desc': 'asking whether Luca likes ice cream (e.g. "Do you like ice cream?")',
        'success_reply': "No, I don't. I don't like ice cream.",
        'popup': "아이스크림을 좋아하는지 영어로 물어보세요.",
        'next_stage': 'done',
        'next_popup': None,
    },
}


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json(force=True, silent=True) or {}
    student_info = data.get('student', 'Unknown Student')
    user_message = (data.get('message') or '').strip()
    stage = data.get('stage') or 'await_feeling'

    reply = "Hi! Let's talk!"
    popup = None
    next_stage = stage

    if not text_model:
        # API 키가 비어있을 때의 안전 장치
        reply = "Sorry, I can't talk right now. Please ask your teacher to check my settings."
        next_stage = stage
    else:
        try:
            # 1) 스몰토크: "How are you?" 에 대한 답변
            if stage == 'await_feeling':
                if looks_like_giveup(user_message):
                    reply = "That's okay! Do you like Kimbap?"
                else:
                    feedback = call_gemini_text(
                        f'The student just answered "How are you?" with: "{user_message}". '
                        f'Write ONE short, warm reaction (max 1 short sentence) to what they said. '
                        f'Do not ask any question yourself.'
                    )
                    reply = f"{feedback} Do you like Kimbap?".strip()
                next_stage = 'await_kimbap_answer'

            # 2) 루카가 먼저 묻는 핵심 문장: "Do you like Kimbap?"
            elif stage == 'await_kimbap_answer':
                if looks_like_giveup(user_message):
                    reply = "That's okay! Now you ask me a question."
                else:
                    feedback = call_gemini_text(
                        f'The student just answered whether they like Kimbap with: "{user_message}". '
                        f'Write ONE short, warm reaction (max 1 short sentence). Do not ask a question.'
                    )
                    reply = f"{feedback} Now you ask me a question.".strip()
                next_stage = 'await_pizza_question'
                popup = "피자를 좋아하는지 영어로 물어보세요."

            # 3) 역할 반전 단계 (피자 / 아이스크림): 학생이 직접 질문해야 함
            elif stage in ASK_STAGES:
                cfg = ASK_STAGES[stage]
                if looks_like_giveup(user_message):
                    reply = "That's okay! Let's try the next one."
                    next_stage = cfg['next_stage']
                    popup = cfg['next_popup']
                else:
                    try:
                        system_prompt = (
                            "You are judging a young Korean EFL beginner's spoken English attempt, "
                            "transcribed by speech recognition so it may contain noise, typos, or odd grammar. "
                            "Be lenient: judge by intent and key words, not exact wording or perfect pronunciation."
                        )
                        user_prompt = (
                            f"Target: the student should be {cfg['target_desc']}.\n"
                            f"Student said (speech-to-text, possibly imperfect): \"{user_message}\"\n\n"
                            "Decide exactly one outcome:\n"
                            "- \"matched\": a reasonable, recognizable attempt at the target question, even with grammar mistakes.\n"
                            "- \"retry\": unrelated or unrecognizable, and the student has not given up."
                        )
                        result = call_gemini_json(system_prompt, user_prompt)
                    except Exception:
                        result = {"outcome": "retry", "reply": "Hmm, try asking me with 'Do you like...?'"}

                    if result.get('outcome') == 'matched':
                        reply = cfg['success_reply']
                        next_stage = cfg['next_stage']
                        popup = cfg['next_popup']
                    else:
                        reply = strip_emoji(result.get('reply') or "Hmm, try asking me with 'Do you like...?'")
                        next_stage = stage  # 같은 단계에 머물며 재시도
                        popup = cfg['popup']  # 같은 팝업을 다시 보여줌

            # 4) 수업 종료 이후: 자유 대화로 마무리
            else:
                reply = call_gemini_text(
                    f'The lesson is finished. The student said: "{user_message}". '
                    f'Reply warmly in ONE short sentence. Do not ask a new structured question.'
                )
                next_stage = 'done'

        except Exception as e:
            print(f"Gemini API 에러: {e}")
            traceback.print_exc()
            reply = "I am a little shy today. Can you say that again?"
            next_stage = stage

    # 📊 구글 스프레드시트에 실시간 로그 기록
    if sheet:
        try:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            sheet.append_row([current_time, student_info, user_message, reply])
        except Exception as e:
            print(f"구글 시트 저장 실패: {e}")
            traceback.print_exc()
    else:
        print("⚠️ 구글 시트가 연결되어 있지 않아 이번 대화는 기록되지 않았습니다.")

    return jsonify({'reply': reply, 'popup': popup, 'stage': next_stage})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
