import pandas as pd
import requests
import json
import os
import random
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

SRS_FILE = "srs_progress.json"

# -----------------------------
# Load vocabulary from selected sheet
# -----------------------------
def load_vocabulary(sheet_name):
    """Load vocabulary from a specific sheet in the ODS file"""
    df = pd.read_excel(
        "DeutschVocabulary.ods",
        engine="odf",
        sheet_name=sheet_name,
        header=None
    )
    
    vocab_list = []
    for _, row in df.iterrows():
        row = list(row)
        for i in range(0, len(row) - 1, 2):
            german = row[i]
            english = row[i + 1]
            if pd.notna(german) and pd.notna(english):
                vocab_list.append((str(german).strip(), str(english).strip()))
    
    return vocab_list

# Global variable - will be set after sheet selection
vocab = []

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


def format_explanation(text):
    """Format explanation text for better readability"""
    lines = text.split('\n')
    formatted = []
    current_section = None
    example_index = 0
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Detect section headers
        if 'EXPLANATION:' in line:
            if formatted:
                formatted.append('')
            formatted.append('📖 EXPLANATION:')
            formatted.append('------------------------------------------------------------')
            current_section = 'explanation'
            continue
        elif 'EXAMPLE' in line:
            formatted.append('')
            formatted.append(line)
            formatted.append('------------------------------------------------------------')
            current_section = 'example'
            example_index = 0
            continue
        
        # Add proper formatting based on content
        if current_section == 'explanation':
            formatted.append('  ' + line)
        elif current_section == 'example':
            if line.startswith('DE:'):
                line_text = line[3:].strip()
                if example_index == 0:
                    formatted.append('    DE: ' + line_text)
                else:
                    formatted.append('    EN: ' + line_text)
            elif line.startswith('EN:'):
                formatted.append('    EN: ' + line[3:].strip())
            elif line.startswith('[') and line.endswith(']'):
                english = line[1:-1].strip()
                formatted.append('    EN: ' + english)
            else:
                if example_index == 0:
                    formatted.append('    DE: ' + line)
                else:
                    formatted.append('    EN: ' + line)
            example_index += 1
        else:
            formatted.append(line)
    
    # Build formatted output without outer borders
    result = '\n'.join(formatted)
    
    return result


def explain_word(german, english):
    prompt = f"""You are a friendly German teacher.

Word: {german}
Meaning: {english}

Give the answer in this exact format:

EXPLANATION:
[A simple short explanation in English]

EXAMPLE 1:
[German sentence]
[English translation]

EXAMPLE 2:
[German sentence]
[English translation]"""

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": "mistral", "prompt": prompt, "stream": False},
            timeout=20
        )
        explanation_text = response.json()["response"]
        # Format for better readability
        return format_explanation(explanation_text)
    except:
        return "(Explanation not available - Ollama is not running)"


# -----------------------------
# Sheet Selection Dialog
# -----------------------------
def select_sheet(parent=None):
    """Show sheet selection dialog and return selected sheet name"""
    if parent is None:
        selection_root = tk.Tk()
    else:
        selection_root = tk.Toplevel(parent)
        selection_root.transient(parent)
    
    selection_root.title("German Vocabulary Trainer - Select Category")
    selection_root.geometry("400x380")
    selection_root.resizable(False, False)
    selection_root.config(bg="#f0f0f0")
    
    selected_sheet = {"value": None}
    
    def on_sheet_selected(sheet_name):
        selected_sheet["value"] = sheet_name
        selection_root.destroy()
    
    # Title
    title_label = tk.Label(selection_root, text="Select a Category to Practice", font=("Helvetica", 16, "bold"), bg="#f0f0f0", fg="#1e3a8a")
    title_label.pack(pady=15)
    
    # Buttons for each sheet with different colors
    button_frame = tk.Frame(selection_root, bg="#f0f0f0", padx=20, pady=20)
    button_frame.pack(fill=tk.BOTH, expand=True)
    
    sheets = [("verben", "#ff6b6b"), ("Nomen", "#4ecdc4"), ("adjective", "#ffd93d"), ("redemittel", "#a78bfa")]
    
    for sheet, color in sheets:
        btn = tk.Button(
            button_frame,
            text=sheet.capitalize(),
            command=lambda s=sheet: on_sheet_selected(s),
            width=25,
            bg=color,
            fg="white",
            font=("Helvetica", 12, "bold"),
            relief=tk.RAISED,
            padx=10,
            pady=8,
            cursor="hand2"
        )
        btn.pack(pady=10)
    
    selection_root.grab_set()
    if parent is None:
        selection_root.mainloop()
    else:
        selection_root.wait_window()
    
    return selected_sheet["value"]


