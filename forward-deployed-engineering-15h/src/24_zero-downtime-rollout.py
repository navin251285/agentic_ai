# %% [markdown]
# # 24 · Zero-downtime changes: rolling upgrades and migrations
#
# Level L5 · Part 3 · professional · ~25 min · builds on 14, 23
#
# Needs Docker with Compose v2 (`docker compose version`), about 2 GB of free RAM and port 8240 free. The cells tagged `needs-docker` start three containers: two order nodes and a proxy. When they are skipped, the checks after them print the output recorded from an earlier real Docker run, labelled as such. That recorded output is not live: it is saved from a real run and replayed here.

# %% [markdown]
# ## Goal
#
# By the end you can roll a new version of a service and a new column in its orders file into a running two-node deployment with zero failed requests, and roll back one bad node with one command.

# %% [markdown]
# ## Why it matters
#
# Lesson 14 put the service in a container and gave it a rollback. A rollback does not help if the release itself takes the service down. Two things do that: restarting the only copy of the service, and changing the data shape and the code in one step, so that old code or new code meets a file it cannot read.
#
# The next cell counts the first problem for an invented customer peak. Plain Python, no Docker yet.

# %%
requests_per_second = 20  # invented customer peak
restart_seconds = 15      # invented: start the new container and pass its health check
print("one node, restarted in place:", requests_per_second * restart_seconds, "failed requests per release if nothing retries")
print("two nodes, one at a time: expected 0 failed requests, measured in Step 6 (assumes one node carries the whole peak)")

# %% [markdown]
# - **Without it:** every release stops the service for the restart time, and a schema change that lands in the same release as the code breaks one side or the other.
# - **With it:** nodes are replaced one at a time behind a proxy, each one must pass a health check before the next one starts, and a data change is made in its own step that old code can ignore.
# - **When you don't need it:** a demo nobody uses, or a service the customer lets you stop in an agreed maintenance window. A live order system needs it.

# %% [markdown]
# ## The idea
#
# A **rolling upgrade** replaces the copies of a service one at a time. A **proxy** in front sends each request to a copy that is up, and a **health check** tells the rollout when a new copy is ready to take traffic. A schema change follows **expand, deploy, contract**: first add the new column with a safe default (old code ignores it), then deploy code that uses it, and only later remove the old column, once no copy needs it.
#
# Analogy: a motorway with roadworks. One lane closes at a time, traffic keeps moving in the other, and nobody closes the bridge to rewire it.

# %% [markdown]
# ## Picture
#
# The customer's clients talk to one proxy. The proxy spreads requests over two nodes. Both nodes read the same orders file, mounted read-only.

# %% [markdown]
# ```mermaid
# flowchart LR
#     C[Clients] -->|localhost:8240| P[proxy: nginx]
#     P -->|retry on the other node if one is down| A[node-a]
#     P --> B[node-b]
#     F[(orders.csv, read-only)] -.-> A
#     F -.-> B
# ```

# %% [markdown]
# ## Before you start
#
# The setup cell creates the folders for this lesson and copies the orders file. Its source is `../data/05/orders.csv`, the synthetic orders file from lesson 05 (invented, no real customer data). The copy is the working file: the migration changes the copy, never the source.

# %%
import difflib, json, os, shutil, subprocess, sys, threading, time
from collections import Counter
from datetime import date
from pathlib import Path

import httpx
import pandas as pd

sys.path.insert(0, "..")
from tut_env import load

load()
DOCKER_RAN, CAPTURED = False, {}  # DOCKER_RAN is set by the needs-docker cells; CAPTURED holds their real outputs
COMPOSE = ["docker", "compose", "-p", "tut-forward-deployed-engineering-15h-24", "-f", "../infra/compose/rollout-24.yml", "--env-file", "../.env"]  # one project for this lesson
PROXY, ORDER = "http://localhost:8240", "BB-1118"  # every probe asks the proxy for this order
REC = json.loads(Path("../data/recorded/24.json").read_text())  # saved from a real Docker run
LABEL = f"recorded output from the last real Docker run on {REC['_recorded']} (timing-based: counts and uptimes change on every run)"
Path("../data/24").mkdir(parents=True, exist_ok=True)
ORDERS = Path("../data/24/orders.csv")
_ = shutil.copy("../data/05/orders.csv", ORDERS)
print("working copy ready:", ORDERS.name, "(a copy of the invented lesson 05 orders)")

