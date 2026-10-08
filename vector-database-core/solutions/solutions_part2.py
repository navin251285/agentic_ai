# %% [markdown]
# # Solutions · Part 2 · Your first vector database
# Answers to the "Try it" exercises. Each section re-declares what it needs, so it runs on its own.

# %% [markdown]
# ## Lesson 07
# Shared setup from lesson 07: the 50 recipes, their saved embeddings, the query cache, `knn`, and
# a local-mode Qdrant collection with every recipe as a point.

# %%
import shutil, time, warnings
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore", message="IProgress")
from qdrant_client import QdrantClient, models

original = pd.read_csv("../data/recipes_50.csv")
original_emb = np.load("../data/recipe_embeddings_minilm.npz")["doc_emb"]
cache = np.load("../data/query_embeddings_minilm.npz")
query_cache = dict(zip(cache["queries"].tolist(), cache["query_emb"], strict=True))

def knn(query, vectors, k):
    scores = vectors @ np.asarray(query, dtype=np.float32)
    rows = np.argsort(-scores, kind="stable")[:k]
    return rows, scores[rows]

DB_PATH = "../data/cache/qdrant_sol07"
shutil.rmtree(DB_PATH, ignore_errors=True)
client = QdrantClient(path=DB_PATH)
client.create_collection("recipes", vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE))
client.upsert("recipes", points=[
    models.PointStruct(id=int(r.id), vector=original_emb[i].tolist(),
                       payload={"title": r.title, "vegetarian": bool(r.vegetarian), "minutes": int(r.minutes)})
    for i, r in enumerate(original.itertuples())])
print(client.count("recipes"))

# %% [markdown]
# **Exercise 1.** NumPy: score only the rows the mask allows, then map back with `allowed[rows]`.
# Qdrant: a `Range(lte=30)` condition in `query_filter`. Both return the same three recipes with the
# same scores; Sushi rolls (45 minutes) drops out of the unfiltered top 3.

# %%
q = query_cache["seafood"]
allowed = np.flatnonzero(original["minutes"] <= 30)
rows, scores = knn(q, original_emb[allowed], 3)
print("NumPy: ", [(original["title"][i], round(float(s), 3)) for i, s in zip(allowed[rows], scores, strict=True)])

quick = models.Filter(must=[models.FieldCondition(key="minutes", range=models.Range(lte=30))])
hits = client.query_points("recipes", query=q.tolist(), query_filter=quick, limit=3)
print("Qdrant:", [(p.payload["title"], round(p.score, 3)) for p in hits.points])

# %% [markdown]
# **Exercise 2.** Time grows roughly in a straight line with N, so divide 100 ms by the time per
# vector. The exact number depends on your laptop; on the machine that ran this notebook it was
# about 400,000 vectors (roughly 0.6 GB of float32). This `knn` also sorts every score, which adds
# to the cost; either way, a recipe app with a few hundred thousand recipes already spends a tenth
# of a second per query on brute force.

