# %% [markdown]
# # 23 · Per-customer configuration and multi-tenancy
#
# Level L5 · Part 3 · professional · ~30 min · builds on 14
#
# No Docker, no model and no network: everything runs on your laptop with the files in `../data`. Lesson 14 deployed one service per customer environment. Here one service serves many stores, and each store gets its own files and its own limits.

# %% [markdown]
# ## Goal
#
# By the end you can serve 12 Basket Bazaar stores from one FastAPI service, keep each store's orders in its own CSV file and its limits in one Excel workbook, and show that a request for one store cannot read another store's order.

# %% [markdown]
# ## Why it matters
#
# Basket Bazaar now has 12 stores. Each store wants its own limits, and each store must see only its own orders. Without a tenancy design you have three bad options:
#
# 1. One copy of the service per store. Twelve copies in three environments are 36 deployments to patch.
# 2. One shared file where the store is just a column, and a lookup by order id alone. Any caller who knows an id reads it, whichever store it belongs to.
# 3. Limits typed into the code. Each store change becomes a code release.
#
# The next two cells count the first option and show the second one going wrong.

# %%
import pandas as pd

raw = pd.read_csv("../data/05/orders.csv")  # one shared export: all 12 stores in one file
stores = raw.store.nunique()
environments = 3  # test, staging, production (invented for the count)
print(f"copy per store: {stores} services x {environments} environments = {stores * environments} deployments to patch")


def naive_get_order(order_id):  # no store anywhere in the lookup
    return raw[raw.order_id == order_id][["order_id", "store", "item", "qty"]]


print(naive_get_order("BB-1118").to_string(index=False))

# %% [markdown]
# The naive lookup returned Store 07's two lines to a caller who never named Store 07. `naive_get_order(order_id)` takes only an id, so it cannot tell which store is asking. In a real service, that caller could be the Store 02 app.
#
# - **Without it:** one copy per store, or one shared file that trusts the order id alone. Each store change is a release, and one bad lookup leaks another customer's data.
# - **With it:** one service and one image. A store is a key in a config. Its orders are its own file. Every lookup starts from the store key, and the key is checked against the list of known stores first.
# - **When you don't need it:** one customer on one server. Then one file and no config is enough.

# %% [markdown]
# ## The idea
#
# A **tenant** is one unit whose data must stay apart, such as a customer or, here, one store. There are two ways to keep tenants apart. In **silo** tenancy each customer gets its own deployment: strong separation, many copies to run. In **pool** tenancy one deployment serves everyone, and each tenant's data is kept apart by a key, a schema or a file. This lesson uses a pool with one file per store, and per-tenant limits in a config that is checked when it loads.
#
# Analogy: a shared office building with a lockable cabinet for each company. The building is the service. The cabinet is the store's file. The list at the front desk decides which cabinet a visitor may open, and the visitor's own words never pick the cabinet.

# %% [markdown]
# ## Picture
#
# A request names a store. The service checks the name against the known list before it touches any file. Limits come from that store's row in the workbook.

# %% [markdown]
# ```mermaid
# flowchart LR
#     R[Request: /stores/store-07/...] --> C{store-07 on the known list?}
#     C -->|no| X[404: unknown store]
#     C -->|yes| F[stores/store-07/orders.csv]
#     W[config/store_limits.xlsx] --> P[store-07 limits]
#     C --> P
#     P --> F
# ```

# %% [markdown]
# ## Step by step

# %% [markdown]
# ### Step 1: the data
#
# `../data/05/orders.csv` is a grocery order export with one row per order line: 247 rows and 12 stores. It was made for this course by the lesson 05 code, with a fixed random seed, so it holds no real customer data. Lesson 05 describes the same export as 120 made-up orders, written as 247 rows with copies and faults. The file is generated, not downloaded, so `data/SOURCES.md` is not needed for it. It is already on disk. Lesson 05 showed how to clean it. Here we only drop the exact duplicate rows and add a store id that works as a folder name.

# %%
import shutil
from pathlib import Path

ROOT = Path("../data/23")  # this lesson's run-time files, rebuilt on every run
shutil.rmtree(ROOT, ignore_errors=True)

print(raw.head(5).to_string(index=False))  # ignore the date formats here, this lesson doesn't use them
clean = raw.drop_duplicates().copy()
clean["store_id"] = clean.store.str.lower().str.replace(" ", "-")  # "Store 07" -> "store-07"
print(len(raw), "rows,", len(clean), "after removing duplicates,", clean.store_id.nunique(), "stores")

# %% [markdown]
# ### Step 2: one CSV file per store
#
# Each store gets its own folder and its own `orders.csv`. The folder name is the store id. Code that opens one store's folder cannot open another's by accident, and the separate file is something you can show a customer's security team.

