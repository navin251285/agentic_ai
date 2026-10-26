# %% [markdown]
# # 15 · Deploying into a restricted network: private networks and an egress proxy
#
# Level L3 · Part 2 · core · ~30 min · builds on 14
#
# Needs Docker with Compose v2 (`docker compose version`), about 2 GB of free RAM, and an internet pull the first time of two images: `python:3.12.13-slim` and `ubuntu/squid:7.2-26.04_edge` (the egress proxy). No port on your laptop is used: the customer network has no door to it. Cells tagged `needs-docker` start containers. When they are skipped, the cells after them print the recorded output from a real run of this lesson, labelled as such.
#
# About the proxy tag: `7.2-26.04_edge` is an **edge** (pre-release) tag. Checked on 2026-10-26 against the Docker Hub tag list, `ubuntu/squid` publishes no stable (unsuffixed) tag for Squid 7.2 on Ubuntu 26.04, and `latest` is a moving alias, so neither can be pinned. The lab keeps the exact edge tag so that every run uses the same image. For a production rollback target, pin a stable tag as soon as Canonical publishes one, and re-run this lesson's allow and deny tests against it before you switch.

# %% [markdown]
# ## Goal
#
# By the end you can run the triage service on a network with no route to the internet, let it reach the model API only through an egress proxy that allows one host, and show from the proxy log which calls were allowed and which were denied.

# %% [markdown]
# ## Why it matters
#
# Lesson 14 ran the service on a network that could reach anything. Many customers will not allow that. Their security team wants no outbound calls except to the few hosts the service needs, and a record of each call.
#
# The triage service calls the customer API (ERP) inside the network and the model API outside it: one outside host.
#
# - **Without a proxy:** each outside host is a firewall exception the customer's team keeps alive. A call to a host
#   nobody listed fails with a timeout, which looks like a bug in the app.
# - **With an egress proxy:** the customer network has no route out. The proxy is the only way to an outside host.
#   It says yes or no per host name and logs each decision.
# - **When you don't need it:** a laptop, or a customer whose policy allows outbound calls. Then the proxy only adds a hop.

# %% [markdown]
# ## The idea
#
# Docker Compose can mark a network **internal**: its containers reach each other, but nothing outside. An **egress proxy** is the one container on two networks, the customer network and the outside one. The triage service sets `HTTP_PROXY`, so its outside calls go to the proxy. The proxy checks the host name against an **allowlist** and forwards only the allowed ones. Names inside the network, such as `erp`, skip the proxy: `NO_PROXY` lists them. `HTTP_PROXY` and `NO_PROXY` are standard environment variables, and `httpx` reads them by default.
#
# Analogy: one reception desk. Everyone leaves through it, and the guard checks each name against a list and writes it in the book.

# %% [markdown]
# ## Picture
#
# The triage service is on the customer network only. Its one way out is the proxy.

# %% [markdown]
# ```mermaid
# flowchart LR
#     subgraph cust[Customer network: internal, no route out]
#         T[triage v1.2.0] -->|erp: direct, NO_PROXY| E[erp: customer API, mock]
#         T -->|HTTP_PROXY| P[egress proxy: allowlist]
#     end
#     subgraph out[Outside: the internet in real life]
#         P -->|allowed: api.model-vendor.example| M[model API stand-in]
#     end
#     T -.->|direct call: no route| M
# ```

# %% [markdown]
# ## Before you start
#
# Run the setup cell first. It loads the settings from earlier lessons (names and yes/no only; no values are printed), and creates the folders the files go to. The customer API that `erp` runs is the file `apps/13/customer_api.py` from lesson 13, so that file must exist; the setup cell checks it.

# %%
import json, os, shutil, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, "..")
from tut_env import is_set, load
load()
DOCKER_RAN = False  # set to True by the cells tagged needs-docker
STACK = "tut-forward-deployed-engineering-15h-15"  # one Compose project for this lesson only
COMPOSE = ["docker", "compose", "-p", STACK, "-f", "../infra/compose/restricted-net-15.yml", "--env-file", "../.env"]
REC = json.loads(Path("../data/recorded/15.json").read_text())
for d in ["../apps/15", "../infra/compose/egress"]:
    Path(d).mkdir(parents=True, exist_ok=True)


