# %% [markdown]
# # Solutions · Part 3 · Search people actually trust
# Answers to the "Try it" exercises. Each section re-declares what it needs, so it runs on its own.

# %% [markdown]
# ## Lesson 16
# Shared setup from lesson 16: the 2,000 recipes in a local-mode collection, the saved labels
# (`data/eval_queries_20.json`), the query cache, both runs and the four metrics.

# %%
import json, math, re, uuid, warnings
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore", message="IProgress")
from qdrant_client import QdrantClient, models

recipes = pd.read_csv("../data/recipes_2000.csv")
doc_emb = np.load("../data/recipe_embeddings_minilm_2000.npz")["doc_emb"]
TITLE = dict(zip(recipes.slug, recipes.title))
qrels = json.load(open("../data/eval_queries_20.json"))["qrels"]
cache = np.load("../data/query_embeddings_minilm_eval.npz")
query_cache = dict(zip(cache["queries"].tolist(), cache["query_emb"], strict=True))

RECIPE_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://example.com/recipes/")
client = QdrantClient(":memory:")
client.create_collection("recipes", vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE))
client.upload_points("recipes", [
    models.PointStruct(id=str(uuid.uuid5(RECIPE_NS, r.slug)), vector=doc_emb[i].tolist(),
                       payload={"slug": r.slug}) for i, r in enumerate(recipes.itertuples())])
print(len(qrels), "labelled queries,", client.count("recipes").count, "points")

# %% [markdown]
# The two runs and the metrics, as in the lesson.

# %%
STOP_WORDS = {"a", "an", "and", "the", "for", "of", "on", "in", "with", "until", "great"}
tokenize = lambda text: {w for w in re.findall(r"[a-z]+", text.lower()) if w not in STOP_WORDS}
recipe_words = {r.slug: tokenize(f"{r.title} {r.description}") for r in recipes.itertuples()}

def vector_run(queries, k=10):
    reqs = [models.QueryRequest(query=query_cache[q].tolist(), limit=k, with_payload=["slug"]) for q in queries]
    return {q: [p.payload["slug"] for p in r.points]
            for q, r in zip(queries, client.query_batch_points("recipes", requests=reqs))}

def keyword_run(queries, k=10):
    out = {}
    for q in queries:
        scores = {s: len(tokenize(q) & w) for s, w in recipe_words.items()}
        out[q] = sorted((s for s in scores if scores[s] > 0), key=lambda s: (-scores[s], s))[:k]
    return out

def evaluate(run, qrels, k=5):
    def ndcg(ranked, labels):
        dcg = sum(labels.get(s, 0) / math.log2(i + 1) for i, s in enumerate(ranked[:k], 1))
        ideal = sum(g / math.log2(i + 1) for i, g in enumerate(sorted(labels.values(), reverse=True)[:k], 1))
        return dcg / ideal
    rr = lambda ranked, labels: next((1 / i for i, s in enumerate(ranked, 1) if s in labels), 0.0)
    return pd.DataFrame.from_dict({q: {f"P@{k}": sum(s in l for s in run[q][:k]) / k,
                                       f"R@{k}": sum(s in l for s in run[q][:k]) / len(l),
                                       "RR": rr(run[q], l), f"nDCG@{k}": ndcg(run[q], l)}
                                   for q, l in qrels.items()}, orient="index")

print("ready")

# %% [markdown]
# ### Exercise 1 · Grow the exam
# Label the two extra queries. A fruity dessert: apple pie and strawberry cheesecake are exactly
# right; lemon sorbet and panna cotta (berry sauce) are acceptable. Creamy mushroom pasta: the
# generated "Creamy mushroom pasta" is exactly right; other mushroom pastas and Mushroom risotto
# are acceptable.

# %%
FLAVOUR = "(spicy|smoky|lemon garlic|creamy|honey ginger|herby) "
titles_like = lambda pattern, grade: {s: grade for s, t in TITLE.items() if re.fullmatch(pattern, t.lower())}

qrels22 = dict(qrels)
qrels22["a fruity dessert"] = {"apple-pie": 2, "strawberry-cheesecake": 2, "lemon-sorbet": 1, "panna-cotta": 1}
qrels22["creamy mushroom pasta"] = (titles_like(FLAVOUR + "mushroom pasta", 1)
                                    | {"creamy-mushroom-pasta": 2, "mushroom-risotto": 1})
