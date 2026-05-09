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
PROVIDERS = []

groq_keys = [k.strip() for k in os.getenv("GROQ_API_KEYS", "").split(",") if k.strip()]
for key in groq_keys:
    PROVIDERS.append({
        "name": "Groq",
        "key": key,
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "model": "llama-3.3-70b-versatile",
        "headers": {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        "format": "openai"
    })

openrouter_keys = [k.strip() for k in os.getenv("OPENROUTER_API_KEYS", "").split(",") if k.strip()]
for key in openrouter_keys:
    PROVIDERS.append({
        "name": "OpenRouter",
        "key": key,
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "model": "google/gemini-2.0-flash-001",
        "headers": {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com",
            "X-Title": "SSC Factory"
        },
        "format": "openai"
    })

gemini_keys = [k.strip() for k in os.getenv("GEMINI_API_KEYS", "").split(",") if k.strip()]
for key in gemini_keys:
    PROVIDERS.append({
        "name": "Gemini",
        "key": key,
        "url": f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}",
        "model": "gemini-2.0-flash",
        "headers": {"Content-Type": "application/json"},
        "format": "gemini"
    })

TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
RUN_DURATION_SECONDS = 110 * 60

SUBJECTS = {
    "GK_CurrentAffairs": "unique SSC level GK questions based on established facts and general knowledge. Focus on Indian history, geography, polity, science, and static GK. Do NOT include speculative future events or placeholder notes.",
    "English": "unique SSC level English questions (Grammar, Vocab, Narration) with clear answers.",
    "Math": "unique SSC level Math questions. IMPORTANT: Provide a Short-Trick and a Full Step-by-Step Solution for EVERY question.",
    "Reasoning": "unique SSC level Reasoning questions with detailed logical explanations for each answer."
}

# --- UTILITIES ---

def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def load_json_safe(filepath: str, default=None):
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
    tmp = f"{filepath}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, filepath)
    log(f"Saved {filepath} ({len(json.dumps(data))} bytes)")

def validate_batch(content: str) -> Tuple[bool, str]:
    if not content:
        return False, "Empty content"
    if len(content) < 500:
        return False, f"Content too short ({len(content)} chars)"

    questions = re.findall(r'(?:^|\n)(?:Q?\d+[\.\)\:]\s*)', content, re.IGNORECASE)
    if len(questions) < 3:
        questions = re.findall(r'(?:^|\n)\d+[\.\)\:]', content)

    answers = re.findall(r'(?i)(?:^|\n)(?:ans(?:wer)?[\:\s]|solution[\:\s]|short\s*trick|correct\s*answer|explanation[\:\s])', content)

    if "needs future information" in content.lower() or "placeholder" in content.lower():
        return False, "Contains placeholder/future speculation"

    if len(questions) < 3 and len(answers) < 3:
        return False, f"Only {len(questions)} questions, {len(answers)} answers detected"

    return True, f"OK: ~{len(questions)} questions, ~{len(answers)} answers"

# --- CORE FUNCTIONS ---

def fetch_content(subject: str, prompt_detail: str, provider_idx: int, retries: int = 3) -> Tuple[Optional[str], bool]:
    if provider_idx >= len(PROVIDERS):
        return None, True

    provider = PROVIDERS[provider_idx]
    log(f"Using provider: {provider['name']} (key {provider_idx+1}/{len(PROVIDERS)})")

    full_prompt = (
        "Generate 20 " + prompt_detail + "\n\n"
        "CRITICAL FORMAT RULES:\n"
        "1. Every question MUST start with Q1. , Q2. , Q3. etc. on its own line\n"
        "2. The answer MUST be on the NEXT line, starting with Ans: \n"
        "3. Example format (STRICT - each on separate line):\n"
        "   Q1. What is the capital of France?\n"
        "   Ans: Paris\n"
        "   Q2. A train 200m long crosses a platform in 30 seconds at 36 km/hr. Find platform length?\n"
        "   Ans: 100 meters\n"
        "   Q3. [Next question on its own line]\n"
        "   Ans: [Answer on its own line]\n"
        "4. For Math: After Ans:, add Short Trick: then Solution: each on new lines\n"
        "5. NO markdown, NO **, NO tables, NO placeholder notes\n"
        "6. Each question and answer must be on SEPARATE lines - never on same line"
    )

    for attempt in range(retries):
        try:
            if provider["format"] == "gemini":
                data = {
                    "contents": [{"parts": [{"text": full_prompt}]}],
                    "generationConfig": {"temperature": 0.7}
                }
            else:
                data = {
                    "model": provider["model"],
                    "messages": [{"role": "user", "content": full_prompt}],
                    "temperature": 0.7
                }

            res = requests.post(
                provider["url"],
                headers=provider["headers"],
                json=data,
                timeout=50
            )

            if res.status_code in [429, 402]:
                log(f"{provider['name']} key exhausted (HTTP {res.status_code})")
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

            if provider["format"] == "gemini":
                content = payload["candidates"][0]["content"]["parts"][0]["text"].replace("**", "")
            else:
                content = payload["choices"][0]["message"]["content"].replace("**", "")

            preview = content[:300].replace("\n", " | ")
            log(f"DEBUG Response preview: {preview}")

            valid, reason = validate_batch(content)
            if not valid:
                log(f"Validation failed: {reason}")
                time.sleep(2)
                continue

            return content, False

        except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
            log(f"Request error on {provider['name']} (attempt {attempt+1}): {e}")
            time.sleep(2 ** attempt)
        except Exception as e:
            log(f"UNEXPECTED ERROR on {provider['name']}: {e}")
            raise

    return None, False

