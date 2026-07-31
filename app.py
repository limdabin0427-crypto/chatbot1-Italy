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

from config import (
    CHATBOT_ID, ENABLE_GOOGLE_SHEETS, ENDING_EXPRESSIONS, FLASK_SECRET_KEY,
    GOOGLE_SERVICE_ACCOUNT_ENV, MAX_HISTORY_MESSAGES, MAX_RESPONSE_TOKENS,
    MODEL_NAME, OPENAI_API_KEY_ENV, SPREADSHEET_ID, Stage, TEMPERATURE,
)
from data_loader import CHARACTERS
from dialogue_manager import compare_food_answers, get_food_answer, make_food_response
from food_utils import clean_text, find_food

app = Flask(__name__, static_folder='.', static_url_path='')
app.secret_key = FLASK_SECRET_KEY
CORS(app)

CHARACTER = CHARACTERS[CHATBOT_ID]
CHARACTER_NAME = CHARACTER['name']
COUNTRY = CHARACTER['country']
SHEET_TAB = CHARACTER.get('sheet_tab', CHATBOT_ID)
ENDING_MESSAGE = CHARACTER['ending_message']

openai_key = os.environ.get(OPENAI_API_KEY_ENV)
openai_client = OpenAI(api_key=openai_key) if openai_key else None

sheet = None
if ENABLE_GOOGLE_SHEETS:
    try:
        raw_creds = os.environ.get(GOOGLE_SERVICE_ACCOUNT_ENV)
        if raw_creds:
            info = json.loads(raw_creds)
            creds = Credentials.from_service_account_info(
                info,
                scopes=[
                    'https://www.googleapis.com/auth/spreadsheets',
                    'https://www.googleapis.com/auth/drive',
                ],
            )
            spreadsheet = gspread.authorize(creds).open_by_key(SPREADSHEET_ID)
            try:
                sheet = spreadsheet.worksheet(SHEET_TAB)
            except gspread.exceptions.WorksheetNotFound:
                sheet = spreadsheet.add_worksheet(title=SHEET_TAB, rows=1000, cols=7)
                sheet.append_row(['시간','학생정보','학생발화(보정)','원본발화','루카응답','단계','나라'])
            print(f'✅ 구글 시트 연결: {SHEET_TAB}')
        else:
            print('⚠️ GOOGLE_SERVICE_ACCOUNT 환경변수 없음')
    except Exception as error:
        print(f'❌ 구글 시트 연결 실패: {error}')
        traceback.print_exc()


def normalize_stage(stage):
    aliases = {
        'await_greeting': Stage.WAIT_GREETING.value,
        'WAIT_GREETING': Stage.WAIT_GREETING.value,
    }
    return aliases.get(stage, stage or Stage.WAIT_GREETING.value)


def extract_name(message):
    text = message.strip().strip(' .!?')
    text = re.sub(r'^(my name is|i am|i\'m)\s+', '', text, flags=re.I).strip()
    return text or 'my friend'


def is_korea(message):
    t = clean_text(message)
    return any(x in t for x in ['korea', 'south korea', '한국', '대한민국'])


def is_end_message(message):
    t = clean_text(message)
    return any(t == clean_text(x) or clean_text(x) in t for x in ENDING_EXPRESSIONS)


def extract_unknown_food(message):
    m = re.search(r'\bdo\s+you\s+like\s+(.+?)(?:[?.!]|$)', message, re.I)
    if not m:
        return None
    return re.sub(r'\s+', ' ', m.group(1)).strip(' ,.? !').lower() or None


def get_food_name(message):
    matched = find_food(message)
    if matched:
        return matched['display_name']
    return extract_unknown_food(message)


def is_food_question(message):
    return 'do you like' in clean_text(message) and get_food_name(message) is not None


def normalize_user_message(message):
    """STT 오인식을 foods.json 별칭으로 보정해 채팅/로그에 돌려준다."""
    if not is_food_question(message):
        return message.strip()
    food = get_food_name(message)
    return f'Do you like {food}?'


