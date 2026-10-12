# %% [markdown]
# # 39 · Checkpoint: organisation-wide authorization for Trackr
# Level L6 · Part 7 · professional · ~120 min · builds on 38, 38a

# %% [markdown]
# ## Goal
# By the end, one organisation authorization server (Keycloak in Docker) serves Trackr for three users in two teams and two agents. You will see, in printed output, that: each user's token names that user and team; each token works at one resource only; an agent acts with its own identity; a user's request passes through two agents to Trackr with a chain that cannot widen; a step-up is refused until the user signs in again; a signed agent card is checked before use; and a who-can-call-what matrix, with an access-review table, matches the rules, with tests. The model makes 2 calls.

# %% [markdown]
# ## Why it matters
# Lessons 34 to 38a each solved one piece: sign-in, agent identities, signed cards, tenants, delegation. Together, the pieces must agree. Without a checked whole, the failures look like this:
#
# | Question | Each service its own login and list | One server, every rule checked |
# | --- | --- | --- |
# | A user leaves the company | removed in three places, one is forgotten | disabled once; the next token request fails |
# | Who may close an issue? | the agent's scope says yes, the team says no, nobody checks both | scope, team and role are all checked on every call |
# | Which team does a request belong to? | taken from the request, so a caller can name any team | taken from the verified token |
# | Can a token meant for one service open another? | yes, unless each service checks the audience | no: each service checks its own audience |
#
# You do not need this for one tool and one person. It pays when several teams and agents share tools.

# %% [markdown]
# ## The idea
# One authorization server signs every token. Trackr and the triage agent accept a token only when the audience is theirs, the signature is from the server's published keys, and the scope and the user's team and role allow the call. Agents have their own identities (client credentials). A hop that acts for a user exchanges the token it got for one aimed at the next service, with a scope that can only shrink.
#
# Analogy: a company's badge office. One office issues every badge. Each door reads the badge's floor and clearance, not the person's name. A visitor's badge for the lobby does not open the lab, and a lab technician's badge does not open the vault, even when the technician is standing at the vault door.

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart LR
#   KC[Keycloak: one organisation server] -->|alice, teams web, role lead| O[ops-agent]
#   O -->|exchange: aud triage-agent| T[triage-agent A2A]
#   T -->|exchange: aud trackr-mcp, issues:read| M[Trackr MCP]
#   M -->|checks aud, scope, team, role| D{allow or refuse}
#   KC -->|client credentials| T
# ```

# %% [markdown]
# ## Requirements
# | # | Requirement | Checked in step |
# | --- | --- | --- |
# | R1 | One authorization server answers for the organisation | 2 |
# | R2 | A user's token names the user, the team and the role | 5 |
# | R3 | Each token works at one audience only | 6 |
# | R4 | Agents have their own identity and no user team | 7 |
# | R5 | A delegated chain narrows; a skipped hop and a wider scope are refused | 8 to 10 |
# | R6 | A step-up is refused until the user signs in again with the wider scope | 11 |
# | R7 | An agent card is used only if its signature checks against a pinned key | 4 |
# | R8 | Tenant and role rules hold for every row of the who-can-call-what matrix | 12 |
# | R9 | An access-review table prints the result, and the tests pass | 13 |

# %% [markdown]
# ## Build it
#
# ### 1. Set up
# The settings come from `.env`. The lab values for the passwords and client secrets are for the local containers only. The issues file starts from the same six issues every run. The web team has three open issues (4, 9, 15) and the api team two (21, 24).

# %%
import sys, os, json, time, subprocess, atexit, asyncio
from pathlib import Path
import httpx, httpx2, jwt, uvicorn
sys.path.insert(0, "..")
import tut_env, llm_replay
from tut_env import env
tut_env.load()
DATA = Path("../data/39").resolve(); DATA.mkdir(parents=True, exist_ok=True)
APPS = Path("../apps/39").resolve()
REALM_FILE = Path("../infra/39/realm-ops-org.json").resolve()
ISSUES, TRACKR_AUDIT, AS_AUDIT = DATA / "issues.json", DATA / "trackr_audit.log", DATA / "org_as_audit.log"
for path in [TRACKR_AUDIT, AS_AUDIT]:
    path.unlink(missing_ok=True)                      # a fresh run starts with empty logs
