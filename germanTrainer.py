import pandas as pd
import requests
import json
import os
import random
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

SRS_FILE = "srs_progress.json"

# -----------------------------
# Load vocabulary
# -----------------------------
df = pd.read_excel(
    "DeutschVocabulary.ods",
    engine="odf",
    header=None
)

vocab = []
for _, row in df.iterrows():
    row = list(row)
    for i in range(0, len(row) - 1, 2):
        german = row[i]
        english = row[i + 1]
        if pd.notna(german) and pd.notna(english):
            vocab.append((str(german).strip(), str(english).strip()))

print(f"Loaded {len(vocab)} words\n")

# -----------------------------
# Load / Save SRS
# -----------------------------
if os.path.exists(SRS_FILE):
    with open(SRS_FILE, "r") as f:
        srs = json.load(f)
else:
    srs = {}

def save_srs():
    with open(SRS_FILE, "w") as f:
        json.dump(srs, f, indent=2)

# -----------------------------
# SRS functions
# -----------------------------
def get_card(word):
    if word not in srs:
        srs[word] = {"interval": 1, "ease": 2.5, "due": 0}
    return srs[word]

def update_srs(word, quality, current_step):
    """quality: 0=wrong, 1=hard, 2=easy"""
    card = get_card(word)

    if quality == 0:        # Wrong
        card["interval"] = 1
        card["ease"] = max(1.3, card["ease"] - 0.2)
    elif quality == 1:      # Hard
        card["interval"] = int(card["interval"] * 1.5)
        card["ease"] = max(1.3, card["ease"] - 0.05)
    elif quality == 2:      # Easy
        card["interval"] = int(card["interval"] * card["ease"])
        card["ease"] += 0.1

    card["due"] = current_step + card["interval"]


# -----------------------------
# Checking functions (Improved & Stricter)
# -----------------------------
def fallback_check(user, english):
    user = user.lower().strip()
    if len(user) < 2:
        return False

    meanings = [m.strip().lower() for m in english.split(",") if m.strip()]
    
    for m in meanings:
        m_clean = m.replace("to ", "").replace("the ", "").strip()
        
        # Exact match
        if user == m or user == m_clean:
            return True
        
        # Good partial match (only if the key word is fully present)
        if len(m_clean) > 3 and m_clean in user and len(user) >= len(m_clean) - 2:
            return True

    return False


def ai_check(user, english):
    if not user or len(user.strip()) < 2:
        return False

    prompt = f"""You are a very strict German vocabulary examiner.

Correct meaning(s): {english}

User's answer: {user}

Rules (follow strictly):
- ONLY say YES if the user's answer clearly conveys the correct meaning.
- Accept good synonyms, but reject vague, incomplete, or partially correct answers.
- Reject answers that miss the main meaning.
- Be harsh and accurate.

Reply with exactly one word: YES or NO
No explanation. No extra text."""

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "mistral",
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.1}   # Makes it more strict and consistent
            },
            timeout=15
        )
        
        raw_response = response.json()["response"].strip()
        print(f"AI raw response: '{raw_response}'")   # Debugging line
        
        # Very strict check
        cleaned = raw_response.upper().strip()
        if cleaned.startswith("YES") and len(cleaned) <= 15:
            return True
        else:
            return False

    except Exception as e:
        print(f"Ollama error: {e}. Using fallback check...")
        return fallback_check(user, english)


def explain_word(german, english):
    prompt = f"""You are a friendly German teacher.

Word: {german}
Meaning: {english}

Give:
1. A simple short explanation in English
2. Two easy German A2-level example sentences with English translation"""

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": "mistral", "prompt": prompt, "stream": False},
            timeout=20
        )
        return response.json()["response"]
    except:
        return "(Explanation not available - Ollama is not running)"


