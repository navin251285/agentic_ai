# %% [markdown]
# # 14 · Deploying into a customer environment with Docker Compose
#
# Level L3 · Part 2 · core · ~30 min · builds on 13
#
# Needs Docker with Compose v2 (`docker compose version`), about 2 GB of free RAM and port 8140 free. Cells tagged `needs-docker` start containers. When they are skipped, the checks after them print the recorded output from the last real run, labelled as such.

# %% [markdown]
# ## Goal
#
# Lesson 09 ran the workflow as a script on your laptop. In this lesson the triage service runs in a container on the customer's network, next to the customer's API.
#
# Note: v1.0.0 below is a stand-in. It labels whole orders ("missing items" or "complete"). Lessons 20 and 31 triage messages into five labels, and the service grows into that later.
#
# By the end you can package the Basket Bazaar triage service in a container image, start it next to the customer's API with one Compose file, release a bad version, and roll back to the last good image in one command.

# %% [markdown]
# ## Why it matters
#
# Until now the service ran on your laptop, in your Python. A customer runs it on their own machines, and each machine needs the same Python, the same packages and the same environment variables. Done by hand, every host repeats the same list, and each host can drift.
#
# The next cell counts a typical checklist for three invented hosts (a test, a staging and a production host). It is plain Python, no Docker yet.

# %%
by_hand = ["install Python 3.12", "create a virtualenv", "pip install the 4 packages",
           "copy the 2 service files", "set the environment variables",
           "start the API process", "start the mock customer API", "restart both after a reboot"]
hosts = 3  # test, staging, production
print(f"a typical checklist (invented): {len(by_hand)} steps per host, {len(by_hand) * hosts} steps for {hosts} hosts, and each host can drift")
print("with Compose: 1 command per host (up --wait), and the same image everywhere")

# %% [markdown]
# - **Without it:** a checklist per host. The steps differ a little on every machine, so the service works on one host and fails on the next.
# - **With it:** one image built once, and one Compose file that says which images run, which settings they get and which port is open.
# - **When you don't need it:** a demo on your own laptop. A customer system needs it.

# %% [markdown]
# ## The idea
#
# A **container image** is a sealed box with the code, its packages and its Python version. A **container** is a running copy of an image. A **Dockerfile** is the recipe that builds the image. **Docker Compose** starts several containers together, on a private network, from one YAML file. Each container gets its settings from the environment, so the same image runs in test and in production with different settings.
#
# Analogy: a shipping container. The goods are packed once, the truck does not care what is inside, and the port checks the seal, not each item.

# %% [markdown]
# ## Picture
#
# In this lesson the customer's network is a Compose project. Only the triage service has a port open to us. The customer API (`erp`) is reachable by name only from inside that network.

# %% [markdown]
# ```mermaid
# flowchart LR
#     A[Analyst or script on the laptop] -->|localhost:8140| T
#     subgraph net[Customer network, Compose project]
#         T[triage service v1.0.0] -->|http://erp:8000| E[erp: customer API, mock]
#     end
# ```

# %% [markdown]
# ## Before you start
#
# This is the first lesson that starts containers. Run the setup cell first. It loads the settings from lesson 13 (names and yes/no only; no values are printed) and creates the folders the files go to.
#
# `../.env` is the settings file Compose reads (`--env-file`), not a separate secret store. If setup prints `False` for a lesson 13 setting, finish lesson 13 first.

# %%
import json, os, shutil, subprocess, sys
from pathlib import Path

sys.path.insert(0, "..")
from tut_env import is_set, load

load()
DOCKER_RAN = False  # set to True by the cells tagged needs-docker
STACK = "tut-forward-deployed-engineering-15h-14"  # one Compose project name for this lesson only
COMPOSE = ["docker", "compose", "-p", STACK, "-f", "../infra/compose/customer-env-14.yml", "--env-file", "../.env"]
TRIAGE = "http://localhost:8140"
REC = json.loads(Path("../data/recorded/14.json").read_text())
for folder in ["../apps/14", "../infra/compose"]:
    Path(folder).mkdir(parents=True, exist_ok=True)

