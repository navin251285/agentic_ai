"""Scout chat v1: python scout_chat.py [--no-history]   (needs GOOGLE_CLOUD_API_KEY)"""
import os, random, sys, time
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
if os.environ.get("SCOUT_CASSETTE"):           # only so the course can record and replay this script
    import llm_replay; llm_replay.start(os.environ["SCOUT_CASSETTE"])
load_dotenv("../.env")
MODEL, MAX_OUTPUT = os.environ.get("TUT_LLM_MODEL", "gemini-3.5-flash-lite"), 120
PRICE_IN, PRICE_OUT = 0.30, 2.50                # USD per million tokens, checked 2026-10-06
WINDOW = int(os.environ.get("SCOUT_WINDOW", 2000))   # tokens per request, system message included
NOTES = ["Mars has two small moons, Phobos and Deimos.", "Venus spins backwards compared with most planets.",
         "A day on Mars lasts about 24 hours and 39 minutes.", "Jupiter is the largest planet in the solar system.",
         "The rover Perseverance landed on Mars in February 2021.", "Saturn's rings are mostly made of ice."]
SYSTEM = ("You are Scout, a research assistant. Answer only from the user's notes below and this chat. "
          "If the notes do not cover it, say so in one sentence. Keep answers to one sentence.\n\n"
          + "\n".join(f"Note {i}: {t}" for i, t in enumerate(NOTES, 1)))
client = genai.Client(vertexai=True, api_key=os.environ.get("GOOGLE_CLOUD_API_KEY") or "replay-no-key-needed")

def contents_of(history):
    return [types.Content(role={"user": "user", "assistant": "model"}[m["role"]], parts=[types.Part(text=m["text"])])
            for m in history]

def fit(history, window):                       # drop oldest pairs until it fits window - MAX_OUTPUT
    config, dropped = types.CountTokensConfig(system_instruction=SYSTEM), 0
    while len(history) > 1 and client.models.count_tokens(
            model=MODEL, contents=contents_of(history), config=config).total_tokens > window - MAX_OUTPUT:
        history, dropped = history[2:], dropped + 2
    return history, dropped

def open_stream(contents, attempts=4):          # retry 408/429/5xx only before anything is shown
    config = types.GenerateContentConfig(system_instruction=SYSTEM, max_output_tokens=MAX_OUTPUT,
                                         automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
    for attempt in range(attempts):
        try:
            stream = client.models.generate_content_stream(model=MODEL, contents=contents, config=config)
            return next(stream), stream
        except errors.APIError as e:
            if e.code not in {408, 429, 500, 502, 503, 504} or attempt == attempts - 1:
                raise
            print(f"  ! {e.code} {e.status}: retrying")
            time.sleep(random.uniform(0, min(8.0, 0.5 * 2 ** attempt)))

def main():
    no_history, history, total, piped = "--no-history" in sys.argv, [], 0.0, not sys.stdin.isatty()
    while True:
        try:
            line = input("" if piped else "you> ").strip()
        except EOFError:                         # Ctrl-D, or the end of a pipe
            break
        print("you>   " + line) if piped else None
        if line == "/quit":
            break
        if line == "/cost":
            print(f"  {len(history) // 2} turns, ${total:.5f} so far"); continue
        history.append({"role": "user", "text": line})
        try:
            to_send, dropped = fit(history[-1:] if no_history else history, WINDOW)
            print(f"  ! dropped {dropped} old messages to fit the window") if dropped else None
            first, stream = open_stream(contents_of(to_send))
            chunks = [first]
            print("scout> " + (first.text or ""), end="", flush=True)
            for ch in stream:
                chunks.append(ch)
                print(ch.text or "", end="", flush=True)
        except errors.APIError as e:
            history.pop()
            print(f"  ! {e.code} {e.status}: {e.message[:70]} (turn not saved)")
            continue
        last, u = chunks[-1], chunks[-1].usage_metadata
        reason = last.candidates[0].finish_reason.value if last.candidates else "BLOCKED"
        n_in, n_out = u.prompt_token_count or 0, (u.candidates_token_count or 0) + (u.thoughts_token_count or 0)
        total += (cost := (n_in * PRICE_IN + n_out * PRICE_OUT) / 1_000_000)
        history.append({"role": "assistant", "text": "".join(c.text or "" for c in chunks).strip()})
        print(f"\n       [{n_in} in, {n_out} out, {reason}] ${cost:.5f} this turn, ${total:.5f} so far")
    print(f"scout> Bye. {len(history) // 2} turns, ${total:.5f}")

if __name__ == "__main__":
    main()