# %%
rng = np.random.default_rng(7)
ms_per_vector = []
for n in [10_000, 100_000, 300_000]:
    vecs = rng.standard_normal((n, 384), dtype=np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    runs = []
    for _ in range(10):
        t0 = time.perf_counter(); knn(q, vecs, 3); runs.append(time.perf_counter() - t0)
    ms = float(np.median(runs)) * 1000
    ms_per_vector.append(ms / n)
    print(f"{n:>8,} vectors: {ms:7.2f} ms")
print(f"about {100 / ms_per_vector[-1]:,.0f} vectors for 100 ms per query")
client.close()

# %% [markdown]
# ## Lesson 08
# Shared setup from lesson 08: lesson 03's five toy recipes `[sweet, spicy]`, the query
# `[0.3, 0.4]`, and an in-memory client for experiments.

# %%
import numpy as np
from qdrant_client import QdrantClient, models

toy = {
    "Tomato soup": [0.3, 0.1], "Mango salsa": [0.6, 0.8], "Chocolate brownies": [0.95, 0.0],
    "Caesar salad": [0.1, 0.1], "Lemon sorbet": [0.8, 0.0],
}
toy_query = [0.3, 0.4]
lab = QdrantClient(":memory:")
print(len(toy), "toy recipes")

# %% [markdown]
# **Exercise 1.** Double brownies points in exactly the same direction as Chocolate brownies, so
# Cosine (which normalises on upload) gives both the same score, 0.6 (Lemon sorbet too: all three
# lie along the sweet axis), and ranks them below Mango salsa. Dot keeps the length: 1.9 × 0.3 = 0.57 beats Mango salsa's 0.5, so the doubled vector
# jumps to first place without tasting any more like the query.

# %%
toy6 = {**toy, "Double brownies": [1.9, 0.0]}
for metric in [models.Distance.COSINE, models.Distance.DOT]:
    name = f"toy6_{metric.value}"
    lab.create_collection(name, vectors_config=models.VectorParams(size=2, distance=metric))
    lab.upsert(name, points=[models.PointStruct(id=i, vector=v, payload={"title": t})
                             for i, (t, v) in enumerate(toy6.items())])
    hits = lab.query_points(name, query=toy_query, limit=6).points
    print(f"{metric.value:7}", [(p.payload["title"], round(p.score, 3)) for p in hits])

# %% [markdown]
# **Exercise 2.** The shape gives the size (384, the same as MiniLM) and every vector has length
# 1, so Cosine is the natural choice (Dot or Euclid would rank the same). Note that size alone
# could not tell bge-small and MiniLM apart.

# %%
bge = np.load("../data/recipe_embeddings_bge-small.npz")["doc_emb"]
lengths = np.linalg.norm(bge, axis=1)
print("shape:", bge.shape, " lengths min/max:", round(float(lengths.min()), 4), round(float(lengths.max()), 4))
lab.create_collection("recipes_bge", vectors_config=models.VectorParams(size=bge.shape[1], distance=models.Distance.COSINE))
print(lab.get_collection("recipes_bge").config.params.vectors)
lab.close()

# %% [markdown]
# ## Lesson 09
# Shared setup from lesson 09: the 50 recipes, their MiniLM embeddings, and an in-memory
# `recipes` collection (size 384, Cosine).

# %%
import numpy as np
import pandas as pd
from qdrant_client import QdrantClient, models

recipes = pd.read_csv("../data/recipes_50.csv")
saved = np.load("../data/recipe_embeddings_minilm.npz")
doc_emb, MODEL = saved["doc_emb"], str(saved["model"])
client09 = QdrantClient(":memory:")
client09.create_collection("recipes", vectors_config=models.VectorParams(size=doc_emb.shape[1], distance=models.Distance.COSINE))
print(client09.count("recipes"))

# %% [markdown]
# **Exercise 1.** Add `description` to the payload and load all 50 points twice (the first load
# stands in for lesson 09's original one). Upsert replaces each point by id, so the count stays 50
# and recipe 7 now has six fields.

# %%
def to_payload(row):
    return {"title": str(row.title), "description": str(row.description), "cuisine": str(row.cuisine),
            "vegetarian": bool(row.vegetarian), "minutes": int(row.minutes), "embed_model": MODEL}

points = [models.PointStruct(id=int(row.id), vector=doc_emb[i].tolist(), payload=to_payload(row))
          for i, row in enumerate(recipes.itertuples())]
for _ in range(2):
    client09.upsert("recipes", points=points)
seven = client09.retrieve("recipes", ids=[7])[0].payload
print("points:", client09.count("recipes").count, "| recipe 7 fields:", len(seven), sorted(seven))

# %% [markdown]
# **Exercise 2.** `models.Batch` takes three parallel lists. Recipes 1–10 are the first ten CSV
# rows, so they pair with `doc_emb[:10]`. A list in `with_payload` keeps only the titles.

# %%
first10 = recipes.head(10)
client09.create_collection("recipes_batch", vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE))
client09.upsert("recipes_batch", points=models.Batch(
    ids=[int(i) for i in first10["id"]],
    vectors=doc_emb[:10].tolist(),
    payloads=[to_payload(row) for row in first10.itertuples()],
))
print("points:", client09.count("recipes_batch").count)
print([(r.id, r.payload) for r in client09.retrieve("recipes_batch", ids=[1, 10], with_payload=["title"])])
client09.close()

