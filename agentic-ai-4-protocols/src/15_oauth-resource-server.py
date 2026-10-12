# %% [markdown]
# # 15 · Protecting an MCP server: OAuth 2.1 resource server
# Level L3 · Part 3 · core · ~35 min · builds on 06

# %% [markdown]
# ## Goal
# By the end Trackr runs on `127.0.0.1:8767` as an OAuth 2.1 resource server. No token gets `401` with a `WWW-Authenticate` challenge. A wrong-audience or expired token is refused, and a token without `issues:read` gets `403`. A real model then counts the web team's issues with a read token.

# %% [markdown]
# ## The idea
# A remote MCP server is a **resource server**. It does not issue tokens. It only checks them. Every request must carry `Authorization: Bearer <token>`. The server checks three things. The signature must be valid, so the token came from a trusted authorization server. The audience must be this server, so a token made for another service is refused. The scopes must allow the tool, so a read token cannot close an issue. A missing scope shows up in two ways: HTTP 403 for the server-wide scope, a tool error for a per-tool scope.
#
# Analogy: a hotel key card. The door checks that the card is genuine (signature), that it opens this hotel and not another (audience), and which floors it covers (scopes).

# %% [markdown]
# ## Picture
# ```mermaid
# sequenceDiagram
#   participant C as Client (model host)
#   participant T as Trackr (resource server)
#   participant A as Authorization server
#   C->>T: POST /mcp, no token
#   T-->>C: 401 WWW-Authenticate: resource_metadata=...
#   C->>T: GET /.well-known/oauth-protected-resource/mcp
#   T-->>C: authorization_servers, scopes_supported
#   C->>A: get a token for this resource (lesson 16)
#   A-->>C: access token (aud = Trackr, scope = issues:read)
#   C->>T: POST /mcp, Authorization: Bearer ...
#   T-->>C: checks signature, audience, scope, then the tool runs
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. Set the names and the dev key
# The audience is the server's own address, `RESOURCE`. The issuer is the authorization server. In this lesson that server is a stub: it only mints dev tokens with PyJWT. Lesson 16 replaces it with a real flow. The key is for dev tokens only, and it is not a secret.

# %%
import sys, subprocess, time, atexit
from pathlib import Path
import httpx, jwt
sys.path.insert(0, "..")   # so llm_setup and llm_replay import
import llm_replay
assert Path("../apps/03/trackr_server.py").exists(), "run lesson 03 first: it writes the Trackr tools"
PORT = 8767
RESOURCE = f"http://127.0.0.1:{PORT}/mcp"                # this server's audience (its canonical URI)
ISSUER = "http://127.0.0.1:9000"                         # the authorization server (a dev stub here)
import os, sys
sys.path.insert(0, "..")   # tut_env lives in the topic folder
from tut_env import env
for _name in ("DEV_SIGNING_KEY", "LAB_PROXY_CLIENT_SECRET", "LAB_NOTES_CLIENT_SECRET"):
    os.environ[_name] = env(_name, "")   # from .env (never in the lesson)
assert len(os.environ["DEV_SIGNING_KEY"]) >= 32, "put DEV_SIGNING_KEY (32+ characters) in .env: see .env.example"
DEV_KEY = os.environ["DEV_SIGNING_KEY"]
URL = RESOURCE
Path("../apps/15").mkdir(parents=True, exist_ok=True)
print("resource (audience):", RESOURCE, "| issuer:", ISSUER)

# %% [markdown]
# ### 2. Write the protected server
# The tools are the lesson 03 Trackr tools. This file adds the protection. `DevVerifier` is the token verifier: it checks the signature, the issuer and the audience with PyJWT. `AuthSettings` turns on the protection. `required_scopes` says every call needs `issues:read`. `validate_token_resource=True` makes the SDK check the audience a second time. Each tool then checks its own scope with `require`. The SDK calls only `verify_token`. `TokenVerifier` is a Protocol, so `DevVerifier` needs no base class.