# %% [markdown]
# Next, the helpers and three checks: Docker on the path, the lesson 13 settings, and the lesson 13 mock API file.

# %%
def compose(*args, extra=None):
    """Run docker compose for this lesson's project. extra sets variables for this call only."""
    return subprocess.run([*COMPOSE, *args], capture_output=True, text=True, timeout=900,
                          env={**os.environ, **(extra or {})})


def tail(text, n=8):
    return "\n".join(text.strip().splitlines()[-n:])


def show_recorded(key):
    print("recorded output (Docker was not run in this build):")
    print(REC[key])


print("docker on PATH:", bool(shutil.which("docker")))
print("lesson 13 settings set:", all(is_set(n) for n in ["ERP_SIGNING_KEY", "ERP_READER_CLIENT_SECRET", "ERP_CREDIT_BOT_CLIENT_SECRET"]))
print("lesson 13 mock API file present:", Path("../apps/13/customer_api.py").exists())

# %% [markdown]
# Check that Compose v2 is installed. This cell starts nothing; the next one needs Docker only for its version line. The recording was made on Compose v5.2.0; any v2+ works.

# %% tags=["needs-docker"]
DOCKER_RAN = True
version = subprocess.run(["docker", "compose", "version", "--short"], capture_output=True, text=True)
print("Compose", version.stdout.strip() or version.stderr.strip())

# %% [markdown]
# If Docker was skipped, this shows the Compose version recorded in the last real run.

# %%
if not DOCKER_RAN:
    show_recorded("compose_version")

# %% [markdown]
# ## Step by step

# %% [markdown]
# ### Step 1: the service code (v1.0.0)
#
# The triage service asks the customer API for a token, reads the orders and labels one order: "missing items" when a line is short, otherwise "complete". The customer API is the mock from lesson 13, not a real system. The service reads its settings from the environment, not from the code. It has no secret in it.

# %%
%%writefile ../apps/14/triage_service.py
"""Basket Bazaar triage service, version 1.0.0 (lab, invented data)."""
import os

import httpx
from fastapi import FastAPI, HTTPException

VERSION = "1.0.0"
ERP_URL = os.environ["ERP_URL"]                        # the customer API, by its Compose service name
CLIENT_ID = os.environ["ERP_READER_CLIENT_ID"]         # the service account for reading orders
CLIENT_SECRET = os.environ["ERP_READER_CLIENT_SECRET"]  # injected from the secret store, never in the image
app = FastAPI(title="Basket Bazaar triage", version=VERSION)


def erp_token() -> str:
    """Client credentials grant (lesson 13): exchange the account's secret for a short-lived token."""
    r = httpx.post(f"{ERP_URL}/oauth/token", auth=(CLIENT_ID, CLIENT_SECRET),
                   data={"grant_type": "client_credentials", "scope": "orders:read"}, timeout=5)
    r.raise_for_status()
    return r.json()["access_token"]


@app.get("/health")
def health():
    return {"ok": True, "version": VERSION}


@app.get("/triage/{order_id}")
def triage(order_id: str):
    r = httpx.get(f"{ERP_URL}/orders", headers={"Authorization": f"Bearer {erp_token()}"}, timeout=5)
    if r.status_code != 200:
        raise HTTPException(502, detail=f"customer API returned {r.status_code}")
    order = next((o for o in r.json()["data"] if o["id"] == order_id), None)
    if order is None:
        raise HTTPException(404, detail="order not found")
    label = "missing items" if order["lines_short"] else "complete"
    return {"order_id": order_id, "label": label, "version": VERSION}

# %% [markdown]
# ### Step 2: the image recipe
#
# The Dockerfile starts from a pinned Python image (a tag with the full version, never `latest`), installs the pinned packages, copies one code file in and runs as a non-root user. Both lab services use this one recipe; `APP_FILE` picks the code. The package pins match the lesson's venv (RESEARCH.md, section 1).