# %% [markdown]
# ## Lesson 10
# Shared setup from lesson 10: an in-memory `recipes` collection (50 MiniLM points, Cosine), the
# cached on-topic and off-topic query vectors, and lesson 10's `search` helper.

# %%
import numpy as np
import pandas as pd
from qdrant_client import QdrantClient, models

recipes = pd.read_csv("../data/recipes_50.csv")
doc_emb = np.load("../data/recipe_embeddings_minilm.npz")["doc_emb"]
cache = np.load("../data/query_embeddings_minilm.npz")
query_cache = dict(zip(cache["queries"].tolist(), cache["query_emb"]))
extra = np.load("../data/query_embeddings_minilm_offtopic.npz")
off_cache = dict(zip(extra["queries"].tolist(), extra["query_emb"]))
client10 = QdrantClient(":memory:")
client10.create_collection("recipes", vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE))
client10.upsert("recipes", points=[models.PointStruct(id=int(row.id), vector=doc_emb[i].tolist(),
                payload={"title": str(row.title)}) for i, row in enumerate(recipes.itertuples())])

def search(vec, k=5, min_score=None):
    hits = client10.query_points("recipes", query=vec.tolist(), limit=k, score_threshold=min_score).points
    return [(h.payload["title"], round(h.score, 3)) for h in hits]

print(client10.count("recipes").count, "points;", len(query_cache), "+", len(off_cache), "cached queries")

# %% [markdown]
# **Exercise 1.** An empty list is the signal. "a dip for chips" passes the 0.3 floor (its results
# are on-topic, even if Chocolate chip cookies is a poor first hit); the tax question does not.

# %%
def answer(vec):
    hits = search(vec, k=3, min_score=0.3)
    return [title for title, _ in hits] if hits else "Sorry, no recipes match that."

print("a dip for chips ->", answer(query_cache["a dip for chips"]))
print("quarterly tax return deadline ->", answer(off_cache["quarterly tax return deadline"]))

# %% [markdown]
# **Exercise 2.** For unit vectors, distance = √(2 − 2·cosine), so cosine 0.5 becomes a Euclid
# ceiling of √1.0 = 1.0. Both collections then return the same ids in the same order.

# %%
client10.create_collection("recipes_euclid", vectors_config=models.VectorParams(size=384, distance=models.Distance.EUCLID))
client10.upsert("recipes_euclid", points=[models.PointStruct(id=int(row.id), vector=doc_emb[i].tolist(),
                payload={"title": str(row.title)}) for i, row in enumerate(recipes.itertuples())])
spicy = query_cache["very spicy food"].tolist()
ceiling = float(np.sqrt(2 - 2 * 0.5))
by_cos = [h.id for h in client10.query_points("recipes", query=spicy, limit=50, score_threshold=0.5).points]
by_dist = [h.id for h in client10.query_points("recipes_euclid", query=spicy, limit=50, score_threshold=ceiling).points]
print(f"ceiling {ceiling:.3f} | cosine hits {len(by_cos)} | euclid hits {len(by_dist)} | same: {by_cos == by_dist}")
client10.close()

# %% [markdown]
# ## Lesson 11
# Setup: lesson 11's collection (payload with `description`) in memory, plus the query cache.

# %%
import numpy as np
import pandas as pd
from qdrant_client import QdrantClient, models

recipes = pd.read_csv("../data/recipes_50.csv")
saved = np.load("../data/recipe_embeddings_minilm.npz")
doc_emb, MODEL = saved["doc_emb"], str(saved["model"])
cache = np.load("../data/query_embeddings_minilm.npz")
query_cache = dict(zip(cache["queries"].tolist(), cache["query_emb"]))
client11 = QdrantClient(":memory:")
client11.create_collection("recipes", vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE))
client11.upsert("recipes", points=[models.PointStruct(id=int(r.id), vector=doc_emb[i].tolist(), payload={
    "title": str(r.title), "description": str(r.description), "cuisine": str(r.cuisine),
    "vegetarian": bool(r.vegetarian), "minutes": int(r.minutes)}) for i, r in enumerate(recipes.itertuples())])
