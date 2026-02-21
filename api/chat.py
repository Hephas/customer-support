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
必須全程使用繁體中文，語氣專業且有禮貌。
公司資訊：
- 電話：+886-3-578-0221
- Email：info@hephasenergy.com
- 地址：台灣新竹縣新竹科學園區園區二路60號1F"""

# 初始化 Gemini
try:
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        genai.configure(api_key=api_key)
except Exception as e:
    print(f"Gemini Init Error: {e}")

# 你提供的 Folder ID
DRIVE_FOLDER_ID = "1xbo0b0EW5gbIt2l8m0dOzORrL4k3-DgH"
MAX_FILES = 3
MAX_CHARS = 3500

def get_drive_service():
    # 這是最容易報錯的地方，增加 strip() 確保移除首尾空格/換行
    key_json_str = os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY")
    if not key_json_str:
        return None
    try:
        # 強制清理字串並解析 JSON
        key_data = key_json_str.strip()
        key_json = json.loads(key_data)
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
        downloader = MediaIoBaseDownload(buf, req)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        buf.seek(0)

        text = ""
        if mime == "application/pdf":
            reader = PdfReader(buf)
            text = "\n".join(p.extract_text() or "" for p in reader.pages)
        elif "word" in mime:
            doc = Document(buf)
            text = "\n".join(p.text for p in doc.paragraphs)
        elif "sheet" in mime:
            wb = openpyxl.load_workbook(buf, data_only=True)
            text = "\n".join([f"Sheet: {s}\n" + "\n".join(str(row) for row in wb[s].values) for s in wb.sheetnames])
        elif "presentation" in mime:
            prs = Presentation(buf)
            text = "\n".join([shape.text for slide in prs.slides for shape in slide.shapes if hasattr(shape, "text")])
        
        return f"📄 【{name}】\n{text[:MAX_CHARS]}"
    except Exception as e:
        return f"（讀取檔案 {name} 失敗）"

class handler(BaseHTTPRequestHandler):
    def _send_cors(self, status_code=200):
        self.send_response(status_code)
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

            # 檢索雲端硬碟
            context = ""
            drive = get_drive_service()
            if drive:
                q = f"'{DRIVE_FOLDER_ID}' in parents and trashed=false"
                res = drive.files().list(q=q, fields="files(id, name, mimeType)").execute()
                files = res.get("files", [])
                
                # 簡單關鍵字過濾
                relevant = [f for f in files if any(k in f['name'].lower() for k in user_msg.lower().split())]
                target_files = relevant[:MAX_FILES] if relevant else files[:1]
                
                context = "\n\n".join(extract_text(drive, f) for f in target_files)

            # 生成回答
            full_prompt = SYSTEM_PROMPT + (f"\n\n參考資料：\n{context}" if context else "")
            model = genai.GenerativeModel("gemini-1.5-flash", system_instruction=full_prompt)
            response = model.generate_content(user_msg)
            
            self._send_cors()
            self.wfile.write(json.dumps({"reply": response.text}, ensure_ascii=False).encode("utf-8"))

        except Exception as e:
            self._send_cors(500)
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
