import os
import json
import re
import random
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
# ✏️  나라별 챗봇 설정
# ═══════════════════════════════════════════════════════════════

CHARACTER_NAME    = "Luca"
CHARACTER_COUNTRY = "Italy"
CHARACTER_AGE     = 10
CHARACTER_GENDER  = "boy"

SPREADSHEET_TITLE = "chatbot-Italy"
SHEET_TAB         = "Italy"

# ═══════════════════════════════════════════════════════════════
# 🔑 Gemini API 설정 (가장 표준적인 1.5-flash 적용)
# ═══════════════════════════════════════════════════════════════
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
else:
    print("⚠️  GEMINI_API_KEY 없음")

def make_model(system_instruction=None):
    # 가장 구동률이 높고 안정적인 2.5-flash 모델
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
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT 환경변수 없음")
    service_account_info = json.loads(raw_creds)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
    gc    = gspread.authorize(creds)

    spreadsheet = gc.open(SPREADSHEET_TITLE)

    try:
        sheet = spreadsheet.worksheet(SHEET_TAB)
        print(f"✅ 기존 탭 연결: [{SHEET_TAB}]")
    except gspread.exceptions.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title=SHEET_TAB, rows=1000, cols=6)
        sheet.append_row(["시간", "학생정보", "학생발화", "루카응답", "단계", "나라"])
        print(f"✅ 새 탭 생성: [{SHEET_TAB}]")

    print(f"✅ 구글 시트 연동 성공 → 파일: [{SPREADSHEET_TITLE}] / 탭: [{SHEET_TAB}]")

except Exception as e:
    print(f"❌ 구글 시트 연동 실패: {e}")
    sheet = None

# ─────────────────────────────────────────────────────────────
# 🌍 시스템 프롬프트
# ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = f"""
You are {CHARACTER_NAME}, a {CHARACTER_AGE}-year-old {CHARACTER_GENDER} from {CHARACTER_COUNTRY}.
You are an EFL learning chatbot for Korean 3rd-grade elementary students (complete beginners, CEFR A1).

=== LANGUAGE RULES ===
- Always reply ONLY in English. Never use Korean in your reply.
- If the student writes in Korean or mixed Korean-English, understand their meaning but reply only in English.
- Students may mix Korean and English or pronounce Korean food names with Korean accents.
- If a word appears to be a speech recognition mistake, infer the student's intended food from the conversation context and answer naturally in English.
- Use only very simple words: feelings, food names, colors, animals, numbers.
- Keep replies to 1-2 short, complete sentences. Never leave a sentence unfinished.
- NO emojis. NO special symbols. Plain text only (TTS reads this aloud).

=== CONVERSATION FLOW ===
Follow this flow in order. Do not skip steps.

[STEP 1 - GREETING]
Your opening line is fixed: "Hi, my name is {CHARACTER_NAME}. Nice to meet you."
Wait for the student to greet you back (Hi, Hello, etc.).
When they greet you, respond: "Hi!" or "Hello!" then ask "How are you?"

[STEP 2 - FEELING]
Wait for the student to express their feeling.
- Positive feelings (fine, happy, good, awesome, perfect, excited, okay, best, wonderful, super, great):
  → Reply: "That's great. I'm good too."
- Negative feelings (bad, sad, tired, sick, bored, angry, sleepy, hungry, so-so, terrible, not good):
  → Reply: "Oh, that's too bad. I hope you feel better."
- If unclear or just one word, still accept and respond warmly.

[STEP 3 - FREE QUESTION INVITATION]
After responding to their feeling, say: "Now, ask me anything!"
This invites the student to ask you questions freely.