print(client11.count("recipes").count, "points")

# %% [markdown]
# **Exercise 1.** "From 30 to 60, both included" is `Range(gte=30, lte=60)`; "not French" goes in
# `must_not`. Every hit is vegetarian, 30 to 60 minutes, and none is French.

# %%
warm = models.Filter(
    must=[models.FieldCondition(key="vegetarian", match=models.MatchValue(value=True)),
          models.FieldCondition(key="minutes", range=models.Range(gte=30, lte=60))],
    must_not=[models.FieldCondition(key="cuisine", match=models.MatchValue(value="French"))])
hits = client11.query_points("recipes", query=query_cache["something warm for a cold day"].tolist(),
                             query_filter=warm, limit=5).points
for h in hits:
    print(f"{h.payload['title']:<22} {h.payload['cuisine']:<15} {h.payload['minutes']:>3} min  {h.score:.3f}")

# %% [markdown]
# **Exercise 2.** `MatchText(text="chili")` matches the whole word "chili" (not "chilies"). Loop
# until the offset is `None`; the total equals `count` with the same filter.

# %%
chili = models.Filter(must=[models.FieldCondition(key="description", match=models.MatchText(text="chili"))])
found, offset = [], None
while True:
    records, offset = client11.scroll("recipes", scroll_filter=chili, limit=3, offset=offset)
    print("page:", [r.payload["title"] for r in records])
    found += records
    if offset is None:
        break
print("total:", len(found), "| count:", client11.count("recipes", count_filter=chili).count)
client11.close()

# %% [markdown]
# ## Lesson 12
# Setup: lesson 12's collection in memory, with `version` in the payload, the soup already updated
# (25 minutes, new description and vector, version 5), and the helpers `show`, `save_if_version`
# and `safe_delete`.

# %%
extra12 = np.load("../data/lesson12_embeddings_minilm.npz")
soup_query = extra12["query_emb"][0].tolist()
client12 = QdrantClient(":memory:")
client12.create_collection("recipes", vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE))
client12.upsert("recipes", points=[models.PointStruct(id=int(r.id), vector=doc_emb[i].tolist(), payload={
    "title": str(r.title), "description": str(r.description), "cuisine": str(r.cuisine),
    "vegetarian": bool(r.vegetarian), "minutes": int(r.minutes), "version": 1})
    for i, r in enumerate(recipes.itertuples())])
client12.set_payload("recipes", payload={"minutes": 25, "version": 5,
                                        "description": str(extra12["doc_text"][0]).split(". ", 1)[1]}, points=[11])
client12.update_vectors("recipes", points=[models.PointVectors(id=11, vector=extra12["doc_emb"][0].tolist())])
quick_veg = models.Filter(must=[models.FieldCondition(key="vegetarian", match=models.MatchValue(value=True)),
                                models.FieldCondition(key="minutes", range=models.Range(lte=30))])

def show(flt=quick_veg, k=5):
    for h in client12.query_points("recipes", query=soup_query, query_filter=flt, limit=k).points:
        print(f"  {h.id:>3} {h.payload['title']:<24} {h.payload['minutes']:>3} min  {h.score:.3f}")

def save_if_version(point_id, changes, expected_version):
    current = client12.retrieve("recipes", ids=[point_id], with_vectors=True)[0]
    payload = {**current.payload, **changes, "version": expected_version + 1}
    client12.upsert("recipes", points=[models.PointStruct(id=point_id, vector=current.vector, payload=payload)],
                    update_filter=models.Filter(must=[models.FieldCondition(
                        key="version", match=models.MatchValue(value=expected_version))]),
                    update_mode=models.UpdateMode.UPDATE_ONLY)
    after = client12.retrieve("recipes", ids=[point_id])[0].payload
    applied = after["version"] == expected_version + 1 and all(after[k] == v for k, v in changes.items())
    return applied, after

