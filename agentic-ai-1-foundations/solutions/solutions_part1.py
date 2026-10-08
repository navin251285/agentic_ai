# %% [markdown]
# # Solutions · Part 1: What an LLM and an agent are
# Answers to the "Try it" exercises. Try each one yourself first.

# %% [markdown]
# ## Lesson 01
# Setup from lesson 01: the notes, the tool, the scripted model and the loop.

# %%
NOTES = [
    {"id": 1, "text": "Mars has two small moons, Phobos and Deimos."},
    {"id": 2, "text": "Venus spins backwards compared with most planets."},
    {"id": 3, "text": "A day on Mars lasts about 24 hours and 39 minutes."},
    {"id": 4, "text": "Jupiter is the largest planet in the solar system."},
    {"id": 5, "text": "The rover Perseverance landed on Mars in February 2021."},
    {"id": 6, "text": "Saturn's rings are mostly made of ice."},
]

def search_notes(query: str) -> list[dict]:
    q = query.lower()
    return [note for note in NOTES if q in note["text"].lower()]

def scripted_model(history: list[dict]) -> dict:
    last = history[-1]
    if last["role"] == "user":
        topic = last["content"].rstrip("?").split()[-1]
        return {"type": "tool_call", "name": "search_notes", "args": {"query": topic}}
    if last["role"] == "tool":
        ids = [note["id"] for note in last["content"]]
        return {"type": "answer", "text": f"Notes that mention it: {len(ids)} (ids {ids})."}
    raise ValueError(f"unexpected role {last['role']!r}")

def run_agent(question, model, tools, max_steps=5):
    history = [{"role": "user", "content": question}]
    for step in range(1, max_steps + 1):
        reply = model(history)
        if reply["type"] == "answer":
            print(f"step {step}: model answers")
            return reply["text"]
        result = tools[reply["name"]](**reply["args"])
        print(f"step {step}: model calls {reply['name']}({reply['args']}) -> {len(result)} results")
        history.append({"role": "assistant", "content": reply})
        history.append({"role": "tool", "content": result})
    raise RuntimeError(f"agent did not finish in {max_steps} steps")

# %% [markdown]
# **Exercise 1.** The search is a plain substring match, so "moons" only finds note 1
# ("Phobos and Deimos"). Note 3 says "Mars" but not "moons". The answer is only as good as the tool.

# %%
TOOLS = {"search_notes": search_notes}
print(run_agent("How many notes mention moons?", scripted_model, TOOLS))

# %% [markdown]
# **Exercise 2.** Register a second tool and teach a copy of the model when to use it. The loop is unchanged.

# %%
def count_notes() -> list[dict]:
    return list(NOTES)

def scripted_model_2(history):
    last = history[-1]
    if last["role"] == "user" and last["content"] == "How many notes are there?":
        return {"type": "tool_call", "name": "count_notes", "args": {}}
    if last["role"] == "tool" and history[-2]["content"]["name"] == "count_notes":
        return {"type": "answer", "text": f"There are {len(last['content'])} notes."}
    return scripted_model(history)

TOOLS_2 = {"search_notes": search_notes, "count_notes": count_notes}
print(run_agent("How many notes are there?", scripted_model_2, TOOLS_2))
print(run_agent("How many notes mention Venus?", scripted_model_2, TOOLS_2))

# %% [markdown]
# ## Lesson 02
# Setup from lesson 02: tokenizer, bigram counts, greedy picking and `generate`.

# %%
import re
from collections import Counter, defaultdict

START, END = "<s>", "</s>"
NOTE_TEXTS = [n["text"] for n in NOTES]

def tokenize(text):
    return re.findall(r"[\w']+|[.,!?]", text)

def train(texts):
    c = defaultdict(Counter)
    for t in texts:
        seq = [START] + tokenize(t) + [END]
        for prev, nxt in zip(seq, seq[1:]):
            c[prev][nxt] += 1
    return dict(c)

def next_token_probs(prev):
    c = counts[prev]
    total = sum(c.values())
    return {tok: n / total for tok, n in c.items()}

