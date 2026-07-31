import json
import os
import re
import traceback
from datetime import datetime

import gspread
from flask import Flask, jsonify, render_template, request, session
from flask_cors import CORS
from google.oauth2.service_account import Credentials
from openai import OpenAI

from data_loader import ANSWER_PATTERNS, CHARACTERS, FOODS
from dialogue_manager import make_food_response
from food_utils import clean_text, find_food


app = Flask(__name__, static_folder='.', static_url_path='')
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'italy-chatbot-secret-key')
CORS(app)

# ============================================================
# Italy 챗봇 설정
# ============================================================
COUNTRY = 'Italy'
CHARACTER = CHARACTERS[COUNTRY]
CHARACTER_NAME = CHARACTER['name']
CHARACTER_COUNTRY = CHARACTER['country']
SHEET_TAB = CHARACTER['sheet_tab']
ENDING_MESSAGE = CHARACTER['ending_message']

SPREADSHEET_ID = '1D1xcyBiIOtBE3QfrPMx84RVIREf-8kq5XDqTZWCrDMU'
ANSWER_PATTERN = ANSWER_PATTERNS.get(COUNTRY, ['yes', 'no', 'yes'])

# ============================================================
# OpenAI 설정: 음식 외 자유 질문에만 사용
# ============================================================
OPENAI_KEY = os.environ.get('OPENAI_API_KEY')
openai_client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

# ============================================================
# Google Sheets 연결
# ============================================================
sheet = None
try:
    raw_creds = os.environ.get('GOOGLE_SERVICE_ACCOUNT')
    if not raw_creds:
        print('⚠️ GOOGLE_SERVICE_ACCOUNT 환경변수 없음')
    else:
        service_account_info = json.loads(raw_creds)
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive',
        ]
        creds = Credentials.from_service_account_info(
            service_account_info,
            scopes=scopes,
        )
        gc = gspread.authorize(creds)
        spreadsheet = gc.open_by_key(SPREADSHEET_ID)

        try:
            sheet = spreadsheet.worksheet(SHEET_TAB)
            print(f'✅ 구글 시트 탭 연결 성공: {SHEET_TAB}')
        except gspread.exceptions.WorksheetNotFound:
            sheet = spreadsheet.add_worksheet(
                title=SHEET_TAB,
                rows=1000,
                cols=6,
            )
            sheet.append_row([
                '시간', '학생정보', '학생발화', '루카응답', '단계', '나라'
            ])
            print(f'✅ 구글 시트 탭 생성 성공: {SHEET_TAB}')
except Exception as error:
    print(f'❌ 구글 시트 연결 실패: {error}')
    traceback.print_exc()
    sheet = None


POSITIVE_FEELINGS = {
    'fine', 'happy', 'good', 'great', 'awesome', 'perfect', 'excited',
    'okay', 'ok', 'wonderful', 'super', 'well', 'best'
}
NEGATIVE_FEELINGS = {
    'bad', 'sad', 'tired', 'sick', 'bored', 'angry', 'sleepy',
    'hungry', 'terrible', 'so so', 'not good'
}
GREETING_WORDS = {
    'hi', 'hello', 'hey', 'good morning', 'good afternoon',
    'nice to meet you', '안녕', '하이', '헬로'
}
END_PHRASES = {
    'no', 'no thanks', 'no thank you', 'nothing', 'bye', 'goodbye',
    '없어요', '없어', '없음', '괜찮아요'
}


def contains_phrase(text, phrases):
    return any(phrase in text for phrase in phrases)


def is_end_message(text):
    cleaned = clean_text(text)
    return cleaned in END_PHRASES or contains_phrase(cleaned, {
        'no thanks', 'no thank you', 'goodbye'
    })