def safe_delete(c, flt, expected):
    if not (flt.must or flt.should or flt.must_not):
        raise ValueError("refusing to delete with an empty filter")
    n = c.count("recipes", count_filter=flt).count
    if n != expected:
        raise ValueError(f"filter matches {n} points, expected {expected}")
    c.delete("recipes", points_selector=models.FilterSelector(filter=flt))
    return n

show()

# %% [markdown]
# **Exercise 1.** Read the current version, then write with it: applied, version goes up by one.
# The second call reuses the old number, matches nothing and is skipped (minutes stay 45). The soup
# no longer passes `minutes <= 30`, so it leaves the quick page.

# %%
seen = client12.retrieve("recipes", ids=[11])[0].payload["version"]
ok, after = save_if_version(11, {"minutes": 45}, seen)
print("first write applied:", ok, "| minutes", after["minutes"], "| version", after["version"])
ok, after = save_if_version(11, {"minutes": 15}, seen)          # stale version number
print("stale write applied:", ok, "| minutes", after["minutes"], "| version", after["version"])
show()

# %% [markdown]
# **Exercise 2.** `MatchText(text="chocolate")` finds the two chocolate recipes by description. Mark
# them with `set_payload` on the filter, count live recipes with `must_not`, then purge with the
# guarded delete, expecting exactly 2.

# %%
choc = models.Filter(must=[models.FieldCondition(key="description", match=models.MatchText(text="chocolate"))])
print("chocolate recipes:", [r.payload["title"] for r in client12.scroll("recipes", scroll_filter=choc)[0]])
client12.set_payload("recipes", payload={"retired": True}, points=choc)
retired = models.FieldCondition(key="retired", match=models.MatchValue(value=True))
print("live:", client12.count("recipes", count_filter=models.Filter(must_not=[retired])).count)
print("purged:", safe_delete(client12, models.Filter(must=[retired]), expected=2))
print("final count:", client12.count("recipes").count)
client12.close()

# %% [markdown]
# ## Lesson 13
# Shared setup from lesson 13: the recipes, their vectors, the cached "something warm for a cold
# day" query, and a fresh Edge shard holding all 50 recipes.

# %%
import os, shutil
import numpy as np
import pandas as pd
from qdrant_edge import (CountRequest, Distance, EdgeConfig, EdgeOptimizersConfig, EdgeShard,
                         EdgeVectorParams, FieldCondition, Filter, HnswIndexConfig, Point, Query,
                         QueryRequest, RangeFloat, SearchParams, UpdateOperation)

recipes13 = pd.read_csv("../data/recipes_50.csv")
emb13 = np.load("../data/recipe_embeddings_minilm.npz")["doc_emb"]
warm_query = np.load("../data/query_embeddings_minilm.npz")["query_emb"][0].tolist()
EDGE_SOL = "../data/cache/edge_sol13"
shutil.rmtree(EDGE_SOL, ignore_errors=True)
os.makedirs(EDGE_SOL)
shard = EdgeShard.create(EDGE_SOL, EdgeConfig(vectors=EdgeVectorParams(size=384, distance=Distance.Cosine)))
shard.update(UpdateOperation.upsert_points([
    Point(id=int(r.id), vector=emb13[i].tolist(), payload={"title": r.title, "minutes": int(r.minutes)})
    for i, r in enumerate(recipes13.itertuples())]))

def edge_ask(shard, k=3):
    hits = shard.query(QueryRequest(
        query=Query.Nearest(warm_query), limit=k, with_payload=True,
        filter=Filter(must=[FieldCondition(key="minutes", range=RangeFloat(lte=30))])))
    return [[h.payload["title"], round(h.score, 3)] for h in hits]

print("points:", shard.count(CountRequest()), "| top 3:", edge_ask(shard))

# %% [markdown]
# **Exercise 1.** `delete_points` takes a list of ids. After `close()` and `load()` the delete is
# still there: 49 points, and Gazpacho has left the top 3 (the next quick recipe moves up).

# %%
shard.update(UpdateOperation.delete_points([50]))
shard.close()
shard = EdgeShard.load(EDGE_SOL)
print("points after reload:", shard.count(CountRequest()))
print("top 3:", edge_ask(shard))
shard.close()