def compose(*args, extra=None):
    """Run docker compose for this lesson's project. extra sets variables for this call only."""
    return subprocess.run([*COMPOSE, *args], capture_output=True, text=True, timeout=900,
                          env={**os.environ, **(extra or {})})


def in_triage(code, env_extra=None):
    """Run a short Python snippet inside the triage container, which sits on the customer network."""
    flags = [x for k, v in (env_extra or {}).items() for x in ("-e", f"{k}={v}")]
    return compose("exec", "-T", *flags, "triage", "python", "-c", code)


def tail(text, n=8):
    return "\n".join(text.strip().splitlines()[-n:])


def show_recorded(key):
    print("recorded output from a real run of this lesson (Docker was not run in this build):")
    print(REC[key])


print("docker on PATH:", bool(shutil.which("docker")), "| lesson 13 settings set:", all(is_set(n) for n in ["ERP_SIGNING_KEY", "ERP_READER_CLIENT_SECRET", "ERP_CREDIT_BOT_CLIENT_SECRET"]), "| apps/13/customer_api.py exists:", Path("../apps/13/customer_api.py").exists())

# %% [markdown]
# %% [markdown]
# ## Step by step

# %% [markdown]
# ### Step 1: the service (v1.2.0)
#
# Version 1.2.0 keeps the triage answer from lesson 14 and adds `/explain`: the label plus a draft reply from the model API. Two outbound calls now exist. The customer API is inside the network, so it is called directly. The model API is outside, so it is called through the proxy. The `httpx` client reads `HTTP_PROXY` and `NO_PROXY` from the environment, so the code does not change per network. Every failed call becomes a 502 that names the host.

# %%
%%writefile ../apps/15/triage_service.py
"""Basket Bazaar triage service, version 1.2.0 (lab, invented data). /explain calls the model API
through the egress proxy (HTTP_PROXY); the customer API inside the network is called directly (NO_PROXY)."""
import os

import httpx
from fastapi import FastAPI, HTTPException

VERSION = "1.2.0"
ERP_URL = os.environ["ERP_URL"]                         # inside the network: http://erp:8000
CLIENT_ID = os.environ["ERP_READER_CLIENT_ID"]
CLIENT_SECRET = os.environ["ERP_READER_CLIENT_SECRET"]  # injected at start-up, never in the image
MODEL_API_URL = os.environ["MODEL_API_URL"]             # outside the network: reached through the proxy
app = FastAPI(title="Basket Bazaar triage", version=VERSION)


def call(method: str, url: str, **kwargs) -> httpx.Response:
    """One outbound call. A failure becomes a 502 that names the host, not a bare 500."""
    host = url.split("/")[2]
    try:
        r = httpx.request(method, url, timeout=5, **kwargs)
    except httpx.HTTPError as e:
        raise HTTPException(502, detail=f"{host} unreachable: {type(e).__name__}") from e
    if r.status_code >= 400:
        raise HTTPException(502, detail=f"{host} returned {r.status_code}")
    return r


def erp_token() -> str:
    """Client credentials grant (lesson 13): the account's secret in exchange for a short-lived token."""
    r = call("POST", f"{ERP_URL}/oauth/token", auth=(CLIENT_ID, CLIENT_SECRET),
             data={"grant_type": "client_credentials", "scope": "orders:read"})
    return r.json()["access_token"]


def read_order(order_id: str) -> dict:
    r = call("GET", f"{ERP_URL}/orders", headers={"Authorization": f"Bearer {erp_token()}"})
    order = next((o for o in r.json()["data"] if o["id"] == order_id), None)
    if order is None:
        raise HTTPException(404, detail="order not found")
    return order


def label_for(order: dict) -> str:
    return "missing items" if order["lines_short"] else "complete"


@app.get("/health")
def health():
    return {"ok": True, "version": VERSION}


@app.get("/triage/{order_id}")
def triage(order_id: str):
    return {"order_id": order_id, "label": label_for(read_order(order_id)), "version": VERSION}


@app.get("/explain/{order_id}")
def explain(order_id: str):
    label = label_for(read_order(order_id))
    r = call("POST", f"{MODEL_API_URL}/v1/draft", json={"order_id": order_id, "label": label})
    return {"order_id": order_id, "label": label, "draft": r.json()["draft"], "version": VERSION}

