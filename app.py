import os
import json
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

# 1. Render 환경변수에 넣었던 구글 서비스 계정 키 로드
try:
    service_account_info = json.loads(os.environ.get("GOOGLE_SERVICE_ACCOUNT"))
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
    gc = gspread.authorize(creds)
    
    # ⚠️여기에 아까 복사한 선생님의 구글 스프레드시트 ID를 붙여넣으세요!
    SPREADSHEET_ID = "선생님의_구글_시트_ID를_여기에_넣으세요" 
    sheet = gc.open_by_key(SPREADSHEET_ID).sheet1
except Exception as e:
    print(f"구글 시트 연결 실패(체크 필요): {e}")
    sheet = None

# 초3 맞춤형 루카 대화 규칙
LUCA_RULE = """
You are Luca, a friendly 10-year-old boy from Italy. 
Your user is a 3rd-grade elementary school student in South Korea who is just starting to learn English.
1. Use simple sentences (Max 1-2 sentences).
2. End with an easy question to keep the conversation going.
3. Accept single-word answers.
"""

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json()
    student_info = data.get('student', 'Unknown Student') # 프론트에서 보낸 학번/이름
    user_message = data.get('message', '') # 학생이 한 말
    
    # 임시 대답 (나중에 OpenAI 연결 시 진짜 AI 답변으로 바뀜)
    sample_reply = f"Ciao! I'm Luca. How are you today? 😊"
    
    # 📊 구글 스프레드시트에 실시간 로그 기록 추가하기
    if sheet:
        try:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            # 시트 맨 아래에 [일시, 학생정보, 학생 말, 루카 대답]을 한 줄 추가합니다.
            sheet.append_row([current_time, student_info, user_message, sample_reply])
        except Exception as e:
            print(f"시트 기록 실패: {e}")

    return jsonify({'reply': sample_reply})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
