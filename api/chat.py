import os
import io
import json
import google.generativeai as genai
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
from http.server import BaseHTTPRequestHandler
from PyPDF2 import PdfReader
from docx import Document
import openpyxl
from pptx import Presentation

# --- 群翌能源 (Hephas Energy) 官方設定 ---
SYSTEM_PROMPT = """你是群翌能源（Hephas Energy）的專業客服AI助理。
優先根據提供的文件資料回答。文件中找不到答案時，請禮貌告知並建議聯繫專人。
必須全程使用繁體中文（台灣習慣），語氣專業且有禮貌。
公司資訊：
- 電話：+886-3-578-0221
- Email：info@hephasenergy.com
- 地址：台灣新竹縣新竹科學園區園區二路60號1F"""

# 你提供的設定值
DRIVE_FOLDER_ID = "1xbo0b0EW5gbIt2l8m0dOzORrL4k3-DgH"
MAX_FILES = 3
MAX_CHARS = 3500

# 初始化 Gemini
try:
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        genai.configure(api_key=api_key)
except Exception as e:
    print(f"Gemini Init Error: {e}")

def get_drive_service():
    # 直接讀取 Vercel Environment Variables 裡的原始 JSON 字串
    key_json_str = os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY")
    if not key_json_str:
        return None
    try:
        # 這裡最容易出錯，如果 JSON 格式不對會噴 500
        key_json = json.loads(key_json_str.strip())
        creds = service_account.Credentials.from_service_account_info(
            key_json,
            scopes=["https://www.googleapis.com/auth/drive.readonly"]
        )
        return build("drive", "v3", credentials=creds)
    except Exception as e:
        print(f"Drive Auth Error: {e}")
        return None

def extract_text(service, file_info):
    mime = file_info["mimeType"]
    fid = file_info["id"]
    name = file_info["name"]
    try:
        if "google-apps" in mime:
            export_mime = "text/plain" if "spreadsheet" not in mime else "text/csv"
            content = service.files().export(fileId=fid, mimeType=export_mime).execute()
            return f"📄 【{name}】\n{content.decode('utf-8')[:MAX_CHARS]}"
        
        buf = io.BytesIO()
        req = service.files().get_media(fileId=fid)
        MediaIoBaseDownload(buf, req).get_media() # 簡化下載邏輯
        buf.seek(0)

        text = ""
        if mime == "application/pdf":
            reader = PdfReader(buf)
            text = "\n".join(p.extract_text() or "" for p in reader.pages)
        elif "word" in mime:
            text = "\n".join(p.text for p in Document(buf).paragraphs)
        elif "sheet" in mime:
            ws = openpyxl.load_workbook(buf, data_only=True).active
            text = "\n".join("\t".join(str(c) for c in r if c) for r in ws.values if r)
        elif "presentation" in mime:
            text = "\n".join(shape.text for slide in Presentation(buf).slides for shape in slide.shapes if hasattr(shape, "text"))
        
        return f"📄 【{name}】\n{text[:MAX_CHARS]}"
    except:
        return f"（讀取檔案 {name} 失敗）"

class handler(BaseHTTPRequestHandler):
    def _send_cors(self, code=200):
        self.send_response(code)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()

    def do_OPTIONS(self):
        self._send_cors()

    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length))
            user_msg = body.get("message", "")

            # 檢索雲端資料
            context = ""
            service = get_drive_service()
            if service:
                q = f"'{DRIVE_FOLDER_ID}' in parents and trashed=false"
                res = service.files().list(q=q, fields="files(id, name, mimeType)").execute()
                files = res.get("files", [])
                # 簡單匹配：檔名包含用戶關鍵字
                relevant = [f for f in files if any(k in f['name'].lower() for k in user_msg.lower().split())][:MAX_FILES]
                if not relevant: relevant = files[:1] # 若無匹配，保底取一個檔案
                context = "\n\n".join(extract_text(service, f) for f in relevant)

            prompt = SYSTEM_PROMPT + (f"\n\n參考資料：\n{context}" if context else "")
            model = genai.GenerativeModel("gemini-1.5-flash", system_instruction=prompt)
            reply = model.generate_content(user_msg).text
            
            self._send_cors()
            self.wfile.write(json.dumps({"reply": reply}, ensure_ascii=False).encode("utf-8"))

        except Exception as e:
            self._send_cors(500)
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