def generate(prompt, max_tokens=20, stop=None):
    tokens, new = [START] + tokenize(prompt), []
    for _ in range(max_tokens):
        nxt = max(next_token_probs(tokens[-1]).items(), key=lambda kv: kv[1])[0]
        if nxt == END:
            return " ".join(new), "end_token"
        if stop and nxt in stop:
            return " ".join(new), "stop_sequence"
        tokens.append(nxt)
        new.append(nxt)
    return " ".join(new), "max_tokens"

counts = train(NOTE_TEXTS)

# %% [markdown]
# **1.** With 3 tokens the limit cuts the sentence; with 20 the model reaches `</s>` on its own.

# %%
print(generate("Mars", max_tokens=3))
print(generate("Mars"))

# %% [markdown]
# **2.** The new note adds a second "the solar" pair, so after `the` the top token is now `solar`
# (2 of 3) instead of `largest`. The cycle breaks and the model reaches `</s>`, though the sentence is false.

# %%
counts = train(NOTE_TEXTS + ["Earth is in the solar system."])
print(next_token_probs("the"))
print(generate("Jupiter", max_tokens=15))

# %% [markdown]
# ## Lesson 03
# Setup from lesson 03: chunking, `merge`, `train_bpe` and `bpe_encode` (the toy BPE tokenizer).

# %%
import re
from collections import Counter

NOTE_TEXTS_03 = [n["text"] for n in NOTES]

def chunks(text):
    return re.findall(r" ?\w+| ?[^\w\s]+", text)

def merge(word, a, b):
    out, i = [], 0
    while i < len(word):
        if i < len(word) - 1 and word[i] == a and word[i + 1] == b:
            out.append(a + b)
            i += 2
        else:
            out.append(word[i])
            i += 1
    return tuple(out)

def train_bpe(texts, n_merges):
    words = [tuple(c) for t in texts for c in chunks(t)]
    merges = []
    for _ in range(n_merges):
        pairs = Counter(p for w in words for p in zip(w, w[1:]))
        if not pairs:
            break
        (a, b), _ = pairs.most_common(1)[0]
        merges.append((a, b))
        words = [merge(w, a, b) for w in words]
    return merges

def bpe_encode(text, merges):
    pieces = []
    for c in chunks(text):
        w = tuple(c)
        for a, b in merges:
            w = merge(w, a, b)
        pieces.extend(w)
    return pieces

# %% [markdown]
# **1.** 13 tokens. Only ` Mars` (three notes) is whole; `bo` and `it` are the other learned pieces.
# `Phobos` and `orbits` are rare in six sentences, so they stay split into small pieces.

# %%
merges_60 = train_bpe(NOTE_TEXTS_03, 60)
pieces = bpe_encode("Phobos orbits Mars.", merges_60)
print(len(pieces), pieces)

# %% [markdown]
# **2.** Note 2 (Venus) is highest, about 4.7 tokens per word: long words (backwards, compared, planets) whose
# letter pairs rarely repeat in the notes. Note 3 is lowest (2.8): short, frequent words like ` on`, ` Mars`, ` and`.

# %%
merges_40 = train_bpe(NOTE_TEXTS_03, 40)
for n in NOTES:
    ratio = len(bpe_encode(n["text"], merges_40)) / len(n["text"].split())
    print(f"note {n['id']}: {ratio:.2f} tokens per word")

# %% [markdown]
# ## Lesson 04
# Setup from lesson 04: the "Mars is" logits, softmax, temperature, top-k, top-p and the sampler,
# plus lesson 02's bigram counts for generation.

# %%
import math, random, re
from collections import Counter, defaultdict

LOGITS = {"red": 3.0, "a": 2.2, "the": 1.8, "cold": 1.2,
          "small": 0.8, "far": 0.3, "purple": -1.0, "banana": -3.0}

def softmax(logits):
    top = max(logits.values())
    exps = {t: math.exp(s - top) for t, s in logits.items()}
    total = sum(exps.values())
    return {t: e / total for t, e in exps.items()}

