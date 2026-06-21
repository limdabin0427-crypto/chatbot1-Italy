import os
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app) # 프론트엔드와 백엔드가 서로 통신할 수 있게 허용

# 1. 브라우저가 처음 접속했을 때 루카 챗봇 화면(index.html)을 보여주는 주소
@app.route('/')
def home():
    return render_template('index.html')

# 2. [테스트용] 프론트엔드가 루카에게 말을 걸면 응답하는 백엔드 주소
@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json()
    user_message = data.get('message', '')
    
    # 나중에 여기에 OpenAI(ChatGPT) 등을 연결하면 진짜 AI 챗봇이 됩니다!
    reply_message = f"파이썬 백엔드 서버가 대답해요! 보낸 말: '{user_message}'"
    
    return jsonify({'reply': reply_message})

if __name__ == '__main__':
    # Render 배포를 위해 포트 설정을 유연하게 잡아줍니다.
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
