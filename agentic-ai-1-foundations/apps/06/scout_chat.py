"""Scout's first chat loop: python scout_chat.py [--no-history] [--window N]"""
import argparse, re, sys

NOTES = ["Mars has two small moons, Phobos and Deimos.",
         "Venus spins backwards compared with most planets.",
         "A day on Mars lasts about 24 hours and 39 minutes.",
         "Jupiter is the largest planet in the solar system.",
         "The rover Perseverance landed on Mars in February 2021.",
         "Saturn's rings are mostly made of ice."]
SYSTEM = {"role": "system", "text": "You are Scout. Answer only from the user's notes and this chat."}
STOPWORDS = {"the", "what", "which", "how", "are", "was", "tell", "about", "me", "is", "a", "on", "in"}

def tokens(text): return re.findall(r"[\w']+|[.,!?]", text)
def count_tokens(msgs): return sum(1 + len(tokens(m["text"])) for m in msgs)

def fake_model(msgs, window, max_output):
    """Stateless: the reply depends only on msgs."""
    n_in = count_tokens(msgs)
    if n_in > window:
        raise RuntimeError(f"400 prompt is too long: {n_in} tokens > {window} maximum")
    user = msgs[-1]["text"]
    if "my project is" in user.lower():
        text = "Got it. I will keep your project in mind."
    elif "my project" in user.lower():
        said = [m["text"] for m in msgs[:-1] if m["role"] == "user" and "My project is" in m["text"]]
        text = ("Your project is" + said[0].split("My project is", 1)[1]) if said \
            else "I don't know what your project is. Could you tell me?"
    else:
        words = {w.lower() for w in tokens(user)} - STOPWORDS
        scores = [len(words & {w.lower() for w in tokens(n)}) for n in NOTES]
        best = max(range(len(NOTES)), key=scores.__getitem__)
        text = f"From note {best + 1}: {NOTES[best]}" if scores[best] else "None of your notes cover that."
    out = tokens(text)
    room = min(max_output, window - n_in)
    stop = "end_turn" if len(out) <= room else "max_tokens"
    return text if stop == "end_turn" else " ".join(out[:room]), n_in, min(len(out), room), stop

def sliding_window(msgs, window, max_output):
    kept, budget = [], window - max_output - count_tokens([msgs[0]])
    for m in reversed(msgs[1:]):
        if count_tokens([m]) > budget:
            break
        kept.insert(0, m)
        budget -= count_tokens([m])
    return [msgs[0]] + kept

def read_lines(prompt):
    while True:
        try:
            yield input(prompt)
        except EOFError:                     # Ctrl-D, or the end of a pipe
            return

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-history", action="store_true")
    ap.add_argument("--window", type=int, default=200)
    ap.add_argument("--max-output", type=int, default=40)
    args = ap.parse_args()
    piped = not sys.stdin.isatty()
    history = [SYSTEM]
    for line in read_lines("" if piped else "you> "):
        if line.strip() == "/quit":
            break
        history.append({"role": "user", "text": line})
        to_send = [SYSTEM, history[-1]] if args.no_history else history
        trimmed = sliding_window(to_send, args.window, args.max_output)
        if len(trimmed) < len(to_send):
            print(f"  ! dropped {len(to_send) - len(trimmed)} old messages to fit the window")
        text, n_in, n_out, stop = fake_model(trimmed, args.window, args.max_output)
        history.append({"role": "assistant", "text": text})
        print(f"{'you>   ' + line + chr(10) if piped else ''}scout> {text}  [{n_in} in, {n_out} out, {stop}]")
    print(f"scout> Bye. ({len(history)} messages in history)")

if __name__ == "__main__":
    main()