# %%
%%writefile ../apps/15/trackr_oauth.py
"""Trackr as an OAuth 2.1 resource server (lesson 15): the lesson 03 tools behind bearer tokens on 127.0.0.1:8767."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "03"))  # the lesson 03 tools
import jwt
import trackr_server as base
from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

PORT = 8767
RESOURCE = f"http://127.0.0.1:{PORT}/mcp"      # this server's canonical URI (the audience)
ISSUER = "http://127.0.0.1:9000"               # the authorization server (dev stub: it only mints tokens here)
import os
DEV_KEY = os.environ["DEV_SIGNING_KEY"]

class DevVerifier:
    """Checks the signature, the issuer and the audience (the resource), then reads the scopes."""
    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            claims = jwt.decode(token, DEV_KEY, algorithms=["HS256"], audience=RESOURCE, issuer=ISSUER)
        except jwt.PyJWTError:
            return None                        # bad signature, expired, wrong audience: no access
        return AccessToken(token=token, client_id=claims["client_id"], scopes=claims["scope"].split(),
                           expires_at=claims["exp"], resource=claims["aud"], subject=claims["sub"])

mcp = MCPServer("Trackr", token_verifier=DevVerifier(), auth=AuthSettings(
    issuer_url=ISSUER, resource_server_url=RESOURCE, required_scopes=["issues:read"],
    validate_token_resource=True))

def require(scope: str) -> None:
    """Per-tool check: the caller's token must carry this scope."""
    token = get_access_token()
    if token is None or scope not in token.scopes:
        raise ToolError(f"insufficient_scope: this tool needs {scope}")

@mcp.tool(title="Count open issues", annotations=ToolAnnotations(readOnlyHint=True))
def count_open(team: base.Team) -> int:
    require("issues:read")
    return base.count_open(team)

@mcp.tool(title="Close an issue", annotations=ToolAnnotations(destructiveHint=True))
def close_issue(issue_id: int) -> base.Issue:
    require("issues:write")
    return base.close_issue(issue_id)

if __name__ == "__main__":
    mcp.run("streamable-http", host="127.0.0.1", port=PORT, json_response=True)

# %% [markdown]
# The server is a resource server only. It checks tokens and never issues them. Next, you need tokens to test it. In this lesson PyJWT mints them with the claims a real authorization server would put in: `iss`, `aud`, `scope` and `exp`.

# %%
def mint(scope, audience=RESOURCE, ttl=600, client_id="ops-desk"):
    """A dev access token. A negative ttl gives a token that has already expired."""
    now = int(time.time())
    claims = {"iss": ISSUER, "aud": audience, "sub": "dev-user", "client_id": client_id,
              "scope": scope, "iat": now, "exp": now + ttl}
    return jwt.encode(claims, DEV_KEY, algorithm="HS256")

read_token = mint("issues:read")
write_token = mint("issues:read issues:write")
print("read token claims:", jwt.decode(read_token, options={"verify_signature": False}))

# %% [markdown]
# ### 3. Start the server and wait until it answers
# The server runs as its own process, as it would on a real host. The notebook polls the protected-resource metadata. That URL needs no token, so it answers as soon as the server is up. The cell gives up after 20 seconds, and it stops the server if the cell fails.

# %%
server_log = open("../apps/15/server.log", "w")   # closed in the cleanup cell
proc = subprocess.Popen([sys.executable, str(Path("../apps/15/trackr_oauth.py").resolve())],
                        stdout=server_log, stderr=subprocess.STDOUT)
atexit.register(lambda: proc.poll() is None and proc.terminate())
PRM_URL = f"http://127.0.0.1:{PORT}/.well-known/oauth-protected-resource/mcp"
deadline = time.monotonic() + 20
while True:
    try:
        meta = httpx.get(PRM_URL, timeout=10)
        break
    except httpx.ConnectError:
        if proc.poll() is not None or time.monotonic() > deadline:
            raise RuntimeError("server did not start: read ../apps/15/server.log")
        time.sleep(0.2)
print("server answered:", meta.status_code)

# %% [markdown]
# ### 4. The helper that sends the bearer token
# `post` works like lesson 06, with one addition. If a token is given, it goes in the `Authorization` header of that request. The header is sent on every request, because the server keeps no session.

# %%
META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28", "io.modelcontextprotocol/clientCapabilities": {}}
BASE = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json",
        "MCP-Protocol-Version": "2026-07-28"}

def body(method, params=None, req_id=1):
    return {"jsonrpc": "2.0", "id": req_id, "method": method, "params": {**(params or {}), "_meta": META}}

def post(method, params=None, token=None, name=None):
    """One POST to /mcp. The bearer token, if given, is sent in the Authorization header."""
    headers = {**BASE, "Mcp-Method": method}
    if name:
        headers["Mcp-Name"] = name
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.post(URL, json=body(method, params), headers=headers, timeout=10)

# %% [markdown]
# ### 5. No token: the 401 challenge points to the metadata
# The first request has no token, so the server refuses it with `401`. The `WWW-Authenticate` header says how to get in. It names the metadata URL. The client reads that URL to find the authorization server and the scopes.

# %%
r = post("tools/list")
print("status:", r.status_code)
print("WWW-Authenticate:", r.headers["www-authenticate"])
print("metadata:", meta.json())