def apply_temperature(logits, t):
    return softmax({tok: s / t for tok, s in logits.items()})

def top_k(probs, k):
    kept = sorted(probs.items(), key=lambda kv: kv[1], reverse=True)[:k]
    total = sum(p for _, p in kept)
    return {tok: p / total for tok, p in kept}

def top_p(probs, p):
    kept, total = {}, 0.0
    for tok, q in sorted(probs.items(), key=lambda kv: kv[1], reverse=True):
        kept[tok] = q
        total += q
        if total >= p:
            break
    return {tok: q / total for tok, q in kept.items()}

def sample(probs, rng):
    return rng.choices(list(probs), weights=list(probs.values()), k=1)[0]

def pick(logits, rng, temperature=1.0, k=None, p=None):
    if temperature == 0:
        return max(logits, key=logits.get)
    probs = apply_temperature(logits, temperature)
    if k is not None:
        probs = top_k(probs, k)
    if p is not None:
        probs = top_p(probs, p)
    return sample(probs, rng)

# %%
START, END = "<s>", "</s>"
NOTE_SEQS = [[START] + re.findall(r"[\w']+|[.,!?]", n["text"]) + [END] for n in NOTES]
counts_04 = defaultdict(Counter)
for seq in NOTE_SEQS:
    for prev, nxt in zip(seq, seq[1:]):
        counts_04[prev][nxt] += 1

def bigram_logits(prev):
    return {tok: math.log(n) for tok, n in counts_04[prev].items()}

def generate_04(prompt, rng, max_tokens=15, **knobs):
    tokens, new = [START] + re.findall(r"[\w']+|[.,!?]", prompt), []
    for _ in range(max_tokens):
        nxt = pick(bigram_logits(tokens[-1]), rng, **knobs)
        if nxt == END:
            return " ".join(new), "end_token"
        tokens.append(nxt)
        new.append(nxt)
    return " ".join(new), "max_tokens"

# %% [markdown]
# **Exercise 1.** T = 0.5 doubles every gap between logits, so "red" pulls further ahead.
# Top-k 2 keeps "red" and "a"; after renormalising, "red" is above 80% (about 0.83).

# %%
print(top_k(apply_temperature(LOGITS, 0.5), k=2))

# %% [markdown]
# **Exercise 2.** Trick question: both temperatures behave alike, because every choice on the path is
# a tie. Every branch point on the
# "Jupiter" path is a 50/50 choice between tokens seen once each ("in" -> "the" or "February";
# "the" -> "largest" or "solar"), so all their logits are log(1) = 0. Dividing equal logits by any T
# leaves them equal, and the same seed then makes the same draws. Any difference between runs comes
# only from the seed, never from T (here both print 20/20). Temperature only reshapes distributions
# that are uneven to begin with.

# %%
for t in [0.5, 1.5]:
    ends = sum(generate_04("Jupiter", random.Random(seed), temperature=t)[1] == "end_token"
               for seed in range(20))
    print(f"T={t}: {ends}/20 runs reached the end token")

# %% [markdown]
# ## Lesson 05
# Setup from lesson 05: the token counter, Scout's chat, `sliding_window` and `toy_scout`.

# %%
import re

def word_tokenize(text: str) -> list[str]:
    return re.findall(r"[\w']+|[.,!?]", text)

def count_tokens(messages: list[dict]) -> int:
    return sum(1 + len(word_tokenize(m["text"])) for m in messages)

SYSTEM = {"role": "system", "text": "You are Scout. Answer only from the user's notes and this chat."}
TURNS = [
    ("Hi Scout. My project is a school talk about the moons of Mars, for my astronomy class.",
     "Great topic. From note 1, Mars has two small moons, Phobos and Deimos."),
    ("How long is a day on Mars?", "From note 3, a day on Mars lasts about 24 hours and 39 minutes."),
    ("Which rover landed on Mars in 2021?", "From note 5, the rover Perseverance landed on Mars in February 2021."),
    ("What is the largest planet?", "From note 4, Jupiter is the largest planet in the solar system."),
    ("Tell me something odd about Venus.", "From note 2, Venus spins backwards compared with most planets."),
    ("What are Saturn's rings made of?", "From note 6, Saturn's rings are mostly made of ice."),
]
history = [SYSTEM]
for i, (q, a) in enumerate(TURNS, start=1):
    history += [{"role": "user", "text": q, "turn": i}, {"role": "assistant", "text": a, "turn": i}]
