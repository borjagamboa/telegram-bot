import re
import time
import threading
import difflib

def animated_loading(message, base_text="Generando"):
    stop_flag = threading.Event()
    def animate():
        states = [f"⏳ {base_text}", f"⏳ {base_text}.", f"⏳ {base_text}..", f"⏳ {base_text}..."]
        i = 0
        while not stop_flag.is_set():
            try:
                message.edit_text(states[i % len(states)])
                time.sleep(0.6)
                i += 1
            except Exception:
                break
    thread = threading.Thread(target=animate)
    thread.start()
    return stop_flag

def diff_highlight(original, modified):
    differ = difflib.ndiff(original.split(), modified.split())
    result = []
    for word in differ:
        if word.startswith("+ "):
            result.append(f"<u>{word[2:]}</u>")
        elif word.startswith("  "):
            result.append(word[2:])
    return ' '.join(result)

def clean_html(content):
    clean = re.compile("<.*?>")
    return re.sub(clean, "", content)

def clean_response_json(content):
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    return content.strip()
