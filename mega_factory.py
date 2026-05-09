import os
import json
import requests
import hashlib
import time
import re
import random
from fpdf import FPDF
from datetime import datetime
from typing import Optional, Tuple

# --- CONFIG ---
API_KEYS = [k.strip() for k in os.getenv("OPENROUTER_API_KEYS", "").split(",") if k.strip()]
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
RUN_DURATION_SECONDS = 110 * 60

SUBJECTS = {
    "GK_CurrentAffairs": "unique SSC level GK and May 2026 Current Affairs questions with clear answers.",
    "English": "unique SSC level English questions (Grammar, Vocab, Narration) with clear answers.",
    "Math": "unique SSC level Math questions. IMPORTANT: Provide a Short-Trick and a Full Step-by-Step Solution for EVERY question.",
    "Reasoning": "unique SSC level Reasoning questions with detailed logical explanations for each answer."
}

# --- UTILITIES ---

def log(msg: str) -> None:
    """Timestamped logging for GitHub Actions visibility."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def load_json_safe(filepath: str, default=None):
    """Load JSON with corruption recovery."""
    if not os.path.exists(filepath):
        return default if default is not None else []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        log(f"CORRUPTED {filepath}: {e}")
        backup = f"{filepath}.corrupt.{int(time.time())}"
        os.rename(filepath, backup)
        return default if default is not None else []

def save_json_atomic(filepath: str, data) -> None:
    """Atomic write to prevent corruption during crashes."""
    tmp = f"{filepath}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, filepath)

def validate_batch(content: str) -> Tuple[bool, str]:
    """Ensure AI output meets minimum standards."""
    if not content:
        return False, "Empty content"
    if len(content) < 800:
        return False, f"Content too short ({len(content)} chars)"
    
    questions = re.findall(r'^\d+[\.\)]\s', content, re.MULTILINE)
    if len(questions) < 8:
        return False, f"Only {len(questions)} questions detected"
    
    answers = re.findall(r'(?i)ans(?:wer)?[:\s]', content)
    if len(answers) < 5:
        return False, f"Only {len(answers)} answers detected"
    
    return True, f"OK: {len(questions)} questions, {len(answers)} answers"

# --- CORE FUNCTIONS ---

def fetch_content(subject: str, prompt_detail: str, key_idx: int, retries: int = 3) -> Tuple[Optional[str], bool]:
    """Fetch content from OpenRouter with retry logic."""
    if key_idx >= len(API_KEYS):
        return None, True
    
    current_key = API_KEYS[key_idx]
    full_prompt = (
        f"Generate 20 {prompt_detail}\n\n"
        f"STRICT REQUIREMENTS:\n"
        f"- Plain text ONLY. No markdown, no bold/italic markers (**), no tables.\n"
        f"- Format each question as: Q1. [Question text] Ans: [Answer text]\n"
        f"- For Math: Include 'Short Trick:' and 'Solution:' for every question.\n"
        f"- Number sequentially from 1 to 20.\n"
        f"- Ensure every question has a clearly marked answer."
    )
    
    headers = {
        "Authorization": f"Bearer {current_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com",
        "X-Title": "SSC Factory"
    }
    data = {
        "model": "google/gemini-2.0-flash-001",
        "messages": [{"role": "user", "content": full_prompt}],
        "temperature": 0.7
    }
    
    for attempt in range(retries):
        try:
            res = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=data,
                timeout=50
            )
            
            if res.status_code in [429, 402]:
                log(f"Key {key_idx} exhausted (HTTP {res.status_code})")
                return None, True
            
            if res.status_code >= 500:
                wait = (2 ** attempt) + random.uniform(0, 1)
                log(f"Server error {res.status_code}, retrying in {wait:.1f}s...")
                time.sleep(wait)
                continue
            
            if not res.ok:
                log(f"API error {res.status_code}: {res.text[:200]}")
                return None, False
            
            payload = res.json()
            content = payload['choices'][0]['message']['content'].replace("**", "")
            
            valid, reason = validate_batch(content)
            if not valid:
                log(f"Validation failed: {reason}")
                time.sleep(2)
                continue
            
            return content, False
            
        except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
            log(f"Request error (attempt {attempt+1}): {e}")
            time.sleep(2 ** attempt)
        except Exception as e:
            log(f"UNEXPECTED ERROR: {e}")
            raise
    
    return None, False

def create_pdf(content: str, subject: str) -> str:
    """Generate a formatted PDF with color-coded answers and Unicode support."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # Add Unicode font (pre-installed on Ubuntu runners)
    try:
        pdf.add_font("DejaVu", "", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", uni=True)
        pdf.add_font("DejaVu", "B", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", uni=True)
        font_name = "DejaVu"
    except Exception:
        font_name = "Arial"  # Fallback
    
    # Header
    pdf.set_font(font_name, 'B', 18)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 12, f"SSC {subject.upper()} PRACTICE SET", ln=True, align='C')
    pdf.set_font(font_name, '', 10)
    pdf.set_text_color(128, 128, 128)
    pdf.cell(0, 6, f"Generated: {datetime.now().strftime('%d %b %Y, %H:%M')}", ln=True, align='C')
    pdf.ln(5)
    
    # Content with color coding
    for line in content.split('\n'):
        line = line.strip()
        if not line:
            continue
        
        is_answer = any(x in line.lower() for x in ['ans:', 'answer:', 'solution:', 'short trick:'])
        is_question = re.match(r'^\d+[\.\)]\s', line)
        
        if is_answer:
            pdf.set_text_color(0, 128, 0)
            pdf.set_font(font_name, 'B', 10)
        elif is_question:
            pdf.set_text_color(0, 0, 0)
            pdf.set_font(font_name, 'B', 10)
            pdf.ln(2)
        else:
            pdf.set_text_color(50, 50, 50)
            pdf.set_font(font_name, '', 10)
        
        pdf.multi_cell(0, 6, line)
    
    fname = f"{subject}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    pdf.output(fname)
    return fname

def send_to_telegram(filepath: str, subject: str) -> bool:
    """Send PDF to Telegram with proper error handling."""
    if not TG_TOKEN or not TG_CHAT_ID:
        log("Telegram credentials missing!")
        return False
    
    try:
        with open(filepath, "rb") as f:
            resp = requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendDocument",
                data={
                    "chat_id": TG_CHAT_ID,
                    "caption": f"📚 SSC {subject} Practice Set\n📅 {datetime.now().strftime('%d %b %Y')}"
                },
                files={"document": f},
                timeout=30
            )
            if resp.ok:
                log(f"Telegram sent: {filepath}")
                return True
            else:
                log(f"Telegram failed HTTP {resp.status_code}: {resp.text[:200]}")
                return False
    except Exception as e:
        log(f"Telegram error: {e}")
        return False

