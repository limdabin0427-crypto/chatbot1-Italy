import os
import json
import re
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

# 📊 구글 스프레드시트 연동 설정
try:
    service_account_info = json.loads(os.environ.get("GOOGLE_SERVICE_ACCOUNT"))
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
    gc = gspread.authorize(creds)
    
    # ⚠️여기에 선생님의 구글 스프레드시트 ID(주소창 중간의 긴 문자열)를 꼭 넣어주세요!
    SPREADSHEET_ID = "선생님의_구글_시트_ID를_여기에_넣으세요" 
    sheet = gc.open_by_key(SPREADSHEET_ID).sheet1
except Exception as e:
    print(f"구글 시트 연동 실패: {e}")
    sheet = None

# 🇮🇹 초등학교 3학년 학생 맞춤형 대화 규칙 (페다고지 프롬프트)
LUCA_RULE = """
You are Luca, a friendly 10-year-old boy from Italy. 
Your user is a 3rd-grade elementary school student in South Korea who is just starting to learn English (CEFR A1 level). They have just learned the alphabet.

Follow these strict pedagogical rules for conversation:
1. [Length & Vocabulary]: Use extremely simple, short sentences (Max 1-2 sentences per reply). Use words familiar to 10-year-old Korean kids (colors, animals, food, weather, school supplies).
2. [Keep It Going]: Always end your reply with a very easy question to guide the conversation (e.g., "What is your favorite color?", "Do you like apples?").
3. [Accept Word-Only Answers]: If the student answers with just a single word (e.g., "Apple" or "Red"), accept it warmly and keep the conversation going naturally. Do not criticize.
4. [Teacher's Feedback]: If the student's answer is completely irrelevant, weird, or broken, act like a kind teacher. Provide a gentle hint or say, "Try saying this: [Easy Sentence]".
5. [Handling "I don't know"]: If the student says "I don't know" or cannot answer, move on immediately to the core target sentence of the lesson.
6. [Lesson Flow]: Start with brief small talk first (asking about feelings: "How are you today?"). After 1-2 turns, smoothly transition to the core target sentence: "Do you like [something]?".
"""

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json()
    student_info = data.get('student', 'Unknown Student')
    user_message = data.get('message', '')
    
    # 기본 대답 설정
    reply = "Hello! Let's talk!"
    
    # 🤖 1. 진짜 생성형 OpenAI AI 대화 구현하기
    if client:
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini", # 가성비 좋고 빠른 최신 모델 사용
                messages=[
                    {"role": "system", "content": LUCA_RULE},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=60,
                temperature=0.7
            )
            reply = response.choices[0].message.content.strip()
        except Exception as e:
            print(f"OpenAI API 에러: {e}")
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

    return jsonify({'reply': reply})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