# %% [markdown]
# **Exercise 2.** Same 5,000 random vectors and queries as the lesson (seed 13), same Edge shard
# settings. Recall climbs with `hnsw_ef`; the smallest value that reaches 0.9 is usually 40 or 80.
# Graph building has no seed, so recall moves by up to about 0.03 between runs and the answer can
# flip between neighbouring values: expect roughly 40-80.

# %%
rng = np.random.default_rng(13)
N, D = 5000, 64
big = rng.normal(size=(N, D)).astype(np.float32)
big /= np.linalg.norm(big, axis=1, keepdims=True)
big_queries = rng.normal(size=(50, D)).astype(np.float32)
big_queries /= np.linalg.norm(big_queries, axis=1, keepdims=True)
true_top10 = np.argsort(-(big_queries @ big.T), axis=1)[:, :10]

path = "../data/cache/edge_sol13_big"
shutil.rmtree(path, ignore_errors=True)
os.makedirs(path)
s = EdgeShard.create(path, EdgeConfig(
    vectors=EdgeVectorParams(size=D, distance=Distance.Cosine),
    hnsw_config=HnswIndexConfig(m=16, ef_construct=100, full_scan_threshold=10),
    optimizers=EdgeOptimizersConfig(indexing_threshold=10)))
s.update(UpdateOperation.upsert_points([Point(id=i, vector=big[i].tolist()) for i in range(N)]))
s.optimize()
rec = {}
for ef in [10, 20, 40, 80, 160]:
    found = [[p.id for p in s.query(QueryRequest(query=Query.Nearest(q.tolist()), limit=10,
                                                 params=SearchParams(hnsw_ef=ef)))] for q in big_queries]
    rec[ef] = round(float(np.mean([len(set(f) & set(t)) / 10 for f, t in zip(found, true_top10)])), 2)
print("recall by hnsw_ef:", rec)
print("smallest hnsw_ef with recall >= 0.9:", next((ef for ef, r in rec.items() if r >= 0.9), None))
s.close()

# %% [markdown]
# ## Lesson 14
# Shared setup from lesson 14: the 2,000 recipes, their saved vectors, `recipe_id` (uuid5 of the
# slug), `to_points`, and `make_collection` with the payload indexes.

# %%
import uuid
recipes2k = pd.read_csv("../data/recipes_2000.csv")
emb2k = np.load("../data/recipe_embeddings_minilm_2000.npz")["doc_emb"]
RECIPE_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://example.com/recipes/")

def recipe_id(slug):
    return str(uuid.uuid5(RECIPE_NS, slug))

def to_payload14(row):
    return {"slug": row.slug, "title": row.title, "description": row.description,
            "cuisine": row.cuisine, "vegetarian": bool(row.vegetarian), "minutes": int(row.minutes)}

def to_points(df, emb):
    return [models.PointStruct(id=recipe_id(r.slug), vector=emb[i].tolist(), payload=to_payload14(r))
            for i, r in enumerate(df.itertuples())]

def make_collection(client, name="recipes"):
    if client.collection_exists(name):
        client.delete_collection(name)
    client.create_collection(name, vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE))
    return name

c14 = QdrantClient(":memory:")
print(len(recipes2k), "recipes |", emb2k.shape)

# %% [markdown]
# **Exercise 1.** Count before and after an `INSERT_ONLY` load. Rows that are new to the
# collection are written; existing ids are skipped, so the third call adds nothing.

# %%
def nightly_load(client, df, emb, name="recipes"):
    before = client.count(name).count
    client.upload_points(name, to_points(df, emb), batch_size=256,
                         update_mode=models.UpdateMode.INSERT_ONLY, wait=True)
    return client.count(name).count - before

make_collection(c14)
print("first 1,500:", nightly_load(c14, recipes2k[:1500], emb2k[:1500]))
print("all 2,000:  ", nightly_load(c14, recipes2k, emb2k))
print("again:      ", nightly_load(c14, recipes2k, emb2k))