assert all(s in TITLE for labels in qrels22.values() for s in labels)
for q in ["a fruity dessert", "creamy mushroom pasta"]:
    print(q, "->", qrels22[q])

# %% [markdown]
# Re-run both methods on 20 and on 22 queries and compare the means.

# %%
table = {}
for name, make_run in [("vector", vector_run), ("keyword", keyword_run)]:
    table[f"{name} 20"] = evaluate(make_run(list(qrels)), qrels).mean()
    table[f"{name} 22"] = evaluate(make_run(list(qrels22)), qrels22).mean()
print(pd.DataFrame(table).round(3).to_string())
print(evaluate(vector_run(list(qrels22)), qrels22).tail(2).round(2).to_string())
print(evaluate(keyword_run(list(qrels22)), qrels22).tail(2).round(2).to_string())

# %% [markdown]
# Two queries move each mean by a few hundredths, the same size as the gap between the methods.
# That is the "20 queries is small" caution from the lesson in numbers: add queries before
# trusting small differences.

# %% [markdown]
# ### Exercise 2 · How deep must you look?
# Fetch 20 hits per query and compute mean recall@k at several depths.

# %%
runs = {"vector": vector_run(list(qrels), k=20), "keyword": keyword_run(list(qrels), k=20)}
curve = {name: {k: np.mean([sum(s in qrels[q] for s in run[q][:k]) / len(qrels[q]) for q in qrels])
                for k in [1, 3, 5, 10, 20]} for name, run in runs.items()}
print(pd.DataFrame(curve).rename_axis("k").round(3).to_string())

# %% [markdown]
# For the queries vector search scores 0 on at k=20, where is the first right answer?

# %%
deep = vector_run(list(qrels), k=400)
for q in qrels:
    if not any(s in qrels[q] for s in runs["vector"][q]):
        first = next(i for i, s in enumerate(deep[q], 1) if s in qrels[q])
        print(f"{q!r}: first right answer at vector rank {first} ({deep[q][first - 1]})")

# %% [markdown]
# Keyword search is ahead at every depth, but the gap shrinks from 0.11 at k=5 to 0.02 at k=20.
# The four queries vector search scores 0 on stay at 0 even at k=20: their first right answers sit
# at vector ranks 22 (shakshuka) to 120 (guacamole), as printed above, so a reranker over the
# vector top 20 could not
# rescue them. Keyword search has different gaps (fish traybake, grilled cheese). Getting both
# kinds of candidate into one list is the job of hybrid search (lessons 19-20).

# %%
client.close()
print("client closed")

# %% [markdown]
# ## Lesson 17
# Shared setup from lesson 17: the 24 recipe methods, the saved vectors
# (`data/chunk_embeddings_minilm.npz`), the step-question labels (`data/eval_steps_20.json`),
# the chunker, the metrics and `evaluate_chunking`, here taking any chunking function.

# %%
import json, math, uuid, warnings
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore", message="IProgress")
from qdrant_client import QdrantClient, models

recipes = pd.read_csv("../data/recipes_2000.csv").set_index("slug")
methods = json.load(open("../data/recipe_methods_24.json"))
docs = {slug: " ".join(steps) for slug, steps in methods.items()}
qrels = json.load(open("../data/eval_steps_20.json"))["qrels"]
cache = np.load("../data/chunk_embeddings_minilm.npz")
text_cache = dict(zip(cache["texts"].tolist(), cache["emb"], strict=True))
query_cache = dict(zip(cache["queries"].tolist(), cache["query_emb"], strict=True))
RECIPE_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://example.com/recipes/")
recipe_id = lambda slug: str(uuid.uuid5(RECIPE_NS, slug))
VECTORS = models.VectorParams(size=384, distance=models.Distance.COSINE)
client = QdrantClient(":memory:")

def chunk_words(text, size, overlap=0):
    words = text.split()
    return [" ".join(words[i:i + size]) for i in range(0, max(len(words) - overlap, 1), size - overlap)]

def load_chunks(name, chunker):
    client.create_collection(name, vectors_config=VECTORS)
    points = [models.PointStruct(id=str(uuid.uuid5(RECIPE_NS, f"{slug}#{i}")), vector=text_cache[text].tolist(),
                                 payload={"slug": slug, "recipe_id": recipe_id(slug), "chunk": i, "text": text})
              for slug in docs for i, text in enumerate(chunker(slug))]
    client.upload_points(name, points)
    return len(points)