_ = ISSUES.write_text(json.dumps([
    {"id": 4, "team": "web", "state": "open", "title": "Login page flickers on Safari"},
    {"id": 9, "team": "web", "state": "open", "title": "Export CSV drops the owner column"},
    {"id": 12, "team": "web", "state": "closed", "title": "Typo in the footer"},
    {"id": 15, "team": "web", "state": "open", "title": "Dark mode colours are unreadable"},
    {"id": 21, "team": "api", "state": "open", "title": "Rate limit header missing"},
    {"id": 24, "team": "api", "state": "open", "title": "Upload fails above 10 MB"}]))
# %% [markdown]
# The helpers: the organisation server's address, the token endpoints, and a poll that waits until a URL answers.

# %%
ISSUER = "http://127.0.0.1:8390/realms/ops-org"
TOKEN_URL, TRACKR, TRIAGE = f"{ISSUER}/protocol/openid-connect/token", "http://127.0.0.1:8391/mcp", "http://127.0.0.1:8392/"
TOKEN_EXCHANGE, TOKEN_TYPE = "urn:ietf:params:oauth:grant-type:token-exchange", "urn:ietf:params:oauth:token-type:access_token"
DEMO_PASSWORD, OPS_SECRET, TRIAGE_SECRET = env("ORG_DEMO_PASSWORD"), env("ORG_OPS_AGENT_SECRET"), env("ORG_TRIAGE_AGENT_SECRET")
procs, tokens, KC_UP = [], {}, False
llm, first, result = None, None, None                 # set by the model cell; stay None if it is skipped
atexit.register(lambda: [p.terminate() for p in procs])