# %% [markdown]
# **Exercise 2.** `upload_collection` takes columns: the NumPy matrix as `vectors`, and lists of
# payloads and ids in the same order.

# %%
make_collection(c14)
c14.upload_collection("recipes", vectors=emb2k,
                      payload=[to_payload14(r) for r in recipes2k.itertuples()],
                      ids=[recipe_id(s) for s in recipes2k.slug], batch_size=256, wait=True)
print("points:", c14.count("recipes").count)
print("ramen:", c14.retrieve("recipes", ids=[recipe_id("ramen")])[0].payload["title"])
c14.close()

# %% [markdown]
# ## Lesson 15
# Shared setup from lesson 15: the 2,000 recipes in a local collection with `uuid5(slug)` ids, the
# finder's query cache, `check_args` and `build_filter` (re-declared so this section runs on its own).

# %%
import uuid, warnings
warnings.filterwarnings("ignore", message="Payload indexes have no effect")
recipes15 = pd.read_csv("../data/recipes_2000.csv")
emb15 = np.load("../data/recipe_embeddings_minilm_2000.npz")["doc_emb"]
fcache = np.load("../data/query_embeddings_minilm_finder.npz")
finder_cache = dict(zip(fcache["queries"].tolist(), fcache["query_emb"], strict=True))
NS15 = uuid.uuid5(uuid.NAMESPACE_URL, "https://example.com/recipes/")
rid = lambda slug: str(uuid.uuid5(NS15, slug))
CUISINES15 = sorted(recipes15.cuisine.unique())

c15 = QdrantClient(":memory:")
c15.create_collection("recipes", vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE))
c15.upload_points("recipes", [models.PointStruct(
    id=rid(r.slug), vector=emb15[i].tolist(),
    payload={"title": r.title, "description": r.description, "cuisine": r.cuisine,
             "vegetarian": bool(r.vegetarian), "minutes": int(r.minutes)})
    for i, r in enumerate(recipes15.itertuples())])
print("points:", c15.count("recipes").count)

# %% [markdown]
# **Exercise 1.** A string becomes a one-item list, every name is checked, and the condition is
# `MatchAny` (lesson 11): exact match against any value in the list.

# %%
def build_filter15(vegetarian=None, max_minutes=None, cuisine=None):
    must = []
    if vegetarian is not None:
        must.append(models.FieldCondition(key="vegetarian", match=models.MatchValue(value=vegetarian)))
    if max_minutes is not None:
        must.append(models.FieldCondition(key="minutes", range=models.Range(lte=max_minutes)))
    if cuisine is not None:
        names = [cuisine] if isinstance(cuisine, str) else list(cuisine)
        bad = [c for c in names if c not in CUISINES15]
        if bad:
            raise ValueError(f"unknown cuisine(s) {bad}; choose from {CUISINES15}")
        must.append(models.FieldCondition(key="cuisine", match=models.MatchAny(any=names)))
    return models.Filter(must=must) if must else None

def find15(text, k=5, **rules):
    hits = c15.query_points("recipes", query=finder_cache[text].tolist(),
                            query_filter=build_filter15(**rules), limit=k).points
    return [(h.payload["title"], h.payload["cuisine"], h.payload["minutes"], round(h.score, 3)) for h in hits]

page = find15("a hot curry", cuisine=["Indian", "Thai"], vegetarian=True)
for row in page:
    print(row)
print("all Indian or Thai:", all(c in ("Indian", "Thai") for _, c, _, _ in page))

# %% [markdown]
# **Exercise 2.** `query` accepts a point id (lesson 10): Qdrant uses that point's stored vector.
# The filter works exactly as with a text query. Beef stew itself fails the filter anyway (meat,
# 180 minutes), so it cannot appear.

# %%
def find_like(slug, k=5, **rules):
    hits = c15.query_points("recipes", query=rid(slug), query_filter=build_filter15(**rules), limit=k).points
    return [(h.payload["title"], h.payload["minutes"], round(h.score, 3)) for h in hits]

for row in find_like("beef-stew", vegetarian=True, max_minutes=30):
    print(row)
c15.close()