print(len(docs), "methods,", len(qrels), "questions,", len(text_cache), "cached chunk vectors")

# %% [markdown]
# The metrics and the evaluation, as in the lesson.

# %%
def evaluate_chunking(chunker, k=5):
    n = load_chunks("eval", chunker)
    rows = []
    for q, labels in qrels.items():
        groups = client.query_points_groups("eval", query=query_cache[q].tolist(), group_by="slug",
                                            limit=k, group_size=1).groups
        ranked = [g.id for g in groups]
        dcg = sum(labels.get(s, 0) / math.log2(r + 1) for r, s in enumerate(ranked[:k], 1))
        ideal = sum(g / math.log2(r + 1) for r, g in enumerate(sorted(labels.values(), reverse=True)[:k], 1))
        rows.append({"MRR": next((1 / r for r, s in enumerate(ranked, 1) if s in labels), 0.0),
                     "R@3": sum(s in labels for s in ranked[:3]) / len(labels), f"nDCG@{k}": dcg / ideal,
                     "words to read": len(groups[0].hits[0].payload["text"].split())})
    client.delete_collection("eval")
    return {"chunks": n, **pd.DataFrame(rows).mean().to_dict()}

print("ready")

# %% [markdown]
# ### Exercise 1 · One step per chunk
# Each step of a method becomes one chunk. Compare it with the whole method and with 50-word
# windows.

# %%
by_step = lambda slug: methods[slug]
table = pd.DataFrame({"whole": evaluate_chunking(lambda s: [docs[s]]),
                      "50 words": evaluate_chunking(lambda s: chunk_words(docs[s], 50)),
                      "one step": evaluate_chunking(by_step)}).T
print(table.round(3).to_string())
lengths = [len(step.split()) for steps in methods.values() for step in steps]
print("\nwords per step: min", min(lengths), "median", int(np.median(lengths)), "max", max(lengths))

# %% [markdown]
# One step per chunk scores MRR 1.000 and nDCG@5 0.912 with about 27 words to read, the best of
# the three. Against 50-word windows that is inside the noise of 20 queries, but it comes free:
# steps are 4-49 words (median 22), inside the 25-100-word range the lesson found works, and no
# chunk ever stops mid-sentence. When a document has structure (steps, paragraphs, headings),
# chunk along it first and only cut further where a piece is too long.

# %% [markdown]
# ### Exercise 2 · Show the answer, not just the recipe
# Store the parents (whole-method vector, title, minutes) and group the step chunks by
# `recipe_id`, with `with_lookup`.

# %%
client.create_collection("recipes", vectors_config=VECTORS)
client.upload_points("recipes", [models.PointStruct(
    id=recipe_id(s), vector=text_cache[docs[s]].tolist(),
    payload={"title": recipes.title[s], "minutes": int(recipes.minutes[s])}) for s in docs])
load_chunks("steps", by_step)

q = "how long does it need to set in the fridge?"
result = client.query_points_groups("steps", query=query_cache[q].tolist(), group_by="recipe_id",
                                    limit=3, group_size=2, with_lookup=models.WithLookup(collection="recipes", with_payload=True))
for g in result.groups:
    print(f"{g.lookup.payload['title']} ({g.lookup.payload['minutes']} min)")
    for h in g.hits:
        print(f"   {h.score:.3f}  {h.payload['text']}")

# %% [markdown]
# Now one group with three hits: the three best steps of the single best recipe.

# %%
one = client.query_points_groups("steps", query=query_cache[q].tolist(), group_by="recipe_id",
                                 limit=1, group_size=3, with_lookup=models.WithLookup(collection="recipes", with_payload=True))
g = one.groups[0]
print(g.lookup.payload["title"], "->", [(h.payload["chunk"], round(h.score, 3)) for h in g.hits])

# %% [markdown]
# The top group is Tiramisu with exactly the right step ("at least 6 hours", score 0.630). Its
# second hit scores only 0.181: `group_size` is a maximum, and weak hits fill it anyway, so show
# only hits above a threshold, or just the first. Cheesecake and panna cotta, also correct, are
# not in the top 3; sorbet and cookies are (freezer and fridge steps). With `limit=1, group_size=3`
# you get one recipe and its three best steps (5, 1, 6), useful when the recipe is already
# chosen and you want the passages inside it.