# %% [markdown]
# Next, the helpers. `compose` runs Docker Compose for this lesson's project only, and `versions` picks each node's tag and code file for one call. `probe` asks the proxy for one order and returns the status and the version that answered. `traffic` runs in a background thread during the rollout (Step 6) and keeps probing.
#
# `reload_proxy` tells nginx to pick up a node's new address. nginx resolves node names once, when it starts. A recreated container gets a new IP, so reload nginx after every replacement (or use a resolver in production). The reload is part of the rollout, not an extra step.

# %%
V1, V2 = {"tag": "1.0.0", "src": "24/orders_service_1_0_0.py"}, {"tag": "2.0.0", "src": "24/orders_service_2_0_0.py"}


def compose(*args, extra=None):
    return subprocess.run([*COMPOSE, *args], capture_output=True, text=True, timeout=900,
                          env={**os.environ, **(extra or {})})


def versions(a, b):
    return {"NODE_A_TAG": a["tag"], "NODE_A_SRC": a["src"], "NODE_B_TAG": b["tag"], "NODE_B_SRC": b["src"]}


def probe():
    try:
        r = httpx.get(f"{PROXY}/orders/{ORDER}", timeout=3)
        return r.status_code, (r.json().get("version") if r.status_code == 200 else None)
    except httpx.HTTPError as err:
        return type(err).__name__, None


def traffic(stop, seen):
    while not stop.is_set():
        seen.append(probe())
        time.sleep(0.05)


def reload_proxy():
    return compose("exec", "-T", "proxy", "nginx", "-s", "reload").returncode


# %% [markdown]
# ## Step by step
#
# ### Step 1: the orders file and version 1 of the service
#
# The file has one row per order line. The service reads the columns it needs by name and ignores the rest. The `ordered_at` column mixes two date formats (date formats are messy on purpose, lesson 05). Duplicate order ids are in the file on purpose; the service keeps the last row per id.

# %%
print(pd.read_csv(ORDERS).head(3).to_string(index=False))

# %% [markdown]
# The two versions are shipped with the lesson in `apps/24/`. Version 1.0.0 loads the file once at start and answers one route. It has no idea about a `missing_items` column, and it does not need one.
#
# Version 2.0.0 uses the new column. It checks the header when it starts: if the column is missing, it refuses to start. A clear error at start is better than a wrong answer later. Its changes are the version string, that header check and the reply. These are the lines that mention the new column; the `raise` line is the error Step 4 will show:

# %%
v2 = Path("../apps/24/orders_service_2_0_0.py").read_text().splitlines()
print("\n".join(l.strip() for l in v2 if "missing_items" in l))

# %% [markdown]
# ### Step 2: the Dockerfile, the Compose file and the proxy
#
# The three files ship with the lesson: `apps/24/Dockerfile`, `infra/compose/rollout-24.yml` and `infra/compose/rollout-24/nginx.conf`. Compose runs three containers: `node-a`, `node-b` and `proxy`. `APP_FILE` picks the code that goes into each image, and each image gets a tag per release, so the previous version stays on the host for a rollback. Each node has its own tag and code file, set per call; both mount the orders file read-only. The proxy sends each request to node-a or node-b, and if one refuses or times out, it tries the other, so a client does not see the restart. The next cell prints the lines that matter.

# %%
keys = ("APP_FILE:", "/data:ro", "urlopen", "service_healthy", "proxy_next_upstream")
files = ["apps/24/Dockerfile", "infra/compose/rollout-24.yml", "infra/compose/rollout-24/nginx.conf"]
lines = [l.strip() for f in files for l in Path(f"../{f}").read_text().splitlines() if any(k in l for k in keys)]
print("\n".join(dict.fromkeys(lines)))  # each distinct line once

# %% [markdown]
# ### Step 3: start version 1 on both nodes
#
# `up --build --wait` builds the images, starts all three containers and waits until both nodes report healthy. Then the proxy answers. Each probe shows which version answered.

# %% tags=["needs-docker"]
DOCKER_RAN = True
up = compose("up", "-d", "--build", "--wait", extra=versions(V1, V1))
ps = compose("ps", "--format", "table {{.Service}}\t{{.Status}}")
CAPTURED["up_v1"] = f"exit code: {up.returncode}\n{ps.stdout.strip()}"
CAPTURED["up_probes"] = str(Counter(probe() for _ in range(5)))
print(CAPTURED["up_v1"], CAPTURED["up_probes"], sep="\n")

# %% [markdown]
# If Docker was skipped, this shows the start output recorded from the last real run.

# %%
if not DOCKER_RAN:
    print(LABEL, REC["up_v1"], "probes:", REC["up_probes"], sep="\n")