# %%
%%writefile ../apps/14/requirements.txt
fastapi==0.162.0
uvicorn==0.54.0
pyjwt==2.15.1
httpx==0.28.1

# %% [markdown]
# The Dockerfile uses that file. Each line is one build step, and Docker caches each step, so the package layer is reused on the next build.

# %%
%%writefile ../apps/14/Dockerfile
# One recipe for both lab services. APP_FILE picks the code that goes into the image.
FROM python:3.12.13-slim
WORKDIR /app
COPY 14/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
ARG APP_FILE
COPY ${APP_FILE} /app/service.py
RUN useradd --create-home --uid 10001 app
USER app
EXPOSE 8000
CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8000"]

# %% [markdown]
# ### Step 3: the Compose file
#
# The file names two services. `erp` is the customer's API; only the triage service publishes a port (`8140` on the host). `triage` waits for `erp` to report healthy before it starts. Secrets come from `.env` through `${NAME}` and are not written in the file. The image tag comes from `TRIAGE_TAG`, so a rollback is a change of one value.
#
# - The `erp` healthcheck calls `/health` on lesson 13's mock API, which has that endpoint. `triage` has the same check on its own `/health`.
# - `depends_on` with `condition: service_healthy` starts `triage` only after `erp` passes its check.
# - `${TRIAGE_TAG:-1.0.0}` uses the default `1.0.0` when the variable is not set.

# %%
%%writefile ../infra/compose/customer-env-14.yml
# Customer environment for lesson 14 (lab, invented data). Started from the notebook with
# docker compose -p <project> -f <this file> --env-file ../.env up -d --build --wait
services:
  erp:
    build:
      context: ../../apps
      dockerfile: 14/Dockerfile
      args:
        APP_FILE: 13/customer_api.py
    image: bb-erp-mock:13
    environment:
      ERP_SIGNING_KEY: ${ERP_SIGNING_KEY}
      ERP_READER_CLIENT_SECRET: ${ERP_READER_CLIENT_SECRET}
      ERP_CREDIT_BOT_CLIENT_SECRET: ${ERP_CREDIT_BOT_CLIENT_SECRET}
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 5s
      timeout: 3s
      retries: 10
  triage:
    build:
      context: ../../apps
      dockerfile: 14/Dockerfile
      args:
        APP_FILE: ${TRIAGE_SRC:-14/triage_service.py}
    image: bb-triage:${TRIAGE_TAG:-1.0.0}
    environment:
      ERP_URL: http://erp:8000
      ERP_READER_CLIENT_ID: ${ERP_READER_CLIENT_ID:-bb-orders-reader}
      ERP_READER_CLIENT_SECRET: ${ERP_READER_CLIENT_SECRET}
    ports:
      - "8140:8000"
    depends_on:
      erp:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 5s
      timeout: 3s
      retries: 10

# %% [markdown]
# ### Step 4: build and start
#
# `up --build --wait` builds the images, starts both services and waits until each reports healthy. A plain `up` returns as soon as the containers exist, even if the service inside has crashed. `--wait` is what makes the command honest.

# %% tags=["needs-docker"]
DOCKER_RAN = True
up = compose("up", "-d", "--build", "--wait", extra={"TRIAGE_TAG": "1.0.0"})
print("exit code:", up.returncode)
print(tail(up.stderr, 6))
ps = compose("ps", "--format", "table {{.Service}}\t{{.Status}}")
print(tail(ps.stdout + ps.stderr, 4))

# %% [markdown]
# If Docker was skipped, this shows the start output recorded from the last real run.

# %%
if not DOCKER_RAN:
    show_recorded("up_v1")

# %% [markdown]
# Now call the running service from the laptop. The triage answers come from the customer API inside the Compose network. The lookup below uses only the public port. Run the cells in order: this cell reads the service that the start cell above brought up.

# %%
import httpx