# %%
client.close()
print("client closed")

# %% [markdown]
# ## Lesson 18
# Shared setup from lesson 18: the 20 labelled queries and eight translations, MiniLM and Qwen3
# recipe vectors and query vectors from the saved files, `truncate`, and an `evaluate` that scores
# exact search (cosine on unit vectors, the same ranking local-mode Qdrant gives) for one length.

# %%
import json, math
import numpy as np
import pandas as pd

recipes = pd.read_csv("../data/recipes_2000.csv")
slugs = recipes.slug.to_numpy()
qrels = json.load(open("../data/eval_queries_20.json"))["qrels"]
TRANSLATED = {"un postre de chocolate": "a chocolate dessert", "sopa fría para un día de calor": "cold soup for a hot day",
              "Muscheln in Weißwein": "mussels in white wine", "un dolce ghiacciato per l'estate": "a frozen treat for summer",
              "brochettes d'agneau": "lamb skewers", "un ragoût de bœuf mijoté": "a slow-cooked beef stew",
              "भारतीय पनीर करी": "Indian cottage cheese curry", "泰式虾仁面条": "Thai prawn noodles"}
qcache = np.load("../data/query_embeddings_18.npz")
QV = dict(zip(qcache["queries"].tolist(), qcache["qwen3"]))
qwen_docs = np.load("../data/recipe_embeddings_qwen3_2000.npz")["doc_emb"].astype(np.float32)

def truncate(v, dims):
    v = np.asarray(v, dtype=np.float32)[..., :dims]
    return v / np.linalg.norm(v, axis=-1, keepdims=True)

def evaluate(queries, dims, k=5):
    docs, rows = truncate(qwen_docs, dims), []
    for q in queries:
        labels = qrels[TRANSLATED.get(q, q)]
        ranked = slugs[np.argsort(-(docs @ truncate(QV[q], dims)), kind="stable")[:10]]
        dcg = sum(labels.get(s, 0) / math.log2(r + 1) for r, s in enumerate(ranked[:k], 1))
        ideal = sum(g / math.log2(r + 1) for r, g in enumerate(sorted(labels.values(), reverse=True)[:k], 1))
        rows.append({"MRR": next((1 / r for r, s in enumerate(ranked, 1) if s in labels), 0.0), "nDCG@5": dcg / ideal})
    return pd.DataFrame(rows).mean()

print("full Qwen3 nDCG@5:", round(evaluate(list(qrels), 1024)["nDCG@5"], 3))

# %% [markdown]
# ### Exercise 1 · Pick the dimension
# Score many lengths and keep the smallest within 0.02 of the full score.

# %%
full = evaluate(list(qrels), 1024)["nDCG@5"]
curve = pd.Series({d: evaluate(list(qrels), d)["nDCG@5"] for d in [1024, 896, 768, 640, 512, 384, 256]})
smallest = min(d for d, v in curve.items() if v >= full - 0.02)
print(curve.round(3).to_string())
print(f"\nsmallest within 0.02: {smallest} dims -> {4 * smallest * 1e6 / 1e9:.2f} GB for 1M recipes (MiniLM: 1.54 GB)")

# %% [markdown]
# Only 896 dims stays within 0.02 (768 misses by 0.001, well inside the noise of 20 queries), and
# that needs 3.58 GB for 1M recipes, more than twice MiniLM's 1.54 GB. A strict quality bar leaves
# little room to cut. The useful trade is looser: 384 dims costs the same memory as MiniLM and
# scores 0.718 against MiniLM's 0.687.

# %% [markdown]
# ### Exercise 2 · Does the multilingual skill survive the cut?

# %%
english, translated = [TRANSLATED[q] for q in TRANSLATED], list(TRANSLATED)
table = pd.DataFrame({d: {"English": evaluate(english, d)["nDCG@5"], "translated": evaluate(translated, d)["nDCG@5"]}
                      for d in [1024, 256, 64]}).T.rename_axis("dims")
table["share kept (translated)"] = table.translated / table.translated.iloc[0]
table["share kept (English)"] = table.English / table.English.iloc[0]
print(table.round(3).to_string())

# %% [markdown]
# Both lose about the same share: at 256 dims each keeps about 93%, and at 64 dims English keeps
# 56% and translated 60%. On these eight queries the multilingual skill is cut no faster than the
# English one; the translated queries simply start lower (0.719 against 0.917).