def extract_unknown_food(message):
    """foods.json에 없는 음식도 Do you like ___?에서 꺼낸다."""
    match = re.search(
        r'\bdo\s+you\s+like\s+(.+?)(?:\?|\.|!|$)',
        message,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    food_name = match.group(1).strip(' ,.? !')
    food_name = re.sub(r'\s+', ' ', food_name)
    if not food_name:
        return None
    return food_name.lower()


def get_food_name(message):
    matched_food = find_food(message)
    if matched_food:
        return matched_food['display_name']
    return extract_unknown_food(message)


def is_food_question(message):
    cleaned = clean_text(message)
    return 'do you like' in cleaned and get_food_name(message) is not None


def feeling_reply(message):
    cleaned = clean_text(message)
    if contains_phrase(cleaned, NEGATIVE_FEELINGS):
        return "Oh, that's too bad. I hope you feel better. Now, ask me anything!"
    return "That's great. I'm good too. Now, ask me anything!"


def ask_openai_simple(message, history):
    """세 음식 질문 이후의 간단한 자유 질문에만 사용한다."""
    if not openai_client:
        return "That's a good question."

    system_prompt = f"""
You are {CHARACTER_NAME}, a 10-year-old child from {CHARACTER_COUNTRY}.
You are talking with Korean third-grade EFL beginners.
Reply only in very simple English.
Use one or two short sentences.
Do not use emojis or Korean.
Do not ask two questions at once.
""".strip()

    messages = [{'role': 'system', 'content': system_prompt}]
    for item in history[-8:]:
        role = item.get('role')
        content = item.get('content', '')
        if role in {'user', 'assistant'} and content:
            messages.append({'role': role, 'content': content})
    messages.append({'role': 'user', 'content': message})

    try:
        response = openai_client.chat.completions.create(
            model='gpt-4o-mini',
            messages=messages,
            temperature=0.4,
            max_tokens=80,
        )
        reply = response.choices[0].message.content.strip()
        reply = re.sub(r'[\U00010000-\U0010ffff]', '', reply).strip()
        return reply or "That's a good question."
    except Exception as error:
        print(f'❌ OpenAI 호출 실패: {error}')
        traceback.print_exc()
        return "That's a good question."


def save_log(student_info, user_message, reply, next_stage):
    if sheet is None:
        print('⚠️ 구글 시트 미연결 상태 - 로그 저장 생략')
        return

    try:
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        sheet.append_row([
            now,
            student_info,
            user_message,
            reply,
            next_stage,
            CHARACTER_COUNTRY,
        ])
        print(f'📊 시트 로그 저장 성공: {student_info} - {user_message}')
    except Exception as error:
        print(f'❌ 시트 저장 실패: {error}')
        traceback.print_exc()


def make_response(reply, popup, next_stage, fireworks, student_info, user_message):
    history = session.get('chat_history', [])
    history.append({'role': 'user', 'content': user_message})
    history.append({'role': 'assistant', 'content': reply})
    session['chat_history'] = history[-30:]
    session.modified = True

    save_log(student_info, user_message, reply, next_stage)

    return jsonify({
        'reply': reply,
        'popup': popup,
        'stage': next_stage,
        'fireworks': fireworks,
    })


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json(force=True, silent=True) or {}
    student_info = data.get('student', 'Unknown')
    user_message = (data.get('message') or '').strip()
    stage = (data.get('stage') or 'await_greeting').strip()

    if not user_message:
        return make_response(
            'Please say that again.',
            '다시 한번 말해보세요.',
            stage,
            False,
            student_info,
            user_message,
        )

    if stage == 'await_greeting':
        reply = 'Hi! How are you?'
        return make_response(
            reply,
            '지금 기분을 영어로 말해보세요.',
            'await_feeling',
            False,
            student_info,
            user_message,
        )

    if stage == 'await_feeling':
        session['food_question_count'] = 0
        reply = feeling_reply(user_message)
        return make_response(
            reply,
            'Do you like ___? 문장으로 음식에 대해 물어보세요.',
            'food_questions',
            False,
            student_info,
            user_message,
        )

    if stage == 'food_questions':
        if is_food_question(user_message):
            food_name = get_food_name(user_message)
            question_count = int(session.get('food_question_count', 0))

            if question_count < 3:
                answer = ANSWER_PATTERN[question_count]
                reply = make_food_response(answer, food_name)
                question_count += 1
                session['food_question_count'] = question_count
                session.modified = True

                if question_count < 3:
                    popup = f'{question_count + 1}번째 음식 질문을 해보세요.'
                    next_stage = 'food_questions'
                else:
                    reply += ' Do you have any other questions?'
                    popup = '질문이 더 있으면 말하고, 없으면 No라고 대답하세요.'
                    next_stage = 'more_questions'

                return make_response(
                    reply,
                    popup,
                    next_stage,
                    False,
                    student_info,
                    user_message,
                )

        return make_response(
            'Please ask, "Do you like food?"',
            'Do you like ___? 문장으로 음식 질문을 해보세요.',
            'food_questions',
            False,
            student_info,
            user_message,
        )

    if stage == 'more_questions':
        if is_end_message(user_message):
            return make_response(
                ENDING_MESSAGE,
                None,
                'done',
                True,
                student_info,
                user_message,
            )

        history = session.get('chat_history', [])
        reply = ask_openai_simple(user_message, history)
        reply += ' Do you have any other questions?'
        return make_response(
            reply,
            '질문이 더 있으면 말하고, 없으면 No라고 대답하세요.',
            'more_questions',
            False,
            student_info,
            user_message,
        )

    return make_response(
        ENDING_MESSAGE,
        None,
        'done',
        True,
        student_info,
        user_message,
    )


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