if DOCKER_RAN:
    print(httpx.get(f"{TRIAGE}/health", timeout=10).json())
    for order_id in ["BB-1000", "BB-1001", "BB-1002", "BB-1003"]:
        r = httpx.get(f"{TRIAGE}/triage/{order_id}", timeout=10)
        print(order_id, r.status_code, r.json())
else:
    show_recorded("triage")

# %% [markdown]
# ### Step 5: a bad release
#
# A tidy-up renamed the secret setting in the code from `ERP_READER_CLIENT_SECRET` to `ERP_READER_SECRET`. The Compose file still passes the old name. The next cell builds the new code as version 1.1.0 and shows the exact change. A release is a diff. Read the diff first: it changes two lines.

# %%
import difflib

OLD_NAME, NEW_NAME = "ERP_READER_CLIENT_SECRET", "ERP_READER_SECRET"  # the release renames one setting
v1 = Path("../apps/14/triage_service.py").read_text()
v11 = (v1.replace('VERSION = "1.0.0"', 'VERSION = "1.1.0"')
         .replace(f'os.environ["{OLD_NAME}"]', f'os.environ["{NEW_NAME}"]'))
Path("../apps/14/triage_service_1_1_0.py").write_text(v11)
diff = difflib.unified_diff(v1.splitlines(True), v11.splitlines(True), "v1.0.0", "v1.1.0")
print("".join(line for line in diff if line.startswith(("+", "-"))), end="")

# %% [markdown]
# Build and start the bad release the same way. `TRIAGE_SRC` swaps which code file is built into the image. The Compose file still sets only `ERP_READER_CLIENT_SECRET`, so the 1.1.0 container will crash on start with a `KeyError`. The start is expected to fail, and the cell prints why: the last log lines end with that `KeyError`.

# %% tags=["needs-docker"]
bad = compose("up", "-d", "--build", "--wait", extra={"TRIAGE_TAG": "1.1.0", "TRIAGE_SRC": "14/triage_service_1_1_0.py"})
print("exit code:", bad.returncode)
logs = compose("logs", "triage", "--no-color", "--tail", "4")
print(tail(logs.stdout + logs.stderr, 4))

# %% [markdown]
# If Docker was skipped, this shows the start output recorded from the last real run.

# %%
if not DOCKER_RAN:
    show_recorded("bad_start")

# %% [markdown]
# The triage container has exited, so the service is down until the rollback. The customer API is still up.

# %%
if DOCKER_RAN:
    ps = compose("ps", "-a", "--format", "table {{.Service}}\t{{.Status}}")
    print(tail(ps.stdout + ps.stderr, 4))
else:
    show_recorded("bad_ps")

# %% [markdown]
# ### Step 6: roll back
#
# The 1.0.0 image is still on this machine, so the rollback needs no build. The tag `bb-triage:1.0.0` already exists locally and the default `TRIAGE_SRC` is unchanged, so Compose reuses it and recreates the container. Start the same project with the old tag. Compose replaces the broken container and waits for the health check.

# %% tags=["needs-docker"]
back = compose("up", "-d", "--wait", extra={"TRIAGE_TAG": "1.0.0"})
print("exit code:", back.returncode)
print(tail(back.stderr + back.stdout, 6))

# %% [markdown]
# If Docker was skipped, this shows the start output recorded from the last real run.

# %%
if not DOCKER_RAN:
    show_recorded("rollback_up")

# %% [markdown]
# Check the rolled-back service: the health answer should show version 1.0.0 again.

# %%
if DOCKER_RAN:
    print(httpx.get(f"{TRIAGE}/health", timeout=10).json())
    print(httpx.get(f"{TRIAGE}/triage/BB-1000", timeout=10).json())
else:
    show_recorded("rollback")

