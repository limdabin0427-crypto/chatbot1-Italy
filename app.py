import os
import json
import re
import traceback
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import gspread
from google.oauth2.service_account import Credentials

# OpenAI 공식 라이브러리 추가
from openai import OpenAI

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

# 🔑 Render 환경변수에 등록한 OpenAI API 키와 구글 키 가져오기
# (Render Dashboard -> Environment Variables에 OPENAI_API_KEY도 꼭 추가해주세요!)
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None
if not OPENAI_KEY:
    print("⚠️ OPENAI_API_KEY 환경변수가 비어있습니다. AI 대화가 동작하지 않습니다.")

# 📊 구글 스프레드시트 연동 설정
sheet = None
try:
    raw_creds = os.environ.get("GOOGLE_SERVICE_ACCOUNT")
    if not raw_creds:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT 환경변수가 비어있습니다.")

    service_account_info = json.loads(raw_creds)
    # spreadsheets 범위만으로도 동작하지만, drive 범위를 같이 주면
    # 권한 관련 에러(PERMISSION_DENIED)를 예방하는 데 도움이 됩니다.
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

# 🇮🇹 초등학교 3학년 학생 맞춤형 대화 규칙 (페다고지 프롬프트)
# ※ 이 규칙은 '루카가 생성하는 대화 답변'에만 적용됩니다.
#   로그인 화면, 안내 문구(힌트), 버튼 등 사이트의 다른 이모지는 이 규칙과 무관하며 그대로 유지됩니다.
LUCA_RULE = """
You are Luca, a friendly 10-year-old boy from Italy. 
Your user is a 3rd-grade elementary school student in South Korea who is just starting to learn English (CEFR A1 level). They have just learned the alphabet.

Follow these strict pedagogical rules for every reply:
1. [Short Sentences]: Your reply must always be just 1-2 sentences. Never write more than that.
2. [Easy Vocabulary]: Use only words a Korean 3rd grader would know, such as colors, animals, food, weather, and school supplies. Nothing more advanced.
3. [Always Ask Back]: Always end your reply with an easy question the child can answer, to keep the conversation going (e.g., "What is your favorite color?", "Do you like apples?").
4. [Beginner-Friendly]: Remember this student just learned the alphabet. A single-word answer (e.g., "Apple", "Red", "Dog") is a complete, valid answer — respond warmly and keep the conversation going naturally, even if they only ever say one word at a time. Never criticize a short answer.
5. [Teacher's Feedback]: If the answer is strange, off-topic, or clearly wrong, respond like a kind teacher: give a gentle hint or say something like "Try saying this: [simple example sentence]."
6. [Can't Answer -> Move On]: If the student says "I don't know" or doesn't answer at all, don't dwell on it — move straight on to the lesson's core target sentence.
7. [Small Talk, Then Core Sentence]: Start with a little small talk first (e.g., asking how they feel today). After 1-2 turns, smoothly transition to the core target sentence pattern: "Do you like [something]?".
8. [No Emojis In Your Reply]: Never use emojis, emoticons, or special symbols in your reply. Your words are read aloud by a text-to-speech voice, and emojis get read out as awkward English (e.g. "smiling face"). Plain text only — this rule applies only to your own dialogue, nowhere else.
"""

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json()
    student_info = data.get('student', 'Unknown Student')
    user_message = data.get('message', '')
    # 프론트엔드가 보내주는 이전 대화 기록 (없으면 빈 리스트)
    history = data.get('history', [])

    # 기본 대답 설정
    reply = "Hello! Let's talk!"

    # 🤖 1. 진짜 생성형 OpenAI AI 대화 구현하기
    if client:
        try:
            # 시스템 규칙 + 이전 대화 기록을 모두 포함해서 보내야
            # Luca가 직전 대화 맥락을 기억하고 자연스럽게 이어갑니다.
            messages = [{"role": "system", "content": LUCA_RULE}]
            for turn in history[-20:]:  # 토큰 절약을 위해 최근 20턴만 사용
                role = turn.get('role')
                content = (turn.get('content') or '').strip()
                if role in ('user', 'assistant') and content:
                    messages.append({"role": role, "content": content})

            # history에 이번 사용자 발화가 아직 없다면 마지막에 추가
            if not history or history[-1].get('content') != user_message:
                messages.append({"role": "user", "content": user_message})

            response = client.chat.completions.create(
                model="gpt-4o-mini", # 가성비 좋고 빠른 최신 모델 사용
                messages=messages,
                max_tokens=80,
                temperature=0.7
            )
            reply = response.choices[0].message.content.strip()

            # 만약 모델이 그래도 이모지를 섞어 보내면 서버 단에서 한 번 더 제거
            # (이 reply 변수는 '루카가 하는 말'에만 해당 — 사이트의 다른 이모지는 영향 없음)
            emoji_pattern = re.compile(
                "["
                "\U0001F1E6-\U0001F1FF"
                "\U0001F300-\U0001FAFF"
                "\u2600-\u27BF"
                "\u2B00-\u2BFF"
                "]+", flags=re.UNICODE
            )
            reply = emoji_pattern.sub('', reply).strip()
        except Exception as e:
            print(f"OpenAI API 에러: {e}")
            traceback.print_exc()
            reply = "I am a little shy today. Can you say that again?"
    else:
        # API 키가 안 들어왔을 때의 임시 작동 방지용 안전 장치
        reply = f"Hi! I heard you say '{user_message}'. Do you like soccer?"

    # 📊 2. 구글 스프레드시트에 실시간 로그 기록 추가
    if sheet:
        try:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            sheet.append_row([current_time, student_info, user_message, reply])
        except Exception as e:
            print(f"구글 시트 저장 실패: {e}")
            traceback.print_exc()
    else:
        print("⚠️ 구글 시트가 연결되어 있지 않아 이번 대화는 기록되지 않았습니다.")

    return jsonify({'reply': reply})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