def save_to_database(content: str, subject: str) -> None:
    """Persist question batch to JSON database with hash for recovery."""
    db = load_json_safe("ssc_question_db.json", [])
    db.append({
        "timestamp": datetime.now().isoformat(),
        "subject": subject,
        "hash": hashlib.md5(content.encode()).hexdigest(),
        "content": content
    })
    save_json_atomic("ssc_question_db.json", db[-10000:])

# --- MAIN ---

if __name__ == "__main__":
    start_time = time.time()
    key_idx = 0
    memory = load_json_safe("global_memory.json")
    
    if not API_KEYS:
        log("FATAL: No API keys found in OPENROUTER_API_KEYS")
        exit(1)
    
    log(f"🚀 SSC Factory starting with {len(API_KEYS)} API keys")
    log(f"⏱️  Max runtime: {RUN_DURATION_SECONDS/60:.0f} minutes")
    
    for subject, prompt in SUBJECTS.items():
        elapsed = time.time() - start_time
        if elapsed > RUN_DURATION_SECONDS:
            log(f"⏰ Time limit reached ({elapsed/60:.1f}m)")
            break
        
        if key_idx >= len(API_KEYS):
            log("🔑 All API keys exhausted")
            break
        
        log(f"\n{'='*50}")
        log(f"📖 SUBJECT: {subject}")
        log(f"{'='*50}")
        
        accumulator = []
        attempts = 0
        max_attempts = 25
        
        while len(accumulator) < 5 and attempts < max_attempts:
            attempts += 1
            log(f"Fetching batch {len(accumulator)+1}/5 (attempt {attempts})...")
            
            content, rotate = fetch_content(subject, prompt, key_idx)
            
            if rotate:
                key_idx += 1
                if key_idx >= len(API_KEYS):
                    log("No more API keys")
                    break
                continue
            
            if not content:
                continue
            
            h = hashlib.md5(content.encode()).hexdigest()
            if h in memory:
                log(f"♻️ Duplicate detected (hash: {h[:8]}...), skipping")
                continue
            
            accumulator.append(content)
            memory.append(h)
            save_to_database(content, subject)
            save_json_atomic("global_memory.json", memory[-30000:])
            log(f"✅ Batch saved ({len(content)} chars)")
            time.sleep(2)
        
        if len(accumulator) >= 5:
            full_text = "\n\n".join(accumulator)
            pdf_path = create_pdf(full_text, subject)
            success = send_to_telegram(pdf_path, subject)
            if success:
                log(f"🎉 {subject} COMPLETE")
            else:
                log(f"⚠️ {subject} PDF saved locally (Telegram failed)")
        else:
            log(f"❌ {subject} INCOMPLETE: only {len(accumulator)}/5 batches")
    
    total_time = time.time() - start_time
    log(f"\n🏭 Factory complete. Runtime: {total_time/60:.1f} minutes")
