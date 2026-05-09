import os, json, requests, hashlib
from fpdf import FPDF
from datetime import datetime

# --- CONFIG ---
API_KEY = os.getenv("OPENROUTER_API_KEY")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
MEM_FILE = "mem_gk_eng.json"

def fetch_data():
    prompt = (
        "Generate 40 SSC MTS/CHSL level questions. "
        "20 GK: History, Science, Static GK, and 2025-26 Current Affairs. "
        "20 English: Vocabulary (Synonyms/Antonyms), Error Spotting, and Idioms. "
        "Format: Q, Options, Ans, and a 1-sentence Fact/Rule."
    )
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    data = {"model": "google/gemini-2.0-flash-001", "messages": [{"role": "user", "content": prompt}]}
    res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data)
    return res.json()['choices'][0]['message']['content']

def create_pdf(text):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 10, "SSC GK & ENGLISH BANK", ln=True, align='C')
    pdf.set_font("Arial", size=11)
    pdf.set_text_color(0, 0, 0)
    pdf.multi_cell(0, 7, text.encode('latin-1', 'replace').decode('latin-1'))
    fname = f"GK_Eng_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    pdf.output(fname)
    return fname

def send_tg(path):
    requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendDocument", 
                  data={"chat_id": TG_CHAT_ID}, files={"document": open(path, "rb")})

if __name__ == "__main__":
    content = fetch_data()
    # Unique check via hash
    h = hashlib.md5(content.encode()).hexdigest()
    mem = json.load(open(MEM_FILE)) if os.path.exists(MEM_FILE) else []
    if h not in mem:
        f = create_pdf(content)
        send_tg(f)
        mem.append(h)
        json.dump(mem[-500:], open(MEM_FILE, "w")) # Keep last 500