[STEP 4 - FOOD PREFERENCE QUESTIONS]
When the student asks "Do you like (food)?":

  Rule A — First food question:
    Randomly choose YES or NO. Remember your choice as first_answer.
    - If YES: "Yes, I do. I like (food name)."
    - If NO: "No, I don't. I don't like (food name)."

  Rule B — Second food question:
    Do the OPPOSITE of first_answer.
    - If first was YES → say NO: "No, I don't. I don't like (food name)."
    - If first was NO → say YES: "Yes, I do. I like (food name)."
    After answering, ask back: "How about you? Do you like (second food name)?"

  Rule C — Student's response to your question back:
    - If student says YES (yes, i do, yeah, yep, sure):
      Check if this matches your second answer.
      - If your second answer was YES → "Oh, we are the same! I like it too! Great!"
      - If your second answer was NO → "Oh, that's okay. We can be different."
    - If student says NO (no, i don't, nope, nah):
      Check if this matches your second answer.
      - If your second answer was NO → "Oh, we are the same! I don't like it either! Great!"
      - If your second answer was YES → "Oh, that's okay. We can be different."

  Rule D — Any other food question:
    For any later "Do you like...?" questions, answer naturally with either YES or NO.
    Use "it" instead of repeating the food name.

[STEP 5 - MORE QUESTIONS]
After the food exchange is done, ask: "Do you have any other questions?"
- If student asks a non-food question: give a simple, appropriate A1-level answer.
- If student says no: Reply "It was nice to meet you. See you next time! Bye."

=== IMPORTANT ===
- Accept one-word answers (e.g., "happy", "yes", "pizza") as valid.
- Never ask two questions at once.
- Always complete every sentence fully before ending your reply.
"""

# ─────────────────────────────────────────────────────────────
# 🛠️  유틸리티 및 Gemini 호출 (진짜 에러 출력 기능 추가)
# ─────────────────────────────────────────────────────────────
EMOJI_PATTERN = re.compile(
    "[" "\U0001F1E6-\U0001F1FF" "\U0001F300-\U0001FAFF"
    "\u2600-\u27BF" "\u2B00-\u2BFF" "]+", flags=re.UNICODE
)

def strip_emoji(text):
    return EMOJI_PATTERN.sub('', text or '').strip()

def call_gemini(history_messages, max_tokens=200):
    # 1) API 키가 비어있는 경우
    if not GEMINI_KEY:
        return "ERROR: GEMINI_API_KEY 환경변수가 없습니다."
    try:
        model  = make_model(SYSTEM_PROMPT)
        config = genai.types.GenerationConfig(
            max_output_tokens=max_tokens,
            temperature=0.8,
        )
        
        contents = []
        for msg in history_messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({
                "role": role,
                "parts": [{"text": msg["content"]}]
            })

        response = model.generate_content(
            contents,
            generation_config=config
        )
        
        raw = strip_emoji(response.text.strip())
        if raw and raw[-1] not in ".!?":
            raw += "."
        return raw

    except Exception as e:
        # 2) API 호출 시 에러가 나면 챗봇 창에 그대로 원인을 출력해줍니다!
        print(f"❌ Gemini API 호출 에러: {e}")
        traceback.print_exc()
        return f"API ERROR: {str(e)}"

def detect_stage(user_message, current_stage, session_data):
    t = user_message.lower().strip()

    end_phrases = ['no thank', 'no thanks', 'no, thank', 'bye', 'goodbye',
                   '없어요', '없어', '괜찮아요', '없음']
    is_end = any(p in t for p in end_phrases) or re.fullmatch(r'no[.!]?', t)

    if current_stage == 'await_greeting':
        greet_words = ['hi', 'hello', 'hey', 'nice to meet', 'good morning', 'good afternoon', '안녕', '헬로', '하이']
        if any(w in t for w in greet_words):
            return 'await_feeling', "지금 기분을 영어로 말해보세요."
        else:
            return 'await_greeting', f"{CHARACTER_NAME}에게 영어로 인사를 해보세요!"

    elif current_stage == 'await_feeling':
        feeling_words = ['fine', 'happy', 'good', 'awesome', 'perfect', 'excited', 'okay',
                         'best', 'wonderful', 'super', 'great', 'bad', 'sad', 'tired',
                         'sick', 'bored', 'angry', 'sleepy', 'hungry', 'terrible',
                         'so-so', 'not good', 'well', 'ok', '좋아', '행복', '피곤']
        if any(w in t for w in feeling_words) or len(t) >= 2:
            return 'free_question', "루카에게 궁금한 것을 물어보세요!"
        else:
            return 'await_feeling', "지금 기분을 영어로 말해보세요."

    elif current_stage == 'free_question':
        if is_end:
            return 'done', None
        if 'do you like' in t or ('like' in t and ('food' in t or _has_food_word(t))):
            food = _extract_food(t)
            if food:
                if 'first_food' not in session_data:
                    session_data['first_food'] = food
                    session_data['first_answer'] = random.choice(['yes', 'no'])
                elif 'second_food' not in session_data:
                    session_data['second_food'] = food
                    session_data['second_answer'] = 'no' if session_data['first_answer'] == 'yes' else 'yes'
                    return 'await_student_food_answer', "네 또는 아니오로 답해보세요."
            return 'free_question', "루카에게 더 궁금한 것이 있나요?"
        return 'free_question', "루카에게 더 궁금한 것이 있나요?"

    elif current_stage == 'await_student_food_answer':
        if is_end:
            return 'done', None
        return 'free_question', "루카에게 더 궁금한 것이 있나요?"

    elif current_stage == 'free_question_2':
        if is_end:
            return 'done', None
        return 'free_question_2', "루카에게 더 궁금한 것이 있나요?"

    else:
        return 'done', None

def _has_food_word(t):
    food_words = ['pizza', 'ice cream', 'icecream', 'spaghetti', 'pasta', 'burger',
                  'hamburger', 'sushi', 'ramen', 'taco', 'sandwich', 'apple', 'banana',
                  'cake', 'cookie', 'chocolate', 'kimchi', 'rice', 'noodle', 'bread',
                  'cheese', 'milk', 'juice', 'chicken', 'fish', 'egg', 'soup', 'salad',
                  '피자', '아이스크림', '스파게티', '햄버거', '초콜릿']
    return any(f in t for f in food_words)

def _extract_food(t):
    food_list = [
        'pizza', 'ice cream', 'spaghetti', 'pasta', 'burger', 'hamburger',
        'sushi', 'ramen', 'taco', 'sandwich', 'apple', 'banana', 'cake',
        'cookie', 'chocolate', 'kimchi', 'rice', 'noodle', 'bread',
        'cheese', 'milk', 'juice', 'chicken', 'fish', 'egg', 'soup', 'salad'
    ]
    for food in food_list:
        if food in t:
            return food
    return None

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
    stage        = (data.get('stage') or 'await_greeting').strip()

    if 'chat_history' not in session:
        session['chat_history'] = []
    if 'food_data' not in session:
        session['food_data'] = {}

    history   = session['chat_history']
    food_data = session['food_data']

    fireworks = False
    popup     = None

    if not GEMINI_KEY:
        reply = "ERROR: GEMINI_API_KEY가 등록되지 않았습니다."
        return _respond(reply, popup, stage, fireworks, student_info, user_message, history)

    try:
        next_stage, popup = detect_stage(user_message, stage, food_data)
        session['food_data'] = food_data

        if next_stage == 'done':
            fireworks = True
            popup     = None

        food_context = ""
        if food_data.get('first_food'):
            food_context = (
                f"\n[CONTEXT FOR THIS TURN]\n"
                f"first_food={food_data.get('first_food')}, "
                f"first_answer={food_data.get('first_answer')}, "
                f"second_food={food_data.get('second_food','not yet')}, "
                f"second_answer={food_data.get('second_answer','not yet')}\n"
                f"Use this context to give the correct answer and reaction.\n"
            )

        history.append({
            "role": "user",
            "content": user_message + food_context
        })

        reply = call_gemini(history, max_tokens=200)

        if not reply:
            reply = "I am a little shy today. Can you say that again?"

        if history and food_context in history[-1].get("content", ""):
            history[-1]["content"] = user_message

    except Exception as e:
        print(f"❌ 에러: {e}")
        traceback.print_exc()
        reply      = f"SERVER ERROR: {str(e)}"
        next_stage = stage

    return _respond(reply, popup, next_stage, fireworks, student_info, user_message, history)

def _respond(reply, popup, next_stage, fireworks, student_info, user_message, history):
    history.append({"role": "assistant", "content": reply})
    session['chat_history'] = history[-30:]

    if sheet:
        try:
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            sheet.append_row([now, student_info, user_message, reply, next_stage, CHARACTER_COUNTRY])
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