# %% [markdown]
# ## At work
#
# - **Customers run images from their own registry.** The image is built once, tagged per release and pinned, so the same bytes run in test and production. A tag such as `latest` makes a rollback impossible. → lesson 24 (zero-downtime rollout).
# - **Secrets and settings arrive from outside the image.** Customer security teams want the client secret in their own secret store, injected at start-up. → lesson 13 (secrets), lesson 15 (the restricted network the service runs in).
# - **Releases go through a change board.** The board asks for the diff and the rollback plan before it approves. Keep the previous tag on the host and write the rollback command down. → lesson 17 (runbooks and incidents).
# - **Compose runs one host well; larger estates use an orchestrator.** This course uses Compose only; Kubernetes is a separate course.

# %% [markdown]
# ## Common mistakes
#
# **Mistake 1: the setting name in code and in the Compose file differ.** The release reads a name that the environment does not have. The fix is one name in both places, and a check at startup (`is_set`, or a readable error) before the first request.

# %% tags=["raises-exception"]
name = "ERP_READER_SECRET"  # the name the bad release reads; .env does not set it
ERP_SECRET = os.environ[name]

# %% [markdown]
# The fix: read the name the Compose file passes, and fail with a message that names it.

# %%
name = "ERP_READER_CLIENT_SECRET"  # the name the Compose file passes to the container
print(f"{name} is set" if is_set(name) else f"{name} is not set: add it to ../.env or fix the Compose file")

# %% [markdown]
# **Mistake 2: `docker compose up` without `--wait`.** It reports success while the service is still starting or has already crashed. Always wait for health, then check the status.
#
# **Mistake 3: printing the Compose configuration.** `docker compose config` shows every resolved value, including secrets from `.env`. Do not run it in a shared terminal or paste it into a ticket.
#
# **Mistake 4: tagging every build `latest`.** Then "the previous version" is no longer a thing you can point at. Give each release its own tag, as this lesson does (`bb-triage:1.0.0`, `bb-triage:1.1.0`).

# %% [markdown]
# ## Try it
#
# Write `all_from_version` to check a release after a rollback: it returns True only when every triage answer in a list came from the given version. The sample answers are invented.

# %%
# your code here
def all_from_version(results: list[dict], version: str) -> bool:
    """True when every triage answer came from this version."""
    return False  # your code here


sample = [{"order_id": "BB-1000", "label": "missing items", "version": "1.0.0"},
          {"order_id": "BB-1001", "label": "complete", "version": "1.0.0"}]
print(all_from_version(sample, "1.0.0"), all_from_version(sample, "1.1.0"))

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def all_from_version(results: list[dict], version: str) -> bool:
    """True when every triage answer came from this version."""
    return all(r["version"] == version for r in results)


print(all_from_version(sample, "1.0.0"), all_from_version(sample, "1.1.0"))

# %% [markdown]
# ## Tear down
#
# Stop and remove this lesson's containers and network. The images stay, so the rollback still works next time. Use `down -v` only when you also want the volumes removed.

# %%
if not DOCKER_RAN:
    print("nothing to remove: Docker was not run")

# %% [markdown]
# With Docker, the next cell stops the stack and removes its containers and network.

# %% tags=["needs-docker"]
down = compose("down", "--remove-orphans")
print("exit code:", down.returncode)
print(tail(down.stderr + down.stdout, 4) or "stack removed; images kept")

# %% [markdown]
# ## Recap
#
# - **Container image**: a sealed build of the code, packages and Python version, built from a **Dockerfile** with a pinned base and one tag per release.
# - **Docker Compose**: one YAML file starts several services on a private network; `depends_on` with `service_healthy` orders the start, and `--wait` reports the real state.
# - **Settings** come from the environment (`${NAME}` from `.env`), never from the image or the file.
# - **Rollback** is a previous tag that still exists on the host: change `TRIAGE_TAG`, run `up --wait`, check `/health`.
# - Go deeper: the restricted network and egress proxy are lesson 15; the zero-downtime rollout is lesson 24. Kubernetes is a separate course.
#
# **Interview:** "How do you deploy a service into a customer environment that you cannot change?" Strong answer: a pinned image from the customer's registry, settings from their secret store, a health-checked start, and a release that keeps the previous tag so the change board can roll back in one command.