# %% [markdown]
# ### Step 2: the model API stand-in
#
# The model API is outside the customer network. In this lab it is a stand-in: a small server with fixed, invented drafts. It is not a model and runs no inference. The point of the lesson is the network path, so a stand-in is enough. The server is reachable under one host name, `api.model-vendor.example`, on the outside network only.

# %%
%%writefile ../apps/15/model_vendor_mock.py
"""Lab stand-in for a model API (lesson 15). NOT a model: fixed, invented text, no inference."""
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Lab stand-in for a model API (not a model)")
DRAFTS = {
    "missing items": "Hi, part of your order was short. We will credit the missing items to your account.",
    "complete": "Hi, your order is complete. Thank you for shopping with Basket Bazaar.",
}


class DraftRequest(BaseModel):
    order_id: str
    label: str


@app.get("/health")
def health():
    return {"ok": True, "stand_in": True}


@app.post("/v1/draft")
def draft(req: DraftRequest):
    return {"draft": DRAFTS.get(req.label, "We are looking into your order."), "stand_in": True}

# %% [markdown]
# ### Step 3: the image recipe
#
# One Dockerfile serves the three Python services, as in lesson 14. The pinned base image, the pinned packages and the non-root user are the same. `APP_FILE` picks the code.

# %%
%%writefile ../apps/15/requirements.txt
fastapi==0.162.0
uvicorn==0.54.0
pyjwt==2.15.1
httpx==0.28.1

# %% [markdown]
# The Dockerfile uses that file. Each line is one build step, and Docker caches each step.

# %%
%%writefile ../apps/15/Dockerfile
FROM python:3.12.13-slim
WORKDIR /app
COPY 15/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
ARG APP_FILE
COPY ${APP_FILE} /app/service.py
RUN useradd --create-home --uid 10001 app
USER app
EXPOSE 8000
CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8000"]

# %% [markdown]
# ### Step 4: the egress allowlist
#
# Squid is an open-source caching and forwarding proxy, widely used as an egress point. The configuration below is the whole policy: one allowed host, the ports that may be used, and `deny all` for everything else. Read it top to bottom; Squid applies the first rule that matches. `cache deny all` turns off caching, so the proxy only forwards and logs.

# %%
%%writefile ../infra/compose/egress/squid.conf
# Egress proxy for the restricted customer network (lesson 15, lab). Read top to bottom: the first match wins.
http_port 3128
acl model_api dstdomain api.model-vendor.example   # the only outside host the customer allows
acl Safe_ports port 80 8000 443                    # lab model API on 8000; a real vendor uses 443
acl SSL_ports port 443
acl CONNECT method CONNECT
http_access deny !Safe_ports
http_access deny CONNECT !SSL_ports
http_access allow model_api
http_access deny all                               # everything else is refused
cache deny all
pid_filename none
access_log stdio:/var/log/squid/access.log         # every allow and deny, one line each
cache_log /dev/stderr

# %% [markdown]
# ### Step 5: the Compose file
#
# Two networks. `customer` is marked `internal: true`: its containers have no route out. `outside` is an ordinary network. The egress proxy is on both, so it is the only container that can reach the outside. The triage service is on `customer` only, and it publishes no port: the customer network has no door to your laptop, so the tests run from inside it, the way the customer's operations team would run them. The proxy address comes from `EGRESS_PROXY_URL` is optional; leave it unset and the proxy in this file is used.