# %%
for store_id, rows in clean.groupby("store_id"):
    folder = ROOT / "stores" / store_id
    folder.mkdir(parents=True)
    rows.drop(columns="store_id").to_csv(folder / "orders.csv", index=False)

files = sorted((ROOT / "stores").glob("*/orders.csv"))
print(len(files), "files, for example the second file:", files[1].relative_to(ROOT))  # files[1] is store-02
print(files[1].read_text().splitlines()[:2])

# %% [markdown]
# ### Step 3: per-store limits in one Excel workbook
#
# Store operations edit their limits in Excel, not in code. The workbook has one row per store. This lesson writes it from code so that it runs. In a real engagement the customer owns this file. Store 09's limit is lower than the others; that is an invented example to show that limits differ by store.

# %%
config_dir = ROOT / "config"
config_dir.mkdir(parents=True)

limits = pd.DataFrame({"store_id": sorted(clean.store_id.unique())})
limits["max_qty_per_line"] = 2000
limits.loc[limits.store_id == "store-09", "max_qty_per_line"] = 1000  # invented: a tighter limit for one store
limits["late_after_hours"] = 24
limits.to_excel(config_dir / "store_limits.xlsx", sheet_name="limits", index=False)

print(pd.read_excel(config_dir / "store_limits.xlsx", sheet_name="limits").head(3).to_string(index=False))

# %% [markdown]
# ### Step 4: check each row when it loads
#
# A cell typed by hand can be text, empty or zero. Load every row into a model that checks it. A bad row then stops the load with a clear message instead of changing a limit without anyone noticing. The `store_id` pattern also means only ids of one shape can ever be used. `TENANTS` and `ORDERS` load at startup, so editing the workbook needs a restart or reload.

# %%
from pydantic import BaseModel, Field


class StoreConfig(BaseModel):
    store_id: str = Field(pattern=r"^store-\d{2}$")
    max_qty_per_line: int = Field(gt=0)
    late_after_hours: int = Field(gt=0)


rows = pd.read_excel(config_dir / "store_limits.xlsx", sheet_name="limits").to_dict("records")
TENANTS = {row["store_id"]: StoreConfig(**row) for row in rows}
print(len(TENANTS), "stores configured")
print(TENANTS["store-09"].model_dump())

# %% [markdown]
# ### Step 5: one service, every request scoped to one store
#
# The service has one route family, `/stores/{store_id}/...`. The store id is looked up in `TENANTS`, and only then in `ORDERS`. The lookup is the check. An id that is not on the list gets a 404. The code never builds a file path from what the caller sent. The files are read once, at startup, so a request cannot point the service at any other file.

# %%
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

app = FastAPI(title="Basket Bazaar, one service for many stores")
ORDERS = {sid: pd.read_csv(ROOT / "stores" / sid / "orders.csv") for sid in TENANTS}


def tenant(store_id: str) -> StoreConfig:
    """The only way in: an unknown store is a 404, never a file path built from the request."""
    if store_id not in TENANTS:
        raise HTTPException(404, detail="unknown store")
    return TENANTS[store_id]


@app.get("/stores/{store_id}/config")
def store_config(store_id: str):
    return tenant(store_id).model_dump()


@app.get("/stores/{store_id}/orders/{order_id}")
def get_order(store_id: str, order_id: str):
    cfg = tenant(store_id)
    lines = ORDERS[store_id]
    hit = lines[lines.order_id == order_id]
    if hit.empty:
        raise HTTPException(404, detail="order not found in this store")
    return {"order_id": order_id, "store_id": store_id,
            "lines": hit[["item", "qty", "unit"]].to_dict("records"),
            "over_limit": bool((hit.qty > cfg.max_qty_per_line).any())}

# %% [markdown]
# ### Step 6: try the boundary
#
# `TestClient` calls the app in the same process, so there is no server and no port. Three requests: the right store, the wrong store, and a store that is not on the list. `BB-1118` is an order of Store 07.

# %%
client = TestClient(app)

right = client.get("/stores/store-07/orders/BB-1118")
print("1 right store:", right.status_code, right.json()["lines"])
wrong = client.get("/stores/store-02/orders/BB-1118")
print("2 wrong store:", wrong.status_code, wrong.json()["detail"])
unknown = client.get("/stores/store-99/orders/BB-1118")
print("3 unknown store:", unknown.status_code, unknown.json()["detail"])

# %% [markdown]
# ### Step 7: the same rule, two limits
#
# Store 09's limit is 1000 and the other stores have 2000. The check reads the store's own row. To change Store 09's limit, you edit one cell in the workbook and reload, not the code. Here we take Store 09's largest line, so the example is the same on every run.