def wait_for(url: str, timeout: float = 180.0) -> None:
    """Poll until the URL answers 200. Polls; it does not sleep for a fixed time."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            if httpx.get(url, timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        if time.monotonic() > deadline:
            raise RuntimeError(f"no answer from {url}")
        time.sleep(1)

print("ports 8390 (organisation server), 8391 (Trackr), 8392 (triage-agent) | lab secrets set:",
      all([DEMO_PASSWORD, OPS_SECRET, TRIAGE_SECRET]))

# %% [markdown]
# ### 2. One organisation authorization server (`needs-docker`)
# The cell starts Keycloak 26.8 from `infra/39/` with the realm file. The realm file holds no passwords. The admin API then sets the three users' passwords and the two agents' client secrets from `.env`. The realm turns on standard token exchange for the two agents only. Keycloak starts in about a minute.

# %% tags=["needs-docker"]
COMPOSE = ["docker", "compose", "-p", "tut-agentic-ai-4-protocols-39", "-f",
           str(Path("../infra/39/docker-compose.yml").resolve()), "--env-file", str(Path("../.env").resolve())]
subprocess.run([*COMPOSE, "up", "-d"], check=True, capture_output=True, env=os.environ)
wait_for(f"{ISSUER}/.well-known/openid-configuration")
admin = httpx.post("http://127.0.0.1:8390/realms/master/protocol/openid-connect/token", data={
    "grant_type": "password", "client_id": "admin-cli",
    "username": env("KEYCLOAK_ADMIN"), "password": env("KEYCLOAK_ADMIN_PASSWORD")}).json()["access_token"]
ADMIN, ADMIN_H = "http://127.0.0.1:8390/admin/realms/ops-org", {"Authorization": f"Bearer {admin}"}
for user in ["alice", "bob", "carol"]:
    uid = httpx.get(f"{ADMIN}/users?username={user}", headers=ADMIN_H).json()[0]["id"]
    httpx.put(f"{ADMIN}/users/{uid}/reset-password", headers=ADMIN_H,
              json={"type": "password", "value": DEMO_PASSWORD, "temporary": False}).raise_for_status()
clients = {c["clientId"]: c for c in httpx.get(f"{ADMIN}/clients", headers=ADMIN_H).json()}
for cid, secret in [("ops-agent", OPS_SECRET), ("triage-agent", TRIAGE_SECRET)]:
    client = clients[cid]
    client["secret"] = secret
    httpx.put(f"{ADMIN}/clients/{client['id']}", headers=ADMIN_H, json=client).raise_for_status()
KC_UP = True
print("Keycloak 26.8 is up | realm: ops-org | passwords and agent secrets set from .env")

# %% [markdown]
# Without Docker, this cell starts the stand-in instead. It is not Keycloak: it serves the same paths and reads the same realm file, and it reproduces only the rules this lesson uses.

# %%
if not KC_UP:
    procs.append(subprocess.Popen([sys.executable, str(APPS / "org_standin.py"), str(REALM_FILE), str(AS_AUDIT)],
                                  stdout=subprocess.DEVNULL, stderr=open(DATA / "org_standin.err", "w"), env=os.environ))
    wait_for(f"{ISSUER}/.well-known/openid-configuration")
    print("stand-in started (no Docker): same paths and realm file, not Keycloak")
ISSUER_OK = httpx.get(f"{ISSUER}/.well-known/openid-configuration").json()["issuer"] == ISSUER
print("organisation server answers at:", ISSUER, "| matches:", ISSUER_OK)

# %% [markdown]
# ### 3. Read the realm file: who is in which team, and what each scope means
# The realm file is the reviewed source. Each client lists the scopes it may hold. Each audience scope adds one audience to the token. The table is printed from the file, so what you read is what the server runs.

# %%
realm = json.loads(REALM_FILE.read_text())
print("users:", [(u["username"], [g.strip("/") for g in u["groups"]], u["realmRoles"]) for u in realm["users"]])
for c in realm["clients"]:
    print(f"client {c['clientId']:<12} exchange: {c.get('attributes', {}).get('standard.token.exchange.enabled', 'off'):<5}"
          f" may hold: {sorted(set(c.get('defaultClientScopes', []) + c.get('optionalClientScopes', [])))}")
for s in realm["clientScopes"]:
    for m in s.get("protocolMappers", []):
        if m["protocolMapper"] == "oidc-audience-mapper":
            print(f"scope {s['name']:<16} adds audience {m['config']['included.client.audience']}")

# %% [markdown]
# ### 4. Start Trackr and triage-agent, and check the agent card's signature
# Trackr runs as its own server. The triage agent runs in this notebook, as in lesson 38a, so its model call is recorded here. The agent card is signed with a key the notebook pins: an unsigned card, or one signed by another key, is refused before the client uses it.

# %%
trackr_proc = subprocess.Popen([sys.executable, str(APPS / "trackr_org.py"), ISSUER, str(ISSUES), str(TRACKR_AUDIT)],
                               stdout=subprocess.DEVNULL, stderr=open(DATA / "trackr.err", "w"), env=os.environ)
procs.append(trackr_proc)
wait_for("http://127.0.0.1:8391/.well-known/oauth-protected-resource/mcp")
print("Trackr up on 8391")

# %% [markdown]
# The triage agent's card is signed with an ES256 key. The notebook pins the public key; a card that names another key, or has none, fails the check.

# %%
sys.path.insert(0, str(APPS))
import triage_org
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from a2a.utils.signing import create_agent_card_signer, create_signature_verifier

def new_es256_pair() -> tuple[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    return private.decode(), public.decode()

CARD_PRIV, CARD_PUB = new_es256_pair()                    # in production this key lives in a KMS
ATTACKER_PRIV, _ = new_es256_pair()
HEADER = {"kid": "triage-card-39", "alg": "ES256", "typ": "JOSE"}
signed_card = create_agent_card_signer(CARD_PRIV, HEADER)(triage_org.build_card(8392))
forged_card = create_agent_card_signer(ATTACKER_PRIV, HEADER)(triage_org.build_card(8392))
TRUSTED = {"triage-card-39": CARD_PUB}                    # the pinned store: key id -> public key

def trusted_key(kid, jku):
    if kid not in TRUSTED:
        raise jwt.InvalidKeyError(f"unknown key id {kid!r}")
    return TRUSTED[kid]                                    # jku is never fetched: a card may not choose its key

verify_card = create_signature_verifier(trusted_key, ["ES256"])
print("card signer and pinned key store ready | key id:", HEADER["kid"])

# %% [markdown]
# Now check both cards: the forged one must be refused, the signed one must pass.

# %%
try:
    verify_card(forged_card)
    FORGED_REFUSED = False
    print("forged card: ACCEPTED (this is a bug)")
except Exception as e:
    FORGED_REFUSED = True
    print("forged card refused:", type(e).__name__)
verify_card(signed_card)
SIGNED_OK = True
print("signed card: verified against the pinned key")

# %% [markdown]
# Imports for the A2A client: the card resolver, the client factory and the message types.

# %%
from importlib.metadata import version
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import get_artifact_text, new_text_message
from a2a.types import Role, SendMessageRequest, TaskState
print("a2a-sdk", version("a2a-sdk"), "| client, helpers and types imported")

# %% [markdown]
# `AgentServer` serves an ASGI app as a task of this notebook's event loop, as lesson 18 did, and polls until the card answers.

# %%
class AgentServer:
    """One ASGI app served as a task of this notebook's event loop."""
    def __init__(self, app, port: int):
        self.url = f"http://127.0.0.1:{port}"
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))

    async def start(self, timeout: float = 15.0) -> "AgentServer":
        self.task = asyncio.create_task(self.server.serve())
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        async with httpx.AsyncClient(timeout=1) as http:
            while loop.time() < deadline:
                try:
                    if (await http.get(self.url + "/.well-known/agent-card.json")).status_code == 200:
                        return self
                except httpx.TransportError:
                    pass
                await asyncio.sleep(0.1)
        raise RuntimeError("the triage agent did not answer its card URL in time")

    async def stop(self) -> None:
        self.server.should_exit = True
        await self.task

