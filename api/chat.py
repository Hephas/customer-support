import os
import json
import google.generativeai as genai
from http.server import BaseHTTPRequestHandler

# ══════════════════════════════════════
# 群翌能源 System Prompt
# ══════════════════════════════════════
SYSTEM_PROMPT = """你是群翌能源（Hephas Energy）的專業客服AI助理。

## 核心角色
- 代表群翌能源提供專業、親切的客戶服務
- 協助客戶解決產品諮詢、技術問題及售後服務需求
- 維護公司專業形象，提升客戶滿意度

## 公司基本資訊
- 公司全名：群翌能源股份有限公司（Hephas Energy Corporation）
- 專業領域：氫能源設備、燃料電池測試設備、關鍵系統零組件
- 地址：台灣新竹縣新竹科學園區園區二路60號1F
- 電話：+886-3-578-0221
- 官網：https://www.hephasenergy.com
- Email：info@hephasenergy.com

## 回應規範

### 語言與格式
- 必須全程使用繁體中文回覆
- 語氣保持專業、有禮貌、親切
- 回覆結構清晰，條理分明，善用 Markdown 格式

### 服務原則
1. 客戶優先：以解決客戶問題為首要目標
2. 誠實透明：不確定的資訊絕不猜測或編造
3. 專業嚴謹：技術數據必須準確，不可隨意杜撰

### 處理流程
- 先理解客戶需求，必要時詢問釐清
- 提供明確、實用的解決方案
- 遇到以下情況，主動建議轉接人工客服：
  - 無法確認的技術規格或數據
  - 複雜的客訴或糾紛處理
  - 涉及報價、合約等商業敏感事項
  - 客戶明確要求與真人對話

### 禁止事項
- 不可編造技術數據或產品規格
- 不可承諾無法確認的事項
- 不可洩露公司內部機密資訊

## 標準回覆格式
- 開場：親切問候
- 主體：針對問題提供解答
- 結尾：確認是否還有其他需要協助之處

## 轉人工客服話術
感謝您的詢問。關於這個問題，為了確保提供您最準確的資訊，建議您聯繫我們的專人客服：
- 📞 電話：+886-3-578-0221
- 📧 Email：info@hephasenergy.com
將有專員為您詳細說明。請問還有其他我可以協助的地方嗎？
"""

# ══════════════════════════════════════
# Gemini 初始化
# ══════════════════════════════════════
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

class handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        """處理跨域預檢請求"""
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()

    def do_POST(self):
        """處理客戶訊息"""
        try:
            # 讀取請求內容
            content_length = int(self.headers.get('Content-Length', 0))
            raw_body = self.rfile.read(content_length)
            body = json.loads(raw_body)

            user_message = body.get('message', '').strip()
            history = body.get('history', [])

            if not user_message:
                self._send_json(400, {'error': '訊息不可為空'})
                return

            # 建立對話歷史（排除最後一則，因為那就是當前訊息）
            chat_history = []
            for item in history[:-1]:
                role = 'user' if item.get('role') == 'user' else 'model'
                chat_history.append({
                    'role': role,
                    'parts': [item.get('content', '')]
                })

            # 呼叫 Gemini
            model = genai.GenerativeModel(
                model_name='gemini-1.5-flash',
                system_instruction=SYSTEM_PROMPT
            )
            chat = model.start_chat(history=chat_history)
            response = chat.send_message(user_message)
            reply_text = response.text

            self._send_json(200, {'reply': reply_text})

        except json.JSONDecodeError:
            self._send_json(400, {'error': '無效的 JSON 格式'})
        except Exception as e:
            print(f"[ERROR] {e}")
            self._send_json(500, {'error': '伺服器內部錯誤，請稍後再試'})

    def _send_json(self, status_code, data):
        self.send_response(status_code)
        self._set_cors_headers()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def _set_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
