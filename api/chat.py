# api/chat.py
from http.server import BaseHTTPRequestHandler
import json
import requests
import os

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        # 從雲端環境變數讀取金鑰，不直接寫在程式裡
        api_key = os.environ.get("GEMINI_API_KEY")
        
        # 2026 最新穩定版網址
        url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={api_key}"

        # 讀取網頁傳過來的訊息
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        user_msg = json.loads(post_data).get("message")

        # 設定對話邏輯
        diagnostic_logic = "你是一位維修專家。紅燈檢查電源，綠燈按Reset。"
        
        # 準備傳給 Gemini 的資料
        payload = {
            "contents": [{"parts": [{"text": f"指令：{diagnostic_logic}\n客戶問題：{user_msg}"}]}]
        }

        # 呼叫 API
        response = requests.post(url, headers={'Content-Type': 'application/json'}, data=json.dumps(payload))
        
        # 回傳給你的網頁介面
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*') # 讓網頁可以順利讀取
        self.end_headers()
        self.wfile.write(response.text.encode())