print("AgentServer ready (serves an ASGI app until stopped)")

# %% [markdown]
# Start triage-agent on 8392 and read its card the way a client does. The card is accepted only if the signature checks.

# %%
triage = await AgentServer(triage_org.build_app(signed_card), 8392).start()
async with httpx.AsyncClient(timeout=10) as http:
    found = await A2ACardResolver(http, triage.url).get_agent_card(signature_verifier=verify_card)
print("triage-agent card read and verified | skills:", [s.id for s in found.skills])

# %% [markdown]
# ### 5. Alice signs in: her token names her, her team and her role
# Alice signs in through the public client `ops-cli`. The scope list asks for the orchestrator's audience and the triage scope. Read the token: `sub` and `preferred_username` name alice, `teams` and `roles` come from the organisation's records, and `aud` names the orchestrator only. The token has no `act`, because nobody has acted for her yet. (The password grant keeps the notebook short; lesson 34 shows the browser sign-in, and production never uses this grant.)

# %%
def login(user: str, scope: str) -> str:
    """Sign in through the public client ops-cli, asking for exactly the scopes in `scope`."""
    r = httpx.post(TOKEN_URL, data={"grant_type": "password", "client_id": "ops-cli", "username": user,
                                    "password": DEMO_PASSWORD, "scope": scope}, timeout=10)
    r.raise_for_status()
    return r.json()["access_token"]

def claims(token: str) -> dict:
    return jwt.decode(token, options={"verify_signature": False})   # for reading only; the servers verify

SHOW = ["sub", "preferred_username", "aud", "azp", "scope", "teams", "roles", "act"]
ALICE_ORCH = login("alice", "ops-audience issues:read triage:run")
print({k: claims(ALICE_ORCH).get(k) for k in SHOW})

# %% [markdown]
# ### 6. Each token works at one audience
# The orchestrator's token names the orchestrator. Trackr checks that its own name is in `aud`, so the same token is refused there. Trackr's own token is asked for with the Trackr audience scope. The raw request below shows the refusal before any tool runs.

# %%
INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "lesson-39", "version": "1"}}}
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
ORCH_AT_TRACKR = httpx.post(TRACKR, headers={**MCP_HEADERS, "Authorization": f"Bearer {ALICE_ORCH}"}, json=INIT, timeout=10).status_code
print("orchestrator token at Trackr:", ORCH_AT_TRACKR)
ALICE_TRACKR = login("alice", "trackr-audience issues:read issues:write")
print("alice's Trackr token: aud", claims(ALICE_TRACKR)["aud"], "| scope", claims(ALICE_TRACKR)["scope"])

# %% [markdown]
# ### 7. Agents have their own identity, with no user's team
# An agent asks for its own token with client credentials. Its `sub` is the agent's service account, not a person, and it carries no team. It may hold only the scopes its client was given: ops-agent cannot ask for a Trackr audience at all.

# %%
def service_token(client_id: str, secret: str, scope: str) -> httpx.Response:
    return httpx.post(TOKEN_URL, auth=(client_id, secret), data={"grant_type": "client_credentials", "scope": scope}, timeout=10)

r = service_token("ops-agent", OPS_SECRET, "triage-audience triage:run")
AGENT_CLAIMS = claims(r.json()["access_token"])
print("ops-agent:", {k: AGENT_CLAIMS.get(k) for k in SHOW})
r_bad = service_token("ops-agent", OPS_SECRET, "trackr-audience issues:read")
print("ops-agent asks for a Trackr audience:", r_bad.status_code, r_bad.json()["error"])

# %% [markdown]
# ### 8. The orchestrator's hop to triage-agent
# The orchestrator exchanges alice's token for one aimed at triage-agent. The exchange names the caller, ops-agent, and checks that alice's token already names ops-agent. The new token keeps `sub` and `teams`, drops the orchestrator's audience and carries only the scope the hop asked for.