# %% [markdown]
# ### 6. Who gets in: the token checks
# Here are five callers. Each row shows the status and the challenge the server sent back. A `401` means the token is not accepted. A `403` means the token is valid but lacks a scope. The server checks the signature, the expiry, the audience and then the scopes.

# %%
def show(label, r):
    challenge = r.headers.get("www-authenticate", "-").split(",")[0]   # first part: the error name
    print(f"{label:36} {r.status_code}  {challenge}")

show("no token", post("tools/list"))
show("expired read token", post("tools/list", token=mint("issues:read", ttl=-60)))
show("token for another audience", post("tools/list", token=mint("issues:read", audience="http://evil.example/mcp")))
show("write-only token (no issues:read)", post("tools/list", token=mint("issues:write")))
show("read token", post("tools/list", token=read_token))

# %% [markdown]
# ### 7. Scopes per tool: reading is not closing
# The read token passes the server-wide check. `count_open` needs `issues:read`, so it works. `close_issue` needs `issues:write`. The read token gets a tool error (`isError`) that names the missing scope. The write token closes issue 2, an `api` issue, so the web count stays the same.

# %%
def tool_text(r):
    res = r.json()["result"]
    text = " ".join(res["content"][0]["text"].split())   # one line
    return ("ERROR " if res.get("isError") else "") + text[:80]

close = {"name": "close_issue", "arguments": {"issue_id": 2}}
print("count_open, read token :", tool_text(post("tools/call", {"name": "count_open", "arguments": {"team": "web"}}, read_token, "count_open")))
print("close_issue, read token:", tool_text(post("tools/call", close, read_token, "close_issue")))
print("close_issue, write token:", tool_text(post("tools/call", close, write_token, "close_issue")))

# %% [markdown]
# ### 8. A real model uses the protected server (`needs-llm`)
# The model host passes the token to the client once. `Client(URL, auth=token)` sends it on every POST. `MCPAdapter` then gives the model the tools, as in lesson 06. The model makes two calls at most: one to ask for a tool, and one to write the answer.
#
# First the quiet setup and the adapter. The adapter is beta, so its warning is filtered.

# %%
import logging, warnings
from contextlib import AsyncExitStack
from fastmcp import Client
from langchain.mcp import MCPAdapter
from langchain_core._api import LangChainBetaWarning
warnings.filterwarnings("ignore", category=LangChainBetaWarning)  # the adapter is still beta
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("fastmcp").setLevel(logging.WARNING)
stack = AsyncExitStack()   # the adapter stays open for the model cells; closed at the end
adapter = await stack.enter_async_context(MCPAdapter(Client(URL, auth=read_token)))
mcp_tools = await adapter.list_tools()
by_name = {t.name: t for t in mcp_tools}
print(sorted(by_name))
assert "count_open" in by_name

# %% [markdown]
# The question comes next. The model gets it with the tool list.

# %%
from langchain_core.messages import AIMessage, HumanMessage
QUESTION = HumanMessage("How many open issues does the web team have? Use a tool.")
llm = None   # filled by the model cell; stays None if that cell is skipped
print("question:", QUESTION.content)

# %% [markdown]
# The model cell below asks the model which tool to use. Its first call asks for the tool. `get_llm` starts the recording or the replay for this lesson.

# %% tags=["needs-llm"]
from llm_setup import get_llm
llm = get_llm("15_oauth-resource-server", max_calls=2)
first = await llm.bind_tools(mcp_tools).ainvoke([QUESTION])
print("model asks for:", [(c["name"], c["args"]) for c in first.tool_calls])

# %% [markdown]
# If the model cell was skipped, a scripted tool call stands in for the model's first reply. The stand-in is labelled.

# %%
if llm is None:   # fallback: the model cell was skipped
    first = AIMessage(content="", tool_calls=[{"name": "count_open", "args": {"team": "web"}, "id": "scripted_1"}])
    print("SCRIPTED stand-in (no model): model asks for:", [(c["name"], c["args"]) for c in first.tool_calls])

# %% [markdown]
# The host runs each requested tool through the adapter. The adapter sends the call to the server as a POST with the read token.

# %%
results = [await by_name[c["name"]].ainvoke(c) for c in first.tool_calls]
for r in results:
    print("ToolMessage status:", r.status, "| text:", r.text)

# %% [markdown]
# The model reads the result and writes its answer. This is its second and last call (`needs-llm`).

# %% tags=["needs-llm"]
final = await llm.bind_tools(mcp_tools).ainvoke([QUESTION, first, *results])
print("answer:", final.text)