def create_pdf(content: str, subject: str) -> str:
    """PDF with proper layout: questions wrap, answers below, nothing cut off."""
    pdf = FPDF()
    pdf.add_page()

    # Wider margins for more text space
    pdf.set_margins(12, 12, 12)
    pdf.set_auto_page_break(auto=True, margin=15)

    font_name = "Arial"

    # Header
    pdf.set_font(font_name, 'B', 16)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 10, f"SSC {subject.upper()} PRACTICE SET", ln=True, align='C')
    pdf.set_font(font_name, '', 9)
    pdf.set_text_color(128, 128, 128)
    pdf.cell(0, 5, f"Generated: {datetime.now().strftime('%d %b %Y, %H:%M')}", ln=True, align='C')
    pdf.ln(4)

    # Available width for text
    text_width = pdf.w - pdf.l_margin - pdf.r_margin

    for raw_line in content.split('\n'):
        line = raw_line.strip()
        if not line:
            continue

        # Check if this is an answer line
        is_answer = any(line.lower().startswith(x) for x in [
            'ans:', 'answer:', 'solution:', 'short trick:', 
            'explanation:', 'correct answer:'
        ])

        # Check if it's a numbered step (like "1. Division: 5/10 = 0.5")
        is_numbered_step = re.match(r'^\d+[\.\)]\s+[A-Za-z]', line) and any(x in line.lower() for x in ['division', 'multiplication', 'addition', 'subtraction', 'step', 'calculation'])
        if is_numbered_step:
            is_answer = True

        is_question = re.match(r'^Q?\d+[\.\)\:]', line) or line.lower().startswith('question')

        # Pre-encode to latin-1 to prevent any Unicode crashes
        safe_line = line.encode('latin-1', 'replace').decode('latin-1')

        if is_question:
            # Question: bold, black, with spacing before
            pdf.set_text_color(0, 0, 0)
            pdf.set_font(font_name, 'B', 10)
            pdf.ln(3)
            pdf.multi_cell(text_width, 6, safe_line)

        elif is_answer:
            # Answer: bold, green, indented slightly, with spacing
            pdf.set_text_color(0, 128, 0)
            pdf.set_font(font_name, 'B', 10)
            pdf.set_x(pdf.l_margin + 5)  # Slight indent
            pdf.multi_cell(text_width - 5, 6, safe_line)
            pdf.ln(1)

        else:
            # Other text (explanations, etc): normal, gray
            pdf.set_text_color(50, 50, 50)
            pdf.set_font(font_name, '', 9)
            pdf.set_x(pdf.l_margin + 5)
            pdf.multi_cell(text_width - 5, 5, safe_line)

    fname = f"{subject}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    pdf.output(fname)
    log(f"PDF created: {fname}")
    return fname

def send_to_telegram(filepath: str, subject: str) -> bool:
    if not TG_TOKEN or not TG_CHAT_ID:
        log("Telegram credentials missing!")
        return False

    try:
        with open(filepath, "rb") as f:
            resp = requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendDocument",
                data={
                    "chat_id": TG_CHAT_ID,
                    "caption": f"SSC {subject} Practice Set\n{datetime.now().strftime('%d %b %Y')}"
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
    provider_idx = 0
    memory = load_json_safe("global_memory.json")

    if not PROVIDERS:
        log("FATAL: No API providers configured")
        log("Set GROQ_API_KEYS, OPENROUTER_API_KEYS, or GEMINI_API_KEYS")
        exit(1)

    log(f"Starting SSC Factory with {len(PROVIDERS)} provider keys")
    log(f"Max runtime: {RUN_DURATION_SECONDS/60:.0f} minutes")

    for subject, prompt in SUBJECTS.items():
        elapsed = time.time() - start_time
        if elapsed > RUN_DURATION_SECONDS:
            log(f"Time limit reached ({elapsed/60:.1f}m)")
            break

        if provider_idx >= len(PROVIDERS):
            log("All providers exhausted")
            break

        log(f"\n{'='*50}")
        log(f"SUBJECT: {subject}")
        log(f"{'='*50}")

        accumulator = []
        attempts = 0
        max_attempts = 30

        while len(accumulator) < 5 and attempts < max_attempts:
            attempts += 1
            log(f"Fetching batch {len(accumulator)+1}/5 (attempt {attempts})...")

            content, rotate = fetch_content(subject, prompt, provider_idx)

            if rotate:
                provider_idx += 1
                if provider_idx >= len(PROVIDERS):
                    log("No more providers")
                    break
                continue

            if not content:
                continue

            h = hashlib.md5(content.encode()).hexdigest()
            if h in memory:
                log(f"Duplicate detected (hash: {h[:8]}...), skipping")
                continue

            accumulator.append(content)
            memory.append(h)
            save_to_database(content, subject)
            save_json_atomic("global_memory.json", memory[-30000:])
            log(f"Batch saved ({len(content)} chars)")
            time.sleep(2)

        if len(accumulator) >= 5:
            full_text = "\n\n".join(accumulator)
            try:
                pdf_path = create_pdf(full_text, subject)
                success = send_to_telegram(pdf_path, subject)
                if success:
                    log(f"{subject} COMPLETE")
                else:
                    log(f"{subject} PDF saved locally (Telegram failed)")
            except Exception as e:
                log(f"PDF creation failed for {subject}: {e}")
        else:
            log(f"{subject} INCOMPLETE: only {len(accumulator)}/5 batches")

    save_json_atomic("global_memory.json", memory[-30000:])
    log(f"Final memory saved: {len(memory)} entries")

    log("Files in directory:")
    for f in os.listdir('.'):
        if f.endswith(('.json', '.pdf')):
            size = os.path.getsize(f)
            log(f"  {f}: {size} bytes")

    total_time = time.time() - start_time
    log(f"\nFactory complete. Runtime: {total_time/60:.1f} minutes")
