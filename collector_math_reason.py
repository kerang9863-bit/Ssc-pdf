import os, json, requests, hashlib
from fpdf import FPDF
from datetime import datetime

API_KEY = os.getenv("OPENROUTER_API_KEY")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
MEM_FILE = "mem_math_res.json"

def fetch_data():
    prompt = (
        "Generate 20 SSC MTS/CHSL level questions. 10 Quant and 10 Reasoning. "
        "Give Question, Options, Answer, 'Short-Trick', and 'Full Solution'. "
        "IMPORTANT: Do not use markdown like **bold**. Use plain text only."
    )
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    data = {"model": "google/gemini-2.0-flash-001", "messages": [{"role": "user", "content": prompt}]}
    res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data)
    content = res.json()['choices'][0]['message']['content']
    return content.replace("**", "")

def create_pdf(text):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.set_text_color(153, 0, 0) # Professional Red
    pdf.cell(0, 10, "SSC MATHS & REASONING (SOLVED)", ln=True, align='C')
    pdf.ln(5)
    pdf.set_font("Arial", size=10)
    pdf.set_text_color(0, 0, 0)
    safe_text = text.encode('latin-1', 'replace').decode('latin-1')
    pdf.multi_cell(0, 7, safe_text)
    fname = f"Math_Res_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    pdf.output(fname)
    return fname

def send_tg(path):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendDocument"
    with open(path, "rb") as f:
        requests.post(url, data={"chat_id": TG_CHAT_ID}, files={"document": f})

if __name__ == "__main__":
    content = fetch_data()
    h = hashlib.md5(content.encode()).hexdigest()
    if os.path.exists(MEM_FILE):
        with open(MEM_FILE, "r") as f:
            mem = json.load(f)
    else:
        mem = []

    if h not in mem:
        pdf_path = create_pdf(content)
        send_tg(pdf_path)
        mem.append(h)
        with open(MEM_FILE, "w") as f:
            json.dump(mem[-500:], f)