# %% [markdown]
# If the model cell was skipped, the fallback prints what the tool returned, labelled as such.

# %%
if llm is None:   # fallback: no model, so no written answer
    print("answer (skipped: no model here). The tool said:", results[0].text)

# %% [markdown]
# ### 9. Close the adapter
# The model cells are done. The server stays up for the checks that follow, and the cleanup cell stops it.

# %%
await stack.aclose()
print("adapter closed | the server is still running for the checks below")

# %% [markdown]
# ## At work
# - Production servers verify tokens against one organisation-wide authorization server. The client sends the resource indicator (RFC 8707 `resource`), and the server refuses any token whose audience is not its own, so one leaked token cannot open every tool → lesson 34 (professional).
# - Scopes are checked per tool, because read and write differ. The SDK's `required_scopes` is server-wide and gives `403 insufficient_scope`. A per-tool check stops one dangerous tool, such as a close or delete. Teams keep the scope list small and do not publish every scope in `scopes_supported`. The authorization server defines the scopes centrally → lesson 34 (professional).
# - The MCP spec forbids token passthrough: a server must not accept or forward another service's token. The server gets its own token for the upstream call, or uses its own credential → lesson 31.

# %% [markdown]
# ## What just happened
# - With no token the server answered `401`, and the `WWW-Authenticate` header named the metadata URL. That URL told the client where to get a token.
# - The verifier checked the signature, the issuer, the audience and the expiry. Expired tokens and tokens for another audience got `401`.
# - A valid token without `issues:read` got `403 insufficient_scope` at the door, because the server requires that scope for every call.
# - Inside the server, `close_issue` checked for `issues:write`. The read token got a tool error that named the scope. The write token closed the issue.
# - The model used the read token through the adapter. It asked for `count_open`, and the answer was 3.

# %% [markdown]
# ## Common mistakes
# Calling the server without a token and treating the `401` as a normal reply. `raise_for_status()` turns it into an exception that names the status:

# %% tags=["raises-exception"]
post("tools/list").raise_for_status()   # raises httpx.HTTPStatusError: 401 Unauthorized

# %% [markdown]
# Fix: get a token first, then send it in `Authorization` on every request. Check `WWW-Authenticate` to learn where the token comes from.
#
# A second mistake is minting the token for the bare host instead of the resource. The `aud` claim is `http://127.0.0.1:8767`, but the server's resource is `http://127.0.0.1:8767/mcp`. The audience check fails, and the server answers `401`:

# %% tags=["raises-exception"]
post("tools/list", token=mint("issues:read", audience="http://127.0.0.1:8767")).raise_for_status()   # raises httpx.HTTPStatusError: 401 Unauthorized

# %% [markdown]
# Fix: set `aud` to the exact resource, `RESOURCE`, path included. The audience is compared as a string, so the `/mcp` must match. With the exact resource the same request passes:

# %%
r = post("tools/list", token=mint("issues:read", audience=RESOURCE))
print("status with the exact resource:", r.status_code)

# %% [markdown]
# ## Try it
# Mint a read token that expires in 2 seconds. Wait 3 seconds, then call `count_open` for the web team with it, using `post`. Print the status and the challenge. Then mint a fresh read token and call `count_open` with it, and print the count. No model is needed.

# %%
# your code here
# Start from mint("issues:read", ttl=2), then time.sleep(3), then post("tools/call", {"name": "count_open", "arguments": {"team": "web"}}, token, "count_open").

# %% [markdown]
# Clean up: stop the server process and tell the recorder the lesson is done. This cell runs last.

# %%
proc.terminate()
proc.wait(timeout=10)
server_log.close()
llm_replay.stop()
print("server stopped | lesson 15 done")

# %% [markdown]
# ## Key terms
# - **resource server** — an API that checks bearer tokens. A remote MCP server is one. It never issues tokens.
# - **Protected Resource Metadata** — the document at `/.well-known/oauth-protected-resource/...` (RFC 9728). It names the authorization servers and the scopes.
# - **WWW-Authenticate challenge** — the header on a `401` or `403`. It says what the client must do, and it names the metadata URL.
# - **audience** — the `aud` claim: the resource a token was issued for. The server refuses tokens for another audience.
# - **token verifier** — the server's check of a bearer token. Here it is `DevVerifier`, which returns an `AccessToken` or nothing.
# - **scope** — a permission string such as `issues:read`. The server checks it per request and per tool.
# - **insufficient_scope** — the error name for a valid token that lacks a scope. The server-wide `required_scopes` check answers it as HTTP `403`. A per-tool check, such as `close_issue`, returns an `isError` tool result and no 403.