# %% [markdown]
# ### Step 4: the wrong order, and a rollback
#
# The release team deploys version 2.0.0 to node-a before the file has the new column. Version 2 refuses to start. `--wait` reports the failure, and the rollout must stop there. Node-b keeps serving version 1, so clients see no errors. That failed `--wait` is the health gate: a non-zero exit code is the signal to stop the rollout, and Step 6 checks it.

# %% tags=["needs-docker"]
bad = compose("up", "-d", "--no-deps", "--build", "--wait", "node-a", extra=versions(V2, V1))
logs = compose("logs", "node-a", "--no-color", "--tail", "2")
CAPTURED["bad_start"] = f"exit code: {bad.returncode}"
CAPTURED["bad_logs"] = (logs.stdout + logs.stderr).strip()
CAPTURED["bad_probes"] = str(Counter(probe() for _ in range(5)))
print(CAPTURED["bad_start"], CAPTURED["bad_logs"], CAPTURED["bad_probes"], sep="\n")

# %% [markdown]
# If Docker was skipped, this shows the output recorded from the last real run.

# %%
if not DOCKER_RAN:
    print(LABEL, REC["bad_start"], REC["bad_logs"], "probes while node-a is down:", REC["bad_probes"], sep="\n")

# %% [markdown]
# The rollback is the same command as a normal start, with the old tag. The 1.0.0 image is still on this machine, so nothing is built. Then the proxy is reloaded, because nginx must find node-a's new address: the reload is part of the rollback.

# %% tags=["needs-docker"]
back = compose("up", "-d", "--no-deps", "--wait", "node-a", extra=versions(V1, V1))
CAPTURED["rollback"] = f"exit code: {back.returncode} | proxy reload: {reload_proxy()} | probes: {Counter(probe() for _ in range(5))}"
print(CAPTURED["rollback"])

# %% [markdown]
# If Docker was skipped, this shows the rollback output recorded from the last real run.

# %%
if not DOCKER_RAN:
    print(LABEL, REC["rollback"], sep="\n")

# %% [markdown]
# ### Step 5: expand the file first
#
# The migration adds `missing_items` with a safe default of 0. This is the expand step: it changes only the file, and it is safe for version 1, which reads its columns by name and ignores this one. The two invented orders below are marked as short, so the new code has something to show.

# %%
orders = pd.read_csv(ORDERS)
orders["missing_items"] = 0
orders.loc[orders.order_id.isin(["BB-1118", "BB-1063"]), "missing_items"] = 1  # invented: two short orders
orders.to_csv(ORDERS, index=False)
print("after: ", pd.read_csv(ORDERS).columns.tolist())

# %% [markdown]
# Version 1 read the file only at start, so it keeps answering after this change and never asks for the new column. Step 6 checks this under traffic.

# %% [markdown]
# ### Step 6: the rolling upgrade under traffic
#
# A background client asks for one order all the time. The rollout replaces node-a, reloads the proxy, waits a second, then does node-b. Every answer the client gets is kept. The rollout is good only if no answer is an error.

# %% tags=["needs-docker"]
stop, seen = threading.Event(), []
client = threading.Thread(target=traffic, args=(stop, seen))
client.start()
steps = []
for node, env_for_call in [("node-a", versions(V2, V1)), ("node-b", versions(V2, V2))]:
    up = compose("up", "-d", "--no-deps", "--build", "--wait", node, extra=env_for_call)
    steps.append(f"{node}: exit {up.returncode}")
    if up.returncode != 0:
        break  # the health gate: a node that fails its health check stops the rollout
    reload_proxy()
    time.sleep(1)
stop.set()
client.join()
statuses = Counter(status for status, _ in seen)
CAPTURED["rolling"] = (f"{steps}\nanswers: {len(seen)} | status: {dict(statuses)} | failed: {len(seen) - statuses[200]}\n"
                       f"versions seen: {dict(Counter(v for _, v in seen if v))}")
print(CAPTURED["rolling"])

# %% [markdown]
# If Docker was skipped, this shows the rolling-upgrade result recorded from the last real run. Your own run will show a different answer count and version split; the number that must stay the same is `failed: 0`.

# %%
if not DOCKER_RAN:
    print(LABEL, REC["rolling"], sep="\n")

# %% [markdown]
# ## At work
#
# - **Change windows and a written rollback.** Customers approve releases in windows, and the change board asks for the rollback step first. Keeping the previous image tag (lesson 14) makes that step one command. → lesson 28 rehearses a failure before it happens.
# - **Schema changes are a common cause of failed upgrades.** Teams split a column change into expand, deploy and contract releases, and keep the old column until every node runs the new code. → lesson 31 puts this in one customer's delivery plan.
# - **Health gates stop the rollout.** Orchestrators (Compose here, ECS or Kubernetes at the customer) move on only when the new copy is healthy. → lesson 28 covers the fallback when a dependency fails during a release.