# %%
def exchange(who: str, secret: str, subject: str, audience: str, scope: str) -> httpx.Response:
    return httpx.post(TOKEN_URL, auth=(who, secret), data={
        "grant_type": TOKEN_EXCHANGE, "subject_token": subject, "subject_token_type": TOKEN_TYPE,
        "requested_token_type": TOKEN_TYPE, "audience": audience, "scope": scope}, timeout=10)

r = exchange("ops-agent", OPS_SECRET, ALICE_ORCH, "triage-agent", "triage:run triage-audience")
assert r.status_code == 200, r.text
tokens["T2"] = r.json()["access_token"]
print("hop 2, for triage-agent:", {k: claims(tokens["T2"]).get(k) for k in SHOW})

# %% [markdown]
# ### 9. The model picks the team, and triage-agent reads Trackr (`needs-llm`)
# The orchestrator's model sees one tool and must choose it. The tool sends the hop 2 token over A2A. Triage-agent then makes hop 3 to Trackr, reads the team's issues and asks the model once to label them. That is the second model call. The recorder opens just before the first call and closes after the tool returns. The local calls inside that window are replayed from the recording in a replay run too (as in lesson 38a), so Trackr's audit line for this one call exists only in the recording run. Step 12 makes its calls outside the window, live.

# %%
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage

@tool("ask_triage_agent")
async def ask_triage_agent(team: str) -> str:
    """Ask triage-agent to label the open issues of one team (web or api). Use it for any triage request."""
    http = httpx.AsyncClient(headers={"Authorization": f"Bearer {tokens['T2']}"}, timeout=120)
    client = await create_client(agent=found, client_config=ClientConfig(streaming=False, httpx_client=http))
    try:
        task = None
        async for chunk in client.send_message(SendMessageRequest(message=new_text_message(team, role=Role.ROLE_USER))):
            if chunk.WhichOneof("payload") == "task":
                task = chunk.task
    finally:
        await http.aclose()
    assert TaskState.Name(task.status.state) == "TASK_STATE_COMPLETED", task.status
    return get_artifact_text(task.artifacts[0])

SYSTEM = SystemMessage("You are the Trackr ops orchestrator. Triage requests go to triage-agent through ask_triage_agent. Do not label issues yourself.")
QUESTION = HumanMessage("Label the open issues of the web team as bug, feature or question.")
print("tool ready:", ask_triage_agent.name)

# %% [markdown]
# The model call comes next. The recorder opens just before it.

# %% tags=["needs-llm"]
llm_replay.start("39_checkpoint-org-oauth")       # the window opens here
from llm_setup import get_llm
llm = get_llm(max_calls=2)                        # at most 2 calls: the pick, and triage-agent's labels
triage_org.LLM = llm
first = await llm.bind_tools([ask_triage_agent]).ainvoke([SYSTEM, QUESTION])
print("orchestrator asks for:", [(c["name"], c["args"]) for c in first.tool_calls])

# %% [markdown]
# The tool runs the model's pick. If the model did not run, this cell does nothing.

# %% tags=["needs-llm"]
if first is not None and first.tool_calls:
    result = await ask_triage_agent.ainvoke(first.tool_calls[0]["args"])
    print(result)

# %% [markdown]
# The recording closes here. If the model cells were skipped, the same tool runs with the team called by hand (no model: the titles are not labelled).

# %%
llm_replay.stop()                                 # the recording closes here
if result is None:
    result = await ask_triage_agent.ainvoke({"team": "web"})
    print("the model did not run here; the orchestrator called the tool itself:")
    print(result)

# %% [markdown]
# ### 10. Read the chain, and refuse what must fail
# The receipt from triage-agent names alice, her team and the chain of clients: ops-agent, then triage-agent, then Trackr. In a recording run Trackr's audit line also names alice; a replay run prints none (see the note in step 9). Then three requests that must fail: a skipped hop (triage-agent using alice's orchestrator token), a wider scope at hop 3, and ops-agent asking for Trackr's audience. Each refusal comes from the server, not from this notebook.