# %%
%%writefile ../infra/compose/restricted-net-15.yml
# Restricted customer network for lesson 15 (lab, invented data). Started by the notebook with
# docker compose -p <project> -f <this file> --env-file ../.env up -d --build --wait
#
# Two networks, one way out:
#   customer  internal: true, so it has no route out. erp (customer API) and triage live here.
#   outside   an ordinary network. The model API stand-in (api.model-vendor.example) lives here.
#   egress    the one container on both networks: the squid allowlist. triage sends its outside
#             calls to it (HTTP_PROXY); erp is reached directly (NO_PROXY).
# No service publishes a port to your laptop: the tests run from inside the customer network.
services:
  erp:
    build:
      context: ../../apps
      dockerfile: 15/Dockerfile
      args:
        APP_FILE: 13/customer_api.py
    image: bb-erp-mock:15
    environment:
      ERP_SIGNING_KEY: ${ERP_SIGNING_KEY}
      ERP_READER_CLIENT_SECRET: ${ERP_READER_CLIENT_SECRET}
      ERP_CREDIT_BOT_CLIENT_SECRET: ${ERP_CREDIT_BOT_CLIENT_SECRET}
    networks: [customer]
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 5s
      timeout: 3s
      retries: 10
  model-vendor:
    build:
      context: ../../apps
      dockerfile: 15/Dockerfile
      args:
        APP_FILE: 15/model_vendor_mock.py
    image: bb-model-stand-in:15
    networks:
      outside:
        aliases: [api.model-vendor.example]
  egress:
    image: ubuntu/squid:7.2-26.04_edge
    volumes:
      - ./egress/squid.conf:/etc/squid/squid.conf:ro
    networks: [customer, outside]
  triage:
    build:
      context: ../../apps
      dockerfile: 15/Dockerfile
      args:
        APP_FILE: ${TRIAGE_SRC:-15/triage_service.py}
    image: bb-triage:${TRIAGE_TAG:-1.2.0}
    environment:
      ERP_URL: http://erp:8000
      ERP_READER_CLIENT_ID: ${ERP_READER_CLIENT_ID:-bb-orders-reader}
      ERP_READER_CLIENT_SECRET: ${ERP_READER_CLIENT_SECRET}
      MODEL_API_URL: ${MODEL_API_URL:-http://api.model-vendor.example:8000}
      HTTP_PROXY: ${EGRESS_PROXY_URL:-http://egress:3128}
      HTTPS_PROXY: ${EGRESS_PROXY_URL:-http://egress:3128}
      NO_PROXY: erp,localhost,127.0.0.1
    networks: [customer]
    depends_on:
      erp:
        condition: service_healthy
      egress:
        condition: service_started
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 5s
      timeout: 3s
      retries: 10
networks:
  customer:
    internal: true
  outside: {}

# %% [markdown]
# ### Step 6: build and start
#
# The same `up --build --wait` as lesson 14. The proxy has no health check of its own (its image has no shell or HTTP client to run one), so the cell after this one waits until the proxy answers a real request.

# %% tags=["needs-docker"]
DOCKER_RAN = True
up = compose("up", "-d", "--build", "--wait", extra={"TRIAGE_TAG": "1.2.0"})
print("exit code:", up.returncode)
print(tail(up.stderr, 6))
ps = compose("ps", "--format", "table {{.Service}}\t{{.Status}}")
print(tail(ps.stdout + ps.stderr, 10))

# %% [markdown]
# Wait until the proxy answers. The loop stops at the first 200, or after 90 seconds. This call uses `HTTP_PROXY` from the container, so a 200 proves the proxy path works.

# %% tags=["needs-docker"]
PROXY_CHECK = 'import httpx; print(httpx.get("http://api.model-vendor.example:8000/health", timeout=5).status_code)'
deadline = time.time() + 90
while time.time() < deadline:
    check = in_triage(PROXY_CHECK)
    if check.stdout.strip() == "200":
        break
    time.sleep(2)
print("proxy reaches the model API stand-in:", check.stdout.strip() == "200")
if check.stdout.strip() != "200":
    print(tail(check.stderr, 3))

# %% [markdown]
# Now check the network itself. Docker reports whether each network is internal.

# %% tags=["needs-docker"]
for net in ["customer", "outside"]:
    out = subprocess.run(["docker", "network", "inspect", f"{STACK}_{net}", "--format", "internal={{.Internal}}"], capture_output=True, text=True)
    print(net, out.stdout.strip() or out.stderr.strip())

# %% [markdown]
# ### Step 7: test from inside the customer network
#
# The first test uses the direct path. `trust_env=False` makes `httpx` ignore `HTTP_PROXY`, which is what a call would do if somebody forgot the proxy. Both calls should fail. Neither host answers from the customer network: the first name cannot be reached from there, and the second address has no route at all. Both show up as `ConnectError`. This is the only call in the lesson that skips the proxy; the others use it by default.

# %%
DIRECT = """
import httpx
for url in ["http://api.model-vendor.example:8000/health", "http://1.1.1.1/"]:
    try: print(url, httpx.get(url, timeout=3, trust_env=False).status_code)
    except httpx.HTTPError as e: print(url, "no answer:", type(e).__name__)
"""

# %% [markdown]
# Run the direct test from inside the triage container.

# %% tags=["needs-docker"]
DOCKER_RAN = True
direct = in_triage(DIRECT)
print(tail(direct.stdout + direct.stderr, 4))

# %% [markdown]
# Docker skipped? Recorded output:

# %%
if not DOCKER_RAN: show_recorded("direct")

# %% [markdown]
# The second test goes through the service's own API. The triage answer comes from the customer API inside the network. The explain answer comes from the model API stand-in, reached through the proxy. The call to `localhost` skips the proxy because `NO_PROXY` lists it.

# %%
VIA_PROXY = """
import httpx
base = "http://localhost:8000"
print("triage", httpx.get(f"{base}/triage/BB-1000", timeout=10).json())
r = httpx.get(f"{base}/explain/BB-1000", timeout=10)
print("explain", r.status_code, r.json())
"""

# %% [markdown]
# Run it from inside the triage container, which sits on the customer network.

# %% tags=["needs-docker"]
via = in_triage(VIA_PROXY)
print(tail(via.stdout + via.stderr, 4))

# %% [markdown]
# Docker skipped? Recorded output:

# %%
if not DOCKER_RAN: show_recorded("via_proxy")

# %% [markdown]
# The third test asks the proxy for a host that is not on the allowlist. The proxy refuses it with a 403 page that names Squid.

# %%
DENIED = """
import httpx
r = httpx.get("http://example.org/", timeout=10)  # not on the allowlist
print("example.org", r.status_code, "refused by Squid" if "Squid" in r.text else "")
"""

# %% [markdown]
# Run it from inside the triage container, which sits on the customer network.

# %% tags=["needs-docker"]
denied = in_triage(DENIED)
print(tail(denied.stdout + denied.stderr, 4))

# %% [markdown]
# Docker skipped? Recorded output:

# %%
if not DOCKER_RAN: show_recorded("denied")

# %% [markdown]
# The proxy log is the record the security team asks for. Each line the cell prints is the status the proxy returned, the method and the URL. This run has three lines, one for each call that used the proxy; the `erp` calls do not appear, because they skip the proxy.

# %% tags=["needs-docker"]
log = compose("exec", "-T", "egress", "cat", "/var/log/squid/access.log")
for line in log.stdout.splitlines()[-4:]:
    parts = line.split()  # fields: time, elapsed, client, status, size, method, URL
    print(parts[3], parts[5], parts[6]) if len(parts) > 6 else print(line)

# %% [markdown]
# Docker skipped? Recorded output:

# %%
if not DOCKER_RAN: show_recorded("proxy_log")

# %% [markdown]
# ## At work
#
# - **Customers ask for a closed network: no outbound internet, and each outside host allowed by name and logged.** A proxy with an allowlist is the usual answer. A refused call is an incident with a runbook entry. → lesson 17 (runbooks and incidents).
# - **Cloud private links avoid the public internet for some services.** AWS PrivateLink connects a VPC (a private network inside one cloud account) to a service with no internet gateway or public IP ([AWS docs](https://docs.aws.amazon.com/vpc/latest/privatelink/what-is-privatelink.html)). It does not reach across clouds or to on-premises sites. → lesson 28 (a model provider goes down).
# - **Air-gapped sites get images by hand.** Common practice: `docker save` on a connected machine, carry the file across, then `docker load` inside the network, so nothing is pulled at build time. Lesson 14 covers Compose delivery; lesson 24 covers rolling out a new image version.

# %% [markdown]
# ## Common mistakes
#
# **Mistake 1: a name missing from `NO_PROXY`.** The service sends its customer API call to the proxy. The 403 comes from Squid, because `erp` is not on the allowlist. The service reports a 502 that names `erp`, which is easy to misread as the customer API being down. The next cell runs the read with `NO_PROXY` missing the name, then with it set.

# %% tags=["needs-docker"]
CHECK_READ = """
import service
from fastapi import HTTPException
try: service.read_order("BB-1000"); print("read ok")
except HTTPException as e: print(e.status_code, e.detail)
"""
bad = in_triage(CHECK_READ, env_extra={"NO_PROXY": "localhost,127.0.0.1"})
print("NO_PROXY without erp:", tail(bad.stdout + bad.stderr, 2))
good = in_triage(CHECK_READ)
print("NO_PROXY with erp:   ", tail(good.stdout + good.stderr, 2))

# %% [markdown]
# Docker skipped? Recorded output:

# %%
if not DOCKER_RAN: show_recorded("no_proxy_mistake")

# %% [markdown]
# **Mistake 2: the wrong name for the proxy setting.** The client reads `HTTP_PROXY`. If a Compose file sets a name it does not read, such as `EGRESS_PROXY`, the client sees no proxy and goes out direct, and the model host does not resolve on the customer network. The next cell runs the same explain call with the proxy setting empty, which is what the client sees under the wrong name, and then with the right value.

# %% tags=["needs-docker"]
CHECK_EXPLAIN = """
import service
from fastapi import HTTPException
try: print("explain ok", service.explain("BB-1000")["label"])
except HTTPException as e: print(e.status_code, e.detail)
"""
no_proxy = in_triage(CHECK_EXPLAIN, env_extra={"HTTP_PROXY": "", "HTTPS_PROXY": ""})
print("no proxy seen:", tail(no_proxy.stdout + no_proxy.stderr, 2))
with_proxy = in_triage(CHECK_EXPLAIN)
print("proxy set:    ", tail(with_proxy.stdout + with_proxy.stderr, 2))

# %% [markdown]
# Docker skipped? Recorded output:

# %%
if not DOCKER_RAN: show_recorded("wrong_proxy_name")

# %% [markdown]
# The fix is the name the client reads: `HTTP_PROXY`, which the Compose file sets for triage.

# %% [markdown]
# **Mistake 3: a published port on the customer network.** It gives your laptop a door into the network the customer wants closed. Test from inside instead, as this lesson does. **Mistake 4: `allow all` in the proxy policy.** It turns the allowlist into an open door, and the log then records every call as allowed. Keep `deny all` as the last rule.

# %% [markdown]
# ## Try it
#
# Write `classify(status)`. It names what one call through the proxy means: `None` means no answer at all (no route, or the name does not resolve), 403 means the proxy refused, a 2xx means the call reached the host, and any other code means the host answered with an error. The samples are invented.

# %%
# your code here
def classify(status: int | None) -> str:
    """Name what a call through the egress proxy means."""
    return "your code here"


for s in [200, 403, None, 502]:
    print(s, "->", classify(s))

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def classify(status: int | None) -> str:
    """Name what a call through the egress proxy means."""
    if status is None:
        return "no route: the call never left the network"
    if status == 403:
        return "refused by the egress proxy: host not on the allowlist"
    if 200 <= status < 300:
        return "reached the host"
    return "reached the host, which returned an error"


for s in [200, 403, None, 502]:
    print(s, "->", classify(s))

# %% [markdown]
# ## Tear down
#
# Stop and remove this lesson's containers and networks. The images stay, so the next run starts faster. Use `down -v` only when you also want the volumes removed.

# %% tags=["needs-docker"]
DOCKER_RAN = True
down = compose("down", "--remove-orphans")
print("exit code:", down.returncode)
print(tail(down.stderr + down.stdout, 4) or "stack removed; images kept")

# %% [markdown]
# ## Recap
#
# - **Internal network**: a Compose network with no route out. Its containers reach each other and nothing else.
# - **Egress proxy**: the one container on both networks. It allows or refuses each outside host by name and logs every call.
# - **`HTTP_PROXY` and `NO_PROXY`**: outside calls go to the proxy; names inside the network stay direct.
# - **A refused call is a finding**: read the proxy log and the host in the error before you blame the app.
#
# **Interview:** "How does a service in a locked-down network reach a model API?" Strong answer: no route out, one egress proxy with a hostname allowlist and a log, `NO_PROXY` for internal names, and a test that a direct call fails.
