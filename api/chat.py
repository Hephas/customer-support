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

# --- 設定區 ---
SYSTEM_PROMPT = """你是群翌能源（Hephas Energy）的專業客服AI助理。
優先根據提供的文件資料回答。文件中找不到答案時，請禮貌告知並建議聯繫專人。
必須全程使用繁體中文，語氣專業親切。"""

# 初始化 Gemini
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

DRIVE_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "")
MAX_FILES = 3
MAX_CHARS = 3500

def get_drive_service():
    # 改為直接讀取 JSON 字串，不再使用 Base64
    key_json_str = os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY", "")
    if not key_json_str:
        print("[Error] 找不到 GOOGLE_SERVICE_ACCOUNT_KEY 環境變數")
        return None
    try:
        key_json = json.loads(key_json_str)
        creds = service_account.Credentials.from_service_account_info(
            key_json,
            scopes=["https://www.googleapis.com/auth/drive.readonly"]
        )
        return build("drive", "v3", credentials=creds)
    except Exception as e:
        print(f"[Drive Init Error] {e}")
        return None

def search_relevant_files(service, query):
    try:
        # 搜尋指定資料夾內的檔案
        query_str = f"'{DRIVE_FOLDER_ID}' in parents and trashed=false"
        results = service.files().list(q=query_str, fields="files(id, name, mimeType)").execute()
        files = results.get("files", [])
        
        # 簡單的關鍵字匹配邏輯
        keywords = [k.lower() for k in query.split() if len(k) > 1]
        scored = []
        for f in files:
            score = sum(2 for kw in keywords if kw in f["name"].lower()) # 檔名匹配加分
            scored.append((score, f))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [f for score, f in scored[:MAX_FILES]]
    except Exception as e:
        print(f"[Search Error] {e}")
        return []

def extract_text(service, file_info):
    mime = file_info["mimeType"]
    fid = file_info["id"]
    name = file_info["name"]
    try:
        # 處理 Google 原生文件 (Doc/Sheet/Slide)
        if "google-apps" in mime:
            export_mime = "text/plain" if "spreadsheet" not in mime else "text/csv"
            content = service.files().export(fileId=fid, mimeType=export_mime).execute()
            return f"📄 【{name}】\n{content.decode('utf-8')[:MAX_CHARS]}"
        
        # 處理二進位檔案 (PDF/Word/Excel)
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
            text = "\n".join(p.extract_text() for p in reader.pages)
        elif "word" in mime:
            doc = Document(buf)
            text = "\n".join(p.text for p in doc.paragraphs)
        elif "sheet" in mime:
            wb = openpyxl.load_workbook(buf, data_only=True)
            text = "\n".join([f"Sheet: {s}\n" + "\n".join(str(row) for row in wb[s].values) for s in wb.sheetnames])
        
        return f"📄 【{name}】\n{text[:MAX_CHARS]}"
    except Exception as e:
        return f"（讀取檔案 {name} 失敗: {str(e)}）"

class handler(BaseHTTPRequestHandler):
    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_POST(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(content_length))
            user_msg = body.get("message", "")

            # 1. 抓取雲端硬碟資料
            context_text = ""
            drive = get_drive_service()
            if drive:
                relevant_files = search_relevant_files(drive, user_msg)
                context_text = "\n\n".join(extract_text(drive, f) for f in relevant_files)

            # 2. 組合 Prompt 並呼叫 Gemini
            full_prompt = SYSTEM_PROMPT
            if context_text:
                full_prompt += f"\n\n參考公司文件內容：\n{context_text}"
            
            model = genai.GenerativeModel("gemini-1.5-flash", system_instruction=full_prompt)
            response = model.generate_content(user_msg)
            
            # 3. 回傳結果
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"reply": response.text}).encode("utf-8"))

        except Exception as e:
            self.send_response(500)
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