# -----------------------------
# GUI Application
# -----------------------------
class GermanSRSApp:
    def __init__(self, root):
        self.root = root
        self.root.title("German SRS Vocabulary Trainer")
        self.root.geometry("850x720")

        self.current_step = 0
        self.current_german = None
        self.current_english = None

        # GUI Setup
        main_frame = ttk.Frame(root, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        self.status_label = ttk.Label(main_frame, text="Loading...", font=("Helvetica", 12))
        self.status_label.pack(pady=8)

        ttk.Label(main_frame, text="Translate this German word:", font=("Helvetica", 14, "bold")).pack(anchor="w")
        self.word_label = ttk.Label(main_frame, text="", font=("Helvetica", 28, "bold"), foreground="#1e88e5")
        self.word_label.pack(pady=20)

        ttk.Label(main_frame, text="Your English meaning:", font=("Helvetica", 12)).pack(anchor="w")
        self.input_entry = ttk.Entry(main_frame, font=("Helvetica", 16), width=60)
        self.input_entry.pack(pady=12, ipady=10)
        self.input_entry.bind("<Return>", lambda e: self.check_answer())

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(pady=15)

        self.submit_btn = ttk.Button(btn_frame, text="Submit Answer", command=self.check_answer)
        self.submit_btn.pack(side=tk.LEFT, padx=8)

        self.hard_btn = ttk.Button(btn_frame, text="Hard (Again later)", command=self.mark_hard)
        self.hard_btn.pack(side=tk.LEFT, padx=8)

        # Feedback
        self.feedback_label = ttk.Label(main_frame, text="", font=("Helvetica", 14), wraplength=750)
        self.feedback_label.pack(pady=12)

        # Explanation area
        ttk.Label(main_frame, text="Explanation & Examples:", font=("Helvetica", 12, "bold")).pack(anchor="w", pady=(10,5))
        self.explain_text = scrolledtext.ScrolledText(main_frame, height=14, font=("Helvetica", 11), wrap=tk.WORD)
        self.explain_text.pack(fill=tk.BOTH, expand=True, pady=5)

        self.next_btn = ttk.Button(main_frame, text="Next Word →", command=self.next_word, state="disabled")
        self.next_btn.pack(pady=15)

        self.next_word()   # Start first card

    def get_due_words(self):
        return [(g, e) for g, e in vocab if get_card(g)["due"] <= self.current_step]

    def next_word(self):
        due_words = self.get_due_words()

        if not due_words:
            messagebox.showinfo("🎉 Session Complete", "No more words are due today!\nWell done!")
            self.root.quit()
            return

        self.current_german, self.current_english = random.choice(due_words)

        self.word_label.config(text=self.current_german)
        self.input_entry.delete(0, tk.END)
        self.feedback_label.config(text="")
        self.explain_text.delete(1.0, tk.END)
        self.next_btn.config(state="disabled")
        self.submit_btn.config(state="normal")
        self.hard_btn.config(state="normal")

        self.status_label.config(
            text=f"Due words: {len(due_words)}   |   Step: {self.current_step}"
        )

    def check_answer(self):
        if not self.current_german:
            return

        user = self.input_entry.get().strip()
        if not user:
            messagebox.showwarning("Empty", "Please type your answer.")
            return

        is_correct = ai_check(user, self.current_english)

        if is_correct:
            self.feedback_label.config(text="✅ Correct! Great job.", foreground="green")
            explanation = explain_word(self.current_german, self.current_english)
            self.explain_text.insert(tk.END, explanation)
            update_srs(self.current_german, 2, self.current_step)   # Easy
        else:
            self.feedback_label.config(
                text=f"❌ Not quite right.\nCorrect meaning(s): {self.current_english}",
                foreground="red"
            )
            update_srs(self.current_german, 0, self.current_step)   # Wrong

        save_srs()
        self.submit_btn.config(state="disabled")
        self.hard_btn.config(state="disabled")
        self.next_btn.config(state="normal")

    def mark_hard(self):
        if self.current_german:
            update_srs(self.current_german, 1, self.current_step)   # Hard
            save_srs()
            self.next_word()


# -----------------------------
# Run the app
# -----------------------------
if __name__ == "__main__":
    root = tk.Tk()
    app = GermanSRSApp(root)
    root.mainloop()