# %%
print(result.splitlines()[-1])
r3 = exchange("triage-agent", TRIAGE_SECRET, tokens["T2"], "trackr-mcp", "issues:read trackr-audience")
assert r3.status_code == 200, r3.text
tokens["T3"] = r3.json()["access_token"]
print("hop 3, for Trackr:", {k: claims(tokens["T3"]).get(k) for k in SHOW})
refusals = {
    "triage-agent skips hop 2 with alice's orchestrator token": exchange("triage-agent", TRIAGE_SECRET, ALICE_ORCH, "trackr-mcp", "issues:read trackr-audience"),
    "triage-agent widens hop 3 to issues:write": exchange("triage-agent", TRIAGE_SECRET, tokens["T2"], "trackr-mcp", "issues:read issues:write trackr-audience"),
    "ops-agent asks for a Trackr audience": exchange("ops-agent", OPS_SECRET, ALICE_ORCH, "trackr-mcp", "issues:read trackr-audience"),
}
REFUSED = {}
for what, resp in refusals.items():
    REFUSED[what] = (resp.status_code, resp.json()["error"])
    print(f"refused: {what}: {resp.status_code} {resp.json()['error']}")
print("Trackr's audit lines so far:")
if TRACKR_AUDIT.exists():
    for line in TRACKR_AUDIT.read_text().splitlines():
        rec = json.loads(line)
        print({k: rec[k] for k in ("tool", "sub", "azp", "teams", "decision", "reason")})
else:
    print("(none: in a replay run the local calls of step 9 come from the recording, so this run wrote no audit line)")

# %% [markdown]
# ### 11. Step-up: a wider scope needs a new sign-in
# Alice's Trackr token holds `issues:read` only. Closing issue 4 asks for `issues:write`, so Trackr refuses with `insufficient_scope` and says which scope it needs. The client then signs alice in again with the wider scope, and the same call succeeds. Here the second password grant stands in for the browser step-up of lesson 34, where a real app sends the user through the sign-in page again.

# %%
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

AUDIT_START = len(TRACKR_AUDIT.read_text().splitlines()) if TRACKR_AUDIT.exists() else 0   # steps 11 and 12 start here
ALICE_READ = login("alice", "trackr-audience issues:read")
async def trackr(token: str, tool: str, args: dict) -> tuple[bool, str]:
    """One MCP call to Trackr with a bearer token: (allowed, text). A token refused before the tool runs gives (False, why)."""
    http = httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=10)
    try:
        async with Client(streamable_http_client(TRACKR, http_client=http)) as mcp:
            reply = await mcp.call_tool(tool, args)
        return (not reply.is_error), reply.content[0].text
    except Exception:                             # the SDK raised: the token was refused before any tool ran
        async with httpx.AsyncClient(timeout=10) as raw:          # ask the door for its status, plainly
            status = (await raw.post(TRACKR, headers={**MCP_HEADERS, "Authorization": f"Bearer {token}"}, json=INIT)).status_code
        return False, f"{status} refused before the tool ran"
    finally:
        await http.aclose()

before_ok, before_text = await trackr(ALICE_READ, "close_issue", {"issue_id": 4})
print("close issue 4 with issues:read only:", "allowed" if before_ok else "refused", "|", before_text)
ALICE_WRITE = login("alice", "trackr-audience issues:read issues:write")
after_ok, after_text = await trackr(ALICE_WRITE, "close_issue", {"issue_id": 4})
print("close issue 4 after the step-up:", "allowed" if after_ok else "refused", "|", after_text)
STEP_UP_OK = (not before_ok) and "insufficient_scope" in before_text and after_ok

# %% [markdown]
# ### 12. Who can call what: the matrix, with tests
# Each row is a principal with the token it really holds. Each column is one call to Trackr. The expected answers follow the rules: a user's team limits the reads and the closes, the lead role is needed to close, the scope limits the closes, and a token for another audience is refused. The triage row is alice's hop 3 token, so it acts for alice with her team and only the scope the hop passed on. The cell fails if any answer differs from the rules.

# %%
PRINCIPALS = {
    "alice (web, lead)": login("alice", "trackr-audience issues:read issues:write"),
    "bob (api, lead)": login("bob", "trackr-audience issues:read issues:write"),
    "carol (web, member)": login("carol", "trackr-audience issues:read issues:write"),
    "ops-agent (its own token)": service_token("ops-agent", OPS_SECRET, "triage-audience triage:run").json()["access_token"],
    "triage-agent (no user)": service_token("triage-agent", TRIAGE_SECRET, "trackr-audience issues:read").json()["access_token"],
    "triage-agent for alice": tokens["T3"],
}
COLUMNS = [("read web", "list_open_issues", {"team": "web"}), ("read api", "list_open_issues", {"team": "api"}),
           ("close 15 (web)", "close_issue", {"issue_id": 15}), ("close 21 (api)", "close_issue", {"issue_id": 21})]