# -----------------------------
# GUI Application
# -----------------------------
class GermanSRSApp:
    def __init__(self, root, sheet_name):
        self.root = root
        self.root.title(f"German SRS Vocabulary Trainer - {sheet_name.capitalize()}")
        self.root.geometry("950x780")
        self.root.config(bg="#f8f9fa")

        self.current_step = 0
        self.current_german = None
        self.current_english = None

        # Configure custom styles
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Title.TLabel', font=("Helvetica", 14, "bold"), background="#f8f9fa", foreground="#1e3a8a")
        style.configure('Normal.TLabel', background="#f8f9fa")
        
        # GUI Setup
        main_frame = tk.Frame(root, bg="#f8f9fa", padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        self.status_label = tk.Label(main_frame, text="Loading...", font=("Helvetica", 12), bg="#f8f9fa", fg="#6b7280")
        self.status_label.pack(pady=8)

        tk.Label(main_frame, text="Translate this German word:", font=("Helvetica", 14, "bold"), bg="#f8f9fa", fg="#1e3a8a").pack(anchor="w")
        self.word_label = tk.Label(main_frame, text="", font=("Helvetica", 32, "bold"), bg="#e3f2fd", fg="#1565c0", padx=20, pady=15, relief=tk.RAISED, bd=2)
        self.word_label.pack(pady=20, fill=tk.X)

        tk.Label(main_frame, text="Your English meaning:", font=("Helvetica", 12, "bold"), bg="#f8f9fa", fg="#1e3a8a").pack(anchor="w")
        self.input_entry = tk.Entry(main_frame, font=("Helvetica", 16), width=60, bg="white", fg="#1e293b", relief=tk.SUNKEN, bd=2)
        self.input_entry.pack(pady=12, ipady=10)
        self.input_entry.bind("<Return>", lambda e: self.check_answer())

        # Buttons
        btn_frame = tk.Frame(main_frame, bg="#f8f9fa")
        btn_frame.pack(pady=15)

        self.submit_btn = tk.Button(btn_frame, text="✓ Submit Answer", command=self.check_answer, bg="#10b981", fg="white", font=("Helvetica", 11, "bold"), padx=15, pady=8, relief=tk.RAISED, cursor="hand2")
        self.submit_btn.pack(side=tk.LEFT, padx=8)

        self.hard_btn = tk.Button(btn_frame, text="⟲ Hard (Again later)", command=self.mark_hard, bg="#f59e0b", fg="white", font=("Helvetica", 11, "bold"), padx=15, pady=8, relief=tk.RAISED, cursor="hand2")
        self.hard_btn.pack(side=tk.LEFT, padx=8)

        self.change_btn = tk.Button(btn_frame, text="↺ Change Category", command=self.change_category, bg="#8b5cf6", fg="white", font=("Helvetica", 11, "bold"), padx=15, pady=8, relief=tk.RAISED, cursor="hand2")
        self.change_btn.pack(side=tk.LEFT, padx=8)

        # Feedback
        self.feedback_label = tk.Label(main_frame, text="", font=("Helvetica", 13), wraplength=750, bg="#f8f9fa", fg="#1e293b")
        self.feedback_label.pack(pady=12)

        # Explanation area
        tk.Label(main_frame, text="📚 Explanation & Examples:", font=("Helvetica", 12, "bold"), bg="#f8f9fa", fg="#1e3a8a").pack(anchor="w", pady=(10,5))
        self.explain_text = scrolledtext.ScrolledText(main_frame, height=14, font=("Helvetica", 11), wrap=tk.WORD, bg="#fffbeb", fg="#78350f", relief=tk.SUNKEN, bd=2)
        self.explain_text.pack(fill=tk.BOTH, expand=True, pady=5)

        self.next_btn = tk.Button(main_frame, text="→ Next Word", command=self.next_word, state="disabled", bg="#3b82f6", fg="white", font=("Helvetica", 12, "bold"), padx=20, pady=10, relief=tk.RAISED, cursor="hand2", disabledforeground="#9ca3af", activebackground="#1d4ed8")
        self.next_btn.pack(pady=15)

        self.next_word()   # Start first card

    def change_category(self):
        new_sheet = select_sheet(self.root)
        if new_sheet is None:
            return

        global vocab
        vocab = load_vocabulary(new_sheet)
        self.root.title(f"German SRS Vocabulary Trainer - {new_sheet.capitalize()}")
        self.current_step = 0
        self.current_german = None
        self.current_english = None
        self.feedback_label.config(text="", bg="#f8f9fa")
        self.explain_text.delete(1.0, tk.END)
        self.status_label.config(text="Category changed. Loading new words...")
        self.next_word()

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
            self.feedback_label.config(text="✅ Correct! Great job.", fg="#059669", bg="#d1fae5")
            explanation = explain_word(self.current_german, self.current_english)
            self.explain_text.insert(tk.END, explanation)
            update_srs(self.current_german, 2, self.current_step)   # Easy
        else:
            self.feedback_label.config(
                text=f"❌ Not quite right.\nCorrect meaning(s): {self.current_english}",
                fg="#dc2626",
                bg="#fee2e2"
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
    # Show sheet selection dialog
    selected_sheet = select_sheet()
    
    if selected_sheet is None:
        print("No sheet selected. Exiting.")
        exit()
    
    # Load vocabulary from selected sheet
    vocab = load_vocabulary(selected_sheet)
    print(f"Loaded {len(vocab)} words from '{selected_sheet}'\n")
    
    # Start the GUI
    root = tk.Tk()
    app = GermanSRSApp(root, selected_sheet)
    root.mainloop()