def parse_yes_no(message):
    t = clean_text(message)
    negatives = ["no", "no i dont", "i dont", "dont like", "not really", "싫어", "아니"]
    positives = ["yes", "yes i do", "i do", "i like", "love", "좋아", "응"]
    if any(x in t for x in negatives):
        return 'no'
    if any(x in t for x in positives):
        return 'yes'
    return None


def free_chat_reply(message, history):
    if not openai_client:
        return "That's a good question. Do you have more questions?"
    prompt = f"""
You are {CHARACTER_NAME}, a 10-year-old child from {COUNTRY}.
Talk to Korean grade-3 beginner English learners.
Use one or two very short A1-level English sentences.
Accept simple, imperfect, or mixed Korean-English input.
Stay on the student's topic, then gently ask: Do you have more questions?
Do not explain grammar. Do not use emojis.
""".strip()
    messages = [{'role':'system','content':prompt}]
    messages.extend([
        x for x in history[-8:]
        if x.get('role') in {'user','assistant'} and x.get('content')
    ])
    messages.append({'role':'user','content':message})
    try:
        result = openai_client.chat.completions.create(
            model=MODEL_NAME, messages=messages, temperature=TEMPERATURE,
            max_tokens=MAX_RESPONSE_TOKENS,
        )
        reply = result.choices[0].message.content.strip()
        if 'do you have more questions' not in reply.lower():
            reply += ' Do you have more questions?'
        return reply
    except Exception as error:
        print(f'❌ OpenAI 호출 실패: {error}')
        return "That's a good question. Do you have more questions?"


def save_log(student, corrected, original, reply, stage):
    if sheet is None:
        return
    try:
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        # 기존 6열 시트와 새 7열 시트 모두 호환되도록 7개 기록
        sheet.append_row([now, student, corrected, original, reply, stage, COUNTRY])
    except Exception as error:
        print(f'❌ 시트 저장 실패: {error}')
        traceback.print_exc()


def respond(reply, popup, next_stage, fireworks, student, original, corrected=None):
    corrected = corrected or original
    history = session.get('chat_history', [])
    history += [
        {'role':'user','content':corrected},
        {'role':'assistant','content':reply},
    ]
    session['chat_history'] = history[-MAX_HISTORY_MESSAGES:]
    session.modified = True
    save_log(student, corrected, original, reply, next_stage)
    return jsonify({
        'reply': reply,
        'popup': popup,
        'stage': next_stage,
        'fireworks': fireworks,
        'recognized_text': corrected,
    })


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/api/config', methods=['GET'])
def chatbot_config():
    """현재 config.py의 CHATBOT_ID에 해당하는 화면 설정을 전달한다."""
    images = CHARACTER.get('images', {})
    character_images = images.get('character', {})
    tts = CHARACTER.get('tts', {})

    return jsonify({
        'chatbotId': CHATBOT_ID,
        'characterName': CHARACTER_NAME,
        'country': COUNTRY,
        'gif': {
            'greeting': character_images.get('greeting', 'greeting.gif'),
            'speaking': character_images.get('speaking', 'speaking.gif'),
            'yes': character_images.get('yes', 'yes.gif'),
            'no': character_images.get('no', 'no.gif'),
        },
        'backgrounds': images.get('backgrounds', []),
        'flagImg': images.get('flag', ''),
        'tts': {
            'gender': tts.get('gender', CHARACTER.get('gender', 'male')),
            'childMode': tts.get('child_mode', True),
            'rate': tts.get('rate', 0.85),
            'pitch': tts.get('pitch', 1.35),
        },
        'openingLine': CHARACTER.get(
            'opening_line',
            f'Hi! My name is {CHARACTER_NAME}. Nice to meet you.',
        ),
        'finaleMsg': CHARACTER.get(
            'finale_message',
            "Great job! Let's meet new friends!\n잘했어요! 다른 나라 친구도 만나보세요!",
        ),
    })