# %%
biggest = ORDERS["store-09"].sort_values("qty").iloc[-1]
print("store-09 limit:", client.get("/stores/store-09/config").json()["max_qty_per_line"])
check = client.get(f"/stores/store-09/orders/{biggest.order_id}").json()
print(f"store-09 line of qty {biggest.qty}: over_limit = {check['over_limit']}")

# %% [markdown]
# ## At work
#
# - **Silo or pool is a sales and security decision.** Customers often ask for their own deployment, and security reviews ask how tenants are kept apart (lesson 27). Silos cost one upgrade per customer → lesson 24.
# - **Per-tenant budgets.** Teams quote cost per tenant per month and cap spend per tenant → lesson 29.
# - **A tenant id on every log line and trace.** It finds one customer's incident without reading others' data → lesson 16.
# - **Bespoke forks pile up.** Keep one customer's differences in configuration, and move what all customers need into the product → lesson 25.
#
# Go deeper: row-level security and separate schemas need a database. This course keeps CSV and Excel only.

# %% [markdown]
# ## Common mistakes

# %% [markdown]
# **Mistake 1: a KeyError for an unknown store.** `ORDERS[store_id]` with an id that is not on the list raises an error. In a web service, an uncaught error becomes a 500 response, not a clean 404.

# %% tags=["raises-exception"]
ORDERS["store-99"].shape

# %% [markdown]
# The fix is the check in `tenant()` first: the unknown id gets a 404 with a reason, and the dictionary is read only for ids that passed.

# %% [markdown]
# **Mistake 2: building a path from the request.** This code joins the caller's text into a file path. The `..` in the id lets the caller name a different folder, or leave the store folder altogether, than the one that was checked.

# %%
def unsafe_path(store_id):
    return ROOT / "stores" / store_id / "orders.csv"


asked = unsafe_path("../stores/store-02")  # the caller asks for store 02's folder
print(asked)
print("it is store-02's file:", asked.resolve() == (ROOT / "stores" / "store-02" / "orders.csv").resolve())
print(unsafe_path("../.."))  # this one walks out of the stores folder altogether
print("on the known list:", "../stores/store-02" in TENANTS)

# %% [markdown]
# The first path is Store 02's file, though the request named no store of its own. The second `..` leaves `stores/` altogether. The point is the pattern: a caller's text must never become a path. `tenant()` already blocks it, because `"../stores/store-02"` is not in `TENANTS`, so it gets a 404 before any path is built. The fix is the same as before: look the id up in the known list and never join it into a path.

# %% [markdown]
# **Mistake 3: a bad limit typed into Excel.** A zero or a missing number must fail when the file loads, not when a customer's order is checked.

# %% tags=["raises-exception"]
StoreConfig(store_id="store-13", max_qty_per_line=0, late_after_hours=24)

# %% [markdown]
# The model rejects the zero with a clear message. Fix the cell in the workbook, then reload.

# %% [markdown]
# ## Production checklist
#
# - [ ] Every route that takes a store id checks it against the known list first.
# - [ ] No file path is built from request text.
# - [ ] Each config row is validated on load, and a bad row stops the load.
# - [ ] Each tenant's data is in its own file, and the file names are in the runbook.
# - [ ] Logs and traces carry the tenant id, and no other tenant's rows.

# %% [markdown]
# ## Try it
#
# Add a route `GET /stores/{store_id}/summary` that returns how many order lines the store has. Call `tenant()` first, so an unknown store gets a 404. Test it with a store that exists and one that does not. Hint: add it to the same `app` and reuse `client` from step 6.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
@app.get("/stores/{store_id}/summary")
def summary(store_id: str):
    tenant(store_id)
    return {"store_id": store_id, "lines": int(len(ORDERS[store_id]))}


client = TestClient(app)
print(client.get("/stores/store-05/summary").json())
print(client.get("/stores/store-99/summary").status_code)

# %% [markdown]
# ## Recap
#
# - One service serves many stores. A store is a tenant: a key in a config, one CSV file, one row of limits.
# - Check the store id against the known list before any read. Never build a file path from request text.
# - Limits live in an Excel workbook and are checked when they load, so a bad cell stops the load.
# - Silo gives strong separation with many deployments. Pool shares one deployment and keeps tenants apart by key or file.
#
# **Interview:** How do you keep two customers' data apart in one service? Strong answer: check the tenant key against a known list before any read, keep each tenant's data in its own file, schema or deployment, store per-tenant limits as validated config, and put the tenant id on every log and trace.
