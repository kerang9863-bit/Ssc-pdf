import os, json, requests, hashlib
from fpdf import FPDF
from datetime import datetime

API_KEY = os.getenv("OPENROUTER_API_KEY")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
MEM_FILE = "mem_math_res.json"

def fetch_data():
    prompt = (
        "Generate 20 SSC MTS/CHSL level questions. "
        "10 Quant: Arithmetic & Algebra. 10 Reasoning: Series, Syllogism, Blood Relations. "
        "For each: Give Question, Options, Answer, 'Short-Trick' Method, and 'Full Solution'."
    )
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    data = {"model": "google/gemini-2.0-flash-001", "messages": [{"role": "user", "content": prompt}]}
    res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data)
    return res.json()['choices'][0]['message']['content']

def create_pdf(text):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.set_text_color(153, 0, 0) # Dark Red for Math
    pdf.cell(0, 10, "SSC MATHS & REASONING (SOLVED)", ln=True, align='C')
    pdf.set_font("Arial", size=10)
    pdf.set_text_color(0, 0, 0)
    pdf.multi_cell(0, 7, text.encode('latin-1', 'replace').decode('latin-1'))
    fname = f"Math_Res_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    pdf.output(fname)
    return fname

def send_tg(path):
    requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendDocument", 
                  data={"chat_id": TG_CHAT_ID}, files={"document": open(path, "rb")})

if __name__ == "__main__":
    content = fetch_data()
    h = hashlib.md5(content.encode()).hexdigest()
    mem = json.load(open(MEM_FILE)) if os.path.exists(MEM_FILE) else []
    if h not in mem:
        f = create_pdf(content)
        send_tg(f)
        mem.append(h)
        json.dump(mem[-500:], open(MEM_FILE, "w"))
      
