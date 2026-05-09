import os, json, requests, hashlib, time
from fpdf import FPDF
from datetime import datetime

# --- CONFIG ---
# Enter keys as: sk-or-v1-xxx,sk-or-v1-yyy (no spaces)
API_KEYS = os.getenv("OPENROUTER_API_KEYS", "").split(",")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
RUN_DURATION_SECONDS = 110 * 60 # 1 hour 50 minutes to stay within 2hr window

def fetch_batch(key_index):
    current_key = API_KEYS[key_index].strip()
    prompt = (
        "Generate 20 unique SSC MTS/CHSL/CGL questions (Mixed: GK, English, Math, Reasoning). "
        "Include Current Affairs for May 2026. "
        "For Math/Reasoning: Provide Short-Tricks and Full Solutions. "
        "Format: Plain text only, NO markdown stars (**). "
        "Each question must include its category (GK, Math, etc.)"
    )
    headers = {"Authorization": f"Bearer {current_key}", "Content-Type": "application/json"}
    data = {
        "model": "google/gemini-2.0-flash-001", 
        "messages": [{"role": "user", "content": prompt}]
    }
    
    try:
        res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=40)
        if res.status_code in [429, 402]: 
            return None, True 
        return res.json()['choices'][0]['message']['content'].replace("**", ""), False
    except:
        return None, True

def create_and_send_pdf(batch_content, batch_number):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 10, f"SSC MEGA BATCH #{batch_number} - {datetime.now().strftime('%Y-%m-%d')}", ln=True, align='C')
    pdf.ln(5)
    pdf.set_font("Arial", size=10)
    pdf.set_text_color(0, 0, 0)
    
    safe_text = batch_content.encode('latin-1', 'replace').decode('latin-1')
    pdf.multi_cell(0, 7, safe_text)
    
    fname = f"SSC_Batch_{datetime.now().strftime('%H%M%S')}.pdf"
    pdf.output(fname)
    
    with open(fname, "rb") as f:
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendDocument", 
                      data={"chat_id": TG_CHAT_ID}, files={"document": f})
    return fname

def save_to_database(new_content):
    # This saves the actual text so you can build a web quiz later
    db_file = "ssc_question_db.json"
    db = json.load(open(db_file)) if os.path.exists(db_file) else []
    db.append({"date": str(datetime.now()), "content": new_content})
    # Keep only last 50,000 entries to stay under GitHub limits
    with open(db_file, "w") as f:
        json.dump(db[-50000:], f)

if __name__ == "__main__":
    start_time = time.time()
    batch_count = 1
    key_idx = 0
    batch_accumulator = []
    
    # Global memory for duplicate checking
    mem_file = "global_memory.json"
    memory = json.load(open(mem_file)) if os.path.exists(mem_file) else []

    while (time.time() - start_time) < RUN_DURATION_SECONDS:
        if key_idx >= len(API_KEYS):
            print("All keys used up.")
            break

        content, rotate = fetch_batch(key_idx)
        if rotate:
            key_idx += 1
            continue

        h = hashlib.md5(content.encode()).hexdigest()
        if h not in memory:
            batch_accumulator.append(content)
            memory.append(h)
            save_to_database(content)

            if len(batch_accumulator) >= 5: # Sends every 100 questions
                full_text = "\n\n---\n\n".join(batch_accumulator)
                create_and_send_pdf(full_text, batch_count)
                
                # Immediate memory sync to prevent loss if timed out
                with open(mem_file, "w") as f:
                    json.dump(memory[-20000:], f)
                
                batch_accumulator = []
                batch_count += 1
        
        time.sleep(2) 