question7 = {"role": "user", "text": "Remind me: what is my project about?", "turn": 7}

def sliding_window(messages, window, max_output):
    system, rest = messages[0], messages[1:]
    kept, budget = [], window - max_output - count_tokens([system])
    for m in reversed(rest):
        cost = count_tokens([m])
        if cost > budget:
            break
        kept.insert(0, m)
        budget -= cost
    return [system] + kept

def toy_scout(messages):
    for m in messages:
        if m["role"] == "user" and "My project is" in m["text"]:
            return "Your project is" + m["text"].split("My project is")[1]
    return "I don't know what your project is. Could you tell me?"

# %% [markdown]
# **1.** With a 150-token window only 150 - 40 - 15 = 95 tokens are left for history, so turns 1 and 2 drop out
# (plus the user's half of turn 3), and Scout no longer knows the project.

# %%
visible = sliding_window(history + [question7], 150, 40)
print("messages seen:", [(m["turn"], m["role"]) for m in visible if "turn" in m])
print(toy_scout(visible))

# %% [markdown]
# **2.** Pin the system prompt and turn 1, then fill the remaining budget with the newest messages.

# %%
def pin_first_turn(messages, window, max_output):
    pinned = [m for m in messages if m["role"] == "system" or m.get("turn") == 1]
    rest = [m for m in messages if m not in pinned]
    kept, budget = [], window - max_output - count_tokens(pinned)
    for m in reversed(rest):
        if count_tokens([m]) > budget:
            break
        kept.insert(0, m)
        budget -= count_tokens([m])
    return pinned + kept

visible = pin_first_turn(history + [question7], 200, 40)
print("turns seen:", sorted({m["turn"] for m in visible if "turn" in m}), "tokens:", count_tokens(visible))
print(toy_scout(visible))

# %% [markdown]
# ## Lesson 06
# Setup from lesson 06: the system message, token counter and a minimal stateless fake model
# (it only needs to know the project when "My project is" is in the messages it is sent).

# %%
import re

SYSTEM = {"role": "system", "text": "You are Scout. Answer only from the user's notes and this chat."}

def count_tokens(messages):
    return sum(1 + len(re.findall(r"[\w']+|[.,!?]", m["text"])) for m in messages)

def fake_model(messages, max_output=40):
    said = [m["text"] for m in messages[:-1] if m["role"] == "user" and "My project is" in m["text"]]
    if "my project is" in messages[-1]["text"].lower():
        text = "Got it. I will keep your project in mind."
    else:
        text = ("Your project is" + said[0].split("My project is", 1)[1]) if said else "I don't know your project."
    return {"text": text}

# %% [markdown]
# `/reset` replaces the list with a fresh one holding only the system message; `/history` reports its
# size. Neither is sent to the model. After the reset, the model is never shown turn 1 again, so it forgets.

# %%
def chat_loop_v2(model, inputs):
    history = [SYSTEM]
    for user_text in inputs:
        cmd = user_text.strip()
        if cmd == "/quit":
            break
        if cmd == "/reset":
            history = [SYSTEM]
            print("(history reset)")
            continue
        if cmd == "/history":
            print(f"(history: {len(history)} messages, {count_tokens(history)} tokens)")
            continue
        history.append({"role": "user", "text": user_text})
        reply = model(history)
        history.append({"role": "assistant", "text": reply["text"]})
        print(f"you> {user_text}\nscout> {reply['text']}")
    return history

chat_loop_v2(fake_model, ["My project is a talk about Mars.", "What is my project?", "/history",
                          "/reset", "/history", "What is my project?", "/quit"])
