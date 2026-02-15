from http.server import BaseHTTPRequestHandler
import json
import requests
import os

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        # 這是為了處理瀏覽器的安全檢查
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        api_key = os.environ.get("GEMINI_API_KEY")
        # 這裡改用 v1 版本網址，增加穩定性
        url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={api_key}"

        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            user_msg = json.loads(post_data).get("message")

            # 設定 AI 的人設與邏輯
            payload = {
                "contents": [{
                    "parts": [{"text": f"你是一位設備維修助理。請引導客戶解決問題：紅燈檢查電源，綠燈重設。客戶說：{user_msg}"}]
                }]
            }

            response = requests.post(url, headers={'Content-Type': 'application/json'}, data=json.dumps(payload))
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*') # 允許 GitHub 存取
            self.end_headers()
            self.wfile.write(response.text.encode())
            
        except Exception as e:
            self.send_response(500)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())