@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json(force=True, silent=True) or {}
    student = data.get('student', 'Unknown')
    original = (data.get('message') or '').strip()
    stage = normalize_stage((data.get('stage') or '').strip())

    if not original:
        return respond('Please say that again.', '다시 한번 말해보세요.', stage, False, student, original)

    if stage == Stage.WAIT_GREETING.value:
        session.clear()
        return respond(
            f"Hi, I'm {CHARACTER_NAME}. What's your name?",
            '내 이름을 소개해 보세요.',
            Stage.WAIT_NAME.value, False, student, original,
        )

    if stage == Stage.WAIT_NAME.value:
        name = extract_name(original)
        session['student_name'] = name
        return respond(
            f'Oh! Hello {name}! Nice to meet you. Where are you from?',
            "'한국'에서 온 것을 표현해 보세요.",
            Stage.WAIT_COUNTRY.value, False, student, original,
        )

    if stage == Stage.WAIT_COUNTRY.value:
        if not is_korea(original):
            return respond(
                'Please say, "I\'m from Korea."',
                "I'm from Korea. 또는 Korea라고 말해보세요.",
                Stage.WAIT_COUNTRY.value, False, student, original,
            )
        session['food_question_number'] = 0
        return respond(
            f"I'm from {COUNTRY}! Now ask me any questions.",
            f'{CHARACTER_NAME}에게 음식에 관해 궁금한 것을 물어보세요.',
            Stage.FOOD_Q1.value, False, student, original,
        )

    food_question_stages = {
        Stage.FOOD_Q1.value: (0, Stage.FOOD_A1.value, '네 또는 아니오로 답해보세요.'),
        Stage.FOOD_Q2.value: (1, Stage.FOOD_A2.value, '네 또는 아니오로 답해보세요.'),
        Stage.FOOD_Q3.value: (2, Stage.FOOD_A3.value, '네 또는 아니오로 답해보세요.'),
    }
    if stage in food_question_stages:
        number, next_stage, popup = food_question_stages[stage]
        if not is_food_question(original):
            return respond(
                'Please ask, "Do you like pizza?"',
                'Do you like ___? 문장으로 물어보세요.',
                stage, False, student, original,
            )
        corrected = normalize_user_message(original)
        food = get_food_name(corrected)
        bot_answer = get_food_answer(COUNTRY, number)
        session['current_food'] = food
        session['bot_food_answer'] = bot_answer
        session['food_question_number'] = number
        return respond(
            make_food_response(bot_answer, food, ask_back=True),
            popup, next_stage, False, student, original, corrected,
        )

    food_answer_stages = {
        Stage.FOOD_A1.value: (Stage.FOOD_Q2.value, 'Any questions?', f'또, {CHARACTER_NAME}에게 궁금한 것을 물어보세요.'),
        Stage.FOOD_A2.value: (Stage.FOOD_Q3.value, 'Any other questions?', f'또, {CHARACTER_NAME}에게 궁금한 것을 물어보세요.'),
        Stage.FOOD_A3.value: (Stage.FREE_CHAT.value, 'Do you have more questions?', f'{CHARACTER_NAME}에게 더 궁금한 것이 있나요? 없다면 No, thank you.라고 말하세요.'),
    }
    if stage in food_answer_stages:
        student_answer = parse_yes_no(original)
        if student_answer is None:
            return respond(
                'Please answer, "Yes, I do" or "No, I don\'t."',
                '네 또는 아니오로 답해보세요.', stage, False, student, original,
            )
        next_stage, ending_question, popup = food_answer_stages[stage]
        bot_answer = session.get('bot_food_answer', 'yes')
        reply = compare_food_answers(bot_answer, student_answer, ending_question)
        return respond(reply, popup, next_stage, False, student, original)

    if stage == Stage.FREE_CHAT.value:
        if is_end_message(original):
            return respond(ENDING_MESSAGE, None, Stage.END.value, True, student, original)
        history = session.get('chat_history', [])
        reply = free_chat_reply(original, history)
        return respond(
            reply,
            f'{CHARACTER_NAME}에게 더 궁금한 것이 있나요? 없다면 No, thank you.라고 말하세요.',
            Stage.FREE_CHAT.value, False, student, original,
        )

    return respond(ENDING_MESSAGE, None, Stage.END.value, True, student, original)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