# %% [markdown]
# ## Common mistakes
#
# Reading a column before the file has it. Code that indexes a missing column fails like this (v2 checks the header and stops at start instead):

# %% tags=["raises-exception"]
old_row = {"order_id": "BB-1118", "item": "bread", "qty": "2", "unit": "each"}  # a row before the migration
print(old_row["missing_items"])  # KeyError: the column is not there yet

# %% [markdown]
# The fix is the order of the steps, not a try/except: expand the file, then deploy the code that reads the column, then (much later, in its own release) contract. Renaming `qty` to `quantity` in one release breaks every node that still runs the old code, and a rollout that replaces all nodes at once has no healthy node left to answer.

# %% [markdown]
# ## Production checklist
#
# - [ ] The data change ships in its own release, and only adds (expand). Removing a column is a later release.
# - [ ] Each node has a health check, and the rollout stops at the first node that fails it.
# - [ ] The remaining nodes can carry the full peak alone while one is replaced.
# - [ ] The previous image tag and the previous file shape stay until the rollback window closes.
# - [ ] A traffic test runs during the rollout, and its failed-request count is the release evidence.
# - [ ] The change has a written rollback step and runs in an agreed change window.

# %% [markdown]
# ## Try it
#
# Your next release (2.1.0) renames the `qty` column to `quantity`. Write `is_safe(plan)`. A plan is a list of steps: `("expand", col)` adds a column, `("contract", col)` removes one, and `("deploy", version, cols)` starts code that reads those columns. The file starts with the columns of `orders.csv` plus `missing_items`. Steps run in order: a deploy is unsafe if any column it reads is missing at that moment (including one already contracted). Hint: track a set of columns; return False on the first deploy whose columns are not all in it.

# %%
def is_safe(plan):
    # your code here
    ...


good = [("expand", "quantity"), ("deploy", "2.1.0", ["quantity"]), ("contract", "qty")]
bad = [("deploy", "2.1.0", ["quantity"]), ("expand", "quantity"), ("contract", "qty")]
print("good plan:", is_safe(good), "| bad plan:", is_safe(bad), "| expected: True False")

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def is_safe(plan):
    columns = {"order_id", "store", "item", "qty", "unit", "ordered_at", "missing_items"}
    for step in plan:
        if step[0] == "expand":
            columns.add(step[1])
        elif step[0] == "contract":
            columns.discard(step[1])
        elif step[0] == "deploy" and not set(step[2]) <= columns:
            return False
    return True


good = [("expand", "quantity"), ("deploy", "2.1.0", ["quantity"]), ("contract", "qty")]
bad = [("deploy", "2.1.0", ["quantity"]), ("expand", "quantity"), ("contract", "qty")]
print("good plan:", is_safe(good), "| bad plan:", is_safe(bad), "| expected: True False")

# %% [markdown]
# ## Tear down
#
# Stop and remove this lesson's containers and network. The images stay, so a rollback still works next time. With Docker, the next cell also saves this run's real outputs in `data/24/captured.json`. To refresh the recording, copy `data/24/captured.json` to `data/recorded/24.json`; its `_recorded` date is printed with every fallback. If Docker was skipped, this cell does nothing.

# %% tags=["needs-docker"]
down = compose("down", "--remove-orphans")
print("exit code:", down.returncode, "| images kept")
_ = Path("../data/24/captured.json").write_text(json.dumps({**CAPTURED, "_recorded": date.today().isoformat()}, indent=1))

# %% [markdown]
# ## Recap
#
# - **Rolling upgrade**: one node at a time behind a proxy; the proxy retries on the node that is up, and the rollout stops at the first failed health check.
# - **Expand, deploy, contract**: add the new column with a safe default, deploy code that reads it, and remove the old column in a later release.
# - **Rollback**: the previous tag is still on the host, so one `up --wait` restores the node that failed.
# - **Proof**: count the failed requests during the rollout. Zero is the evidence the change board needs.
# - Go deeper: the restricted network is lesson 15 and the failure drill is lesson 28.
#
# **Interview:** "How do you change the code and the data of a running service without downtime?" Strong answer: expand the data in a backward-compatible release, roll the code out one node at a time behind a health-checked proxy, keep the previous image for rollback, and contract only after every node runs the new code.