EXPECTED = {
    "alice (web, lead)": [True, False, True, False],
    "bob (api, lead)": [False, True, False, True],
    "carol (web, member)": [True, False, False, False],
    "ops-agent (its own token)": [False, False, False, False],
    "triage-agent (no user)": [False, False, False, False],
    "triage-agent for alice": [True, False, False, False],
}
matrix = {}
for who, token_value in PRINCIPALS.items():
    matrix[who] = [await trackr(token_value, tool, args) for _, tool, args in COLUMNS]
    got = [ok for ok, _ in matrix[who]]
    assert got == EXPECTED[who], (who, got, EXPECTED[who])
MATRIX_OK = True
print("who-can-call-what matrix: every answer matches the rules (tests passed)")

# %% [markdown]
# ### 13. The access-review table
# The table is printed from the answers above, not typed by hand. A reviewer reads it to see who can do what, and why each refusal happened.

# %%
def why(text: str) -> str:
    """The short reason: the gate that refused (insufficient_scope, forbidden) or the HTTP status before the tool ran."""
    if "refused before the tool ran" in text:
        return text.split()[0] + " (token refused at the door)"
    return text.split(": ", 1)[-1].split(":")[0] if "Error executing tool" in text else text

print("| principal | " + " | ".join(name for name, _, _ in COLUMNS) + " |")
print("| --- | " + " | ".join("---" for _ in COLUMNS) + " |")
for who, row in matrix.items():
    cells = [("yes" if ok else "no: " + why(text)) for ok, text in row]
    print(f"| {who} | " + " | ".join(cells) + " |")
audit = [json.loads(line) for line in TRACKR_AUDIT.read_text().splitlines()][AUDIT_START:]   # only steps 11 and 12
TABLE_PRINTED = len(matrix) == len(PRINCIPALS)
print(f"\nTrackr audit: {len(audit)} lines, {sum(a['decision'] == 'allowed' for a in audit)} allowed, "
      f"{sum(a['decision'] == 'refused' for a in audit)} refused; every line names the user or agent that asked.")

# %% [markdown]
# ### 14. Ship check: every requirement, ticked
# Each line below is a check the cells above already ran. A failed check stops the cell.

# %%
checks = {
    "R1 one organisation server answers at its issuer": ISSUER_OK,
    "R2 token names user, team and role": claims(ALICE_ORCH)["preferred_username"] == "alice" and claims(ALICE_ORCH)["teams"] == ["web"]
        and claims(ALICE_ORCH)["roles"] == ["lead"],
    "R3 orchestrator token refused at Trackr (wrong audience)": ORCH_AT_TRACKR == 401,
    "R4 agent: own service account, no user team": AGENT_CLAIMS["sub"] and "teams" not in AGENT_CLAIMS,
    "R5 chain narrows; skip, widen and foreign audience refused": REFUSED[list(refusals)[0]][0] == 403
        and REFUSED[list(refusals)[1]] == (400, "invalid_scope") and REFUSED[list(refusals)[2]] == (400, "invalid_scope"),
    "R6 step-up: refused, then allowed after a wider sign-in": STEP_UP_OK,
    "R7 forged card refused, pinned card verified": FORGED_REFUSED and SIGNED_OK,
    "R8 matrix matches the rules": MATRIX_OK,
    "R9 access-review table printed": TABLE_PRINTED,
}
for name, passed in checks.items():
    print(("PASS" if passed else "FAIL"), name)
assert all(checks.values())

# %% [markdown]
# ## At real scale
# - **One server, many clients.** Keycloak signs every token and each service keeps only the public keys. A leaver is disabled once. Lesson 34 covers the realm.
# - **Agents are identities.** An agent has a service account and a secret held in a secret store, and carries no user's team unless it acts for a user. Lesson 35 covers this.
# - **Chains narrow, and logs name them.** In this build, Keycloak 26.8's standard exchange returned no `act` claim (step 10 prints `act: None`). RFC 8693 §4.1 defines a nested `act`. Lesson 38a shows that nested form with its own stand-in server, not with Keycloak. Here the chain is read from `azp`, the receipt and the audit lines. Lesson 28 covers tracing.
# - **Review is data.** The access-review table comes from the same calls that enforce the rules, so the report cannot drift from the code. Lesson 33 covers the production gates.

