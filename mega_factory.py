import os, json, requests, hashlib, time
from fpdf import FPDF
from datetime import datetime

# --- CONFIG ---
API_KEYS = os.getenv("OPENROUTER_API_KEYS", "").split(",")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
RUN_DURATION_SECONDS = 110 * 60 

SUBJECTS = {
    "GK_CurrentAffairs": "unique SSC level GK and May 2026 Current Affairs questions with clear answers.",
    "English": "unique SSC level English questions (Grammar, Vocab, Narration) with clear answers.",
    "Math": "unique SSC level Math questions. IMPORTANT: Provide a Short-Trick and a Full Step-by-Step Solution for EVERY question.",
    "Reasoning": "unique SSC level Reasoning questions with detailed logical explanations for each answer."
}

def fetch_content(subject_name, prompt_detail, key_index):
    current_key = API_KEYS[key_index].strip()
    full_prompt = f"Generate 20 {prompt_detail}. Plain text, no stars (**). Always include the answer immediately after each question."
    
    headers = {"Authorization": f"Bearer {current_key}", "Content-Type": "application/json"}
    data = {"model": "google/gemini-2.0-flash-001", "messages": [{"role": "user", "content": full_prompt}]}
    
    try:
        res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=50)
        if res.status_code in [429, 402]: return None, True
        return res.json()['choices'][0]['message']['content'].replace("**", ""), False
    except:
        return None, True

def create_and_send_pdf(content, subject):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, f"SSC {subject.upper()} - 100 Q&A BATCH", ln=True, align='C')
    pdf.ln(5)
    pdf.set_font("Arial", size=10)
    
    safe_text = content.encode('latin-1', 'replace').decode('latin-1')
    pdf.multi_cell(0, 7, safe_text)
    
    fname = f"{subject}_{datetime.now().strftime('%H%M%S')}.pdf"
    pdf.output(fname)
    
    with open(fname, "rb") as f:
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendDocument", 
                      data={"chat_id": TG_CHAT_ID}, files={"document": f})

def save_to_database(content, subject):
    db_file = "ssc_question_db.json"
    db = json.load(open(db_file)) if os.path.exists(db_file) else []
    db.append({
        "date": str(datetime.now()),
        "subject": subject,
        "content": content
    })
    # Keeps the file size manageable
    with open(db_file, "w") as f:
        json.dump(db[-10000:], f)

if __name__ == "__main__":
    start_time = time.time()
    key_idx = 0
    mem_file = "global_memory.json"
    memory = json.load(open(mem_file)) if os.path.exists(mem_file) else []

    for subject, prompt in SUBJECTS.items():
        if (time.time() - start_time) > RUN_DURATION_SECONDS: break
        if key_idx >= len(API_KEYS): break
        
        subject_accumulator = []
        print(f"Working on: {subject}")
        
        while len(subject_accumulator) < 5:
            if key_idx >= len(API_KEYS): break
            
            content, rotate = fetch_content(subject, prompt, key_idx)
            if rotate:
                key_idx += 1
                continue
            
            if content:
                h = hashlib.md5(content.encode()).hexdigest()
                if h not in memory:
                    subject_accumulator.append(content)
                    memory.append(h)
                    save_to_database(content, subject)
                    time.sleep(2)
        
        if len(subject_accumulator) >= 5:
            full_text = "\n\n".join(subject_accumulator)
            create_and_send_pdf(full_text, subject)
            # Update memory file immediately after each PDF
            with open(mem_file, "w") as f:
                json.dump(memory[-30000:], f)
    