# %% [markdown]
# ## Decision guide
# Three choices come up in every multi-team deployment. Each rule has a reason from the docs or from this build.

# %% [markdown]
# **One realm or several.** Use one realm per organisation that shares its users, roles and clients. Keycloak says "Realms are isolated from one another and can only manage and authenticate the users that they control", so a second realm means a second set of users and admins. Teams inside one company are claims, not realms: `ops-org` holds both teams, and `teams` in the token separates them (step 5). Use a separate realm when two organisations must not share an administrator.

# %% [markdown]
# **Token exchange or a service token.** Exchange when a hop acts for a person and the next service must still see that person: alice's `sub` and `teams` survive hop 2 and hop 3 (steps 8 and 10). Use a service token (client credentials, step 7) when the work is the agent's own and no person's team should apply: without a user, triage-agent is refused in every column of the matrix (step 12). Exchange needs a confidential caller with the standard-exchange switch on, as Keycloak's token-exchange page requires; this realm turns it on for the two agents only.

# %% [markdown]
# **Team in the token or looked up.** Put the team and role in the token when every service already verifies the signature and should not make a directory call per request: Trackr reads `teams` from the verified token (step 6). The price is staleness: a removed team stays valid until the token expires, which is 300 s here (`accessTokenLifespan`). Look the team up on each call instead when a removal must take effect at once, and accept one more call and a directory that must stay up.

# %% [markdown]
# ## What just happened
# - One organisation server issued tokens for three users in two teams, and two agents with their own identities.
# - Each token named one audience. The orchestrator's token did not open Trackr.
# - Alice's request reached Trackr through two exchanges. Trackr saw alice, her team and the hop that called it, and no hop could widen the scope.
# - A step-up was refused until alice signed in again with the wider scope.
# - The matrix matched the rules, and each refusal came from a check on the server.

# %% [markdown]
# ## Reference solution
# The build above is the reference. Before you expand the hidden cell, predict the matrix row for carol closing issue 15 and say which check refuses it. The hidden cell prints the rule that decides each column.

# %% tags=["solution"]
print("Gate order in Trackr: scope (insufficient_scope) -> team (forbidden) -> lead role (forbidden).")
print("Carol closing 15: her scope and team pass, so the lead-role gate refuses her as a member.")

# %% [markdown]
# ## Common mistakes
# Forwarding the orchestrator's token to Trackr. The audience check refuses it, so the call fails before any tool runs.

# %% tags=["raises-exception"]
r = httpx.post(TRACKR, headers={**MCP_HEADERS, "Authorization": f"Bearer {ALICE_ORCH}"}, json=INIT, timeout=10)
r.raise_for_status()

# %% [markdown]
# Fix: ask for a token with Trackr's audience scope (step 6), or exchange for it at the hop (step 10). A second mistake is to trust the `teams` value sent in a request. Trackr reads it only from the verified token.

# %% [markdown]
# ## Try it
# Carol is a member, so she cannot close issues even though her token holds `issues:write`. Predict the answer, then ask Trackr to close issue 9 with carol's token. Print the answer, and in one sentence say which of the three gates refuses her.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below

# %% tags=["solution"]
ok, text = await trackr(PRINCIPALS["carol (web, member)"], "close_issue", {"issue_id": 9})
print("allowed" if ok else "refused", "|", text)
print("The lead-role gate refuses her: her scope and team pass, and she is a member, not a lead.")

# %% [markdown]
# Clean up: stop the triage agent and Trackr, stop the stand-in if it ran, and tear down the Keycloak container. The audit logs stay in `../data/39`.

# %%
await triage.stop()
for p in procs:
    p.terminate()
for p in procs:
    p.wait(timeout=10)
if KC_UP:
    subprocess.run([*COMPOSE, "down", "-v"], check=True, capture_output=True, env=os.environ)
print("servers stopped | Keycloak container removed | audit logs kept in ../data/39")

# %% [markdown]
# ## Key terms
# - **Audience (`aud`)** — the server a token is for; each server refuses tokens not naming it (lesson 39).
# - **Teams and roles claims** — the user's groups and realm roles, read from the verified token and used for tenant and role decisions (lesson 39).
# - **Token exchange (RFC 8693)** — a hop trades the token it got for one aimed at the next service (lesson 38a, lesson 39).
# - **Step-up** — a request for a wider scope that the server refuses until the user signs in again (lesson 39).
# - **Access-review table** — the printed who-can-call-what result, produced from the same calls that enforce the rules (lesson 39).
