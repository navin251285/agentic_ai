# %% [markdown]
# # 04 · Resources and prompts: context the app and the user control
# Level L2 · Part 2 · professional · ~30 min · builds on 03

# %% [markdown]
# ## Goal
# By the end you have a Trackr server that publishes read-only **resources** (two static ones and the runbook template `runbook://{team}`), a **prompt** `triage_issue` with argument **completion**, and a resource list that you page with a **cursor**. You can say who controls each primitive, and one real model call drafts a triage note from the runbook and the prompt.

# %% [markdown]
# ## Why it matters
# Without resources and prompts, the app keeps its own copy of every piece of context. The snippet below is the version without them. The runbook text and the prompt wording live in app code, so a new team means a code change and a redeploy. The user has no list of approved prompts to pick from, and the model sees only what the app remembers to paste in.

# %%
# Without resources and prompts: the app keeps its own copies of the text.
RUNBOOKS_IN_APP = {"web": "Web runbook: check the CDN, then roll back the last deploy."}
TRIAGE_TEMPLATE = "Triage Trackr issue {id}: {title}. Write a short triage note."
TEAMS = ["web", "api", "mobile", "infra"]
missing = [t for t in TEAMS if t not in RUNBOOKS_IN_APP]
print("teams the app has no runbook for:", missing)   # every one of these needs a code change

# %% [markdown]
# With a resource template, one definition serves every team. The host reads the runbook it needs by URI. A prompt gives the user a menu entry, and completion helps them type the team name. You do not need any of this for a one-off script with a fixed string. The model should not decide which runbook to read, though. If it should, that is a tool (lesson 03).

# %% [markdown]
# ## The idea
# MCP has three server primitives, and each has a different controller. A **resource** is read-only data under a URI. The **application** decides when to read it and what to attach. A **prompt** is a message template. The **user** picks it and fills in its arguments. A **tool** (lesson 03) is an action the **model** asks for.
#
# A **resource template** such as `runbook://{team}` has a variable in its URI. **Completion** suggests values for an argument while the user types. A long list comes back in pages, and each page carries a **cursor** (`nextCursor`) that the client sends back to get the next page.
#
# Analogy: a library. The librarian hands you the books on the shelf (resources). You fill in a request form (prompt). You may ask the librarian to do a task for you, and that is a tool.

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart LR
#   APP[Host app] -->|reads and attaches| RES[resources: trackr://teams, runbook://team]
#   USER[User] -->|picks and fills in| PR[prompt: triage_issue]
#   PR -->|argument values| CMP[completion/complete]
#   MODEL[Model] -->|asks for| TOOL[tools: lesson 03]
#   RES -->|long lists| PG[nextCursor pages]
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. Write the server
# The server is lesson 03's Trackr with the same 20 issues, but no tools. It has two static resources, one template, one prompt, one completion handler and a paged `resources/list`. The paging uses the low-level hook that the `@completion` decorator also uses, because the high-level server does not page on its own yet.

# %%
from pathlib import Path
APP_DIR = Path("../apps/04")
APP_DIR.mkdir(parents=True, exist_ok=True)
print("app folder ready:", APP_DIR)

# %% [markdown]
# The `writefile` cell below saves the server to `../apps/04/trackr_server.py`.

# %%
%%writefile ../apps/04/trackr_server.py
"""Trackr MCP server (lesson 04): resources, a template, a prompt, completion and paging."""
from mcp.server import MCPServer
from mcp.shared.exceptions import MCPError
from mcp.types import (INVALID_PARAMS, Completion, ListResourcesResult, PaginatedRequestParams,
                       PromptReference, ResourceTemplateReference)

TEAMS = ["web", "api", "mobile", "infra"]
PAGE_SIZE = 2     # resources/list returns this many per page; the cursor is the offset of the next page

ROWS = """1 Login button does nothing on Safari|web|open|high
2 Signup email arrives twice|api|open|medium
3 Dark mode hides the save icon|web|closed|low
4 App crashes when photo is rotated|mobile|open|critical
5 Rate limiter blocks health checks|infra|open|high
6 Search ignores capital letters|api|open|low
7 Push notifications arrive late|mobile|open|medium
8 Disk alert fires every night at 2am|infra|closed|medium
9 Typo on the pricing page|web|open|low
10 Export to CSV drops the last row|api|open|high
11 Offline mode loses drafts|mobile|closed|high
12 TLS certificate expires in 9 days|infra|open|critical
13 Footer links open in the same tab|web|closed|low
14 Pagination returns duplicates|api|open|medium
15 Battery drain in background sync|mobile|open|high
16 Backups not copied to second region|infra|open|high
17 Profile page slow to load|web|open|medium
18 Webhook retries never stop|api|closed|medium
19 Tablet layout cuts off buttons|mobile|open|low
20 Log volume doubled since Monday|infra|open|medium"""
ISSUES: list[dict] = [{"id": int(h.split(" ", 1)[0]), "title": h.split(" ", 1)[1], "team": t, "status": st, "severity": sv}
                      for h, t, st, sv in (line.split("|") for line in ROWS.splitlines())]
RUNBOOKS = {
    "web": "Web runbook\n1. Check the CDN status page.\n2. Roll back the last front-end deploy if errors rise.\n3. Page web on-call for high or critical.",
    "api": "API runbook\n1. Check the rate limiter and the queue depth.\n2. Replay failed webhooks after the fix.\n3. Page api on-call for high or critical.",
    "mobile": "Mobile runbook\n1. Check crash reports for the newest build.\n2. Halt the staged rollout if crashes rise.\n3. Page mobile on-call for critical.",
    "infra": "Infra runbook\n1. Check certificates, disks and backups.\n2. Freeze deploys during an incident.\n3. Page infra on-call for high or critical.",
}

mcp = MCPServer("Trackr")

@mcp.resource("trackr://teams", title="Teams", mime_type="application/json")
def teams() -> list[str]:
    """The teams that own issues."""
    return TEAMS

@mcp.resource("trackr://severities", title="Severities", mime_type="application/json")
def severities() -> list[str]:
    """The severity levels, lowest first."""
    return ["low", "medium", "high", "critical"]

@mcp.resource("trackr://issues/open", title="Open issues", mime_type="application/json")
def open_issues() -> list[dict]:
    """Every open issue: a live, read-only view of the tracker."""
    return [i for i in ISSUES if i["status"] == "open"]

@mcp.resource("runbook://{team}", title="Team runbook", mime_type="text/plain")
def runbook(team: str) -> str:
    """The runbook for one team. The host attaches it to a prompt."""
    if team not in RUNBOOKS:
        raise MCPError(code=INVALID_PARAMS, message=f"no runbook for team {team!r}")
    return RUNBOOKS[team]

@mcp.prompt(title="Triage an issue", description="Draft a triage note for one issue of one team.")
def triage_issue(issue_id: int, team: str) -> str:
    """The user picks this prompt and fills in the arguments."""
    issue = next((i for i in ISSUES if i["id"] == issue_id), None)
    if issue is None or issue["team"] != team:
        raise MCPError(code=INVALID_PARAMS, message=f"issue {issue_id} is not a {team} issue")
    return (f"Triage Trackr issue {issue['id']}: {issue['title']} (severity {issue['severity']}).\n"
            "Write a short triage note: likely cause, first step, and who to page. Use the runbook you are given.")

@mcp.completion()
async def complete(ref, argument, context):
    """Suggest team names for the 'team' argument of the prompt and of the runbook template."""
    if argument.name != "team" or not isinstance(ref, (PromptReference, ResourceTemplateReference)):
        return None
    matches = [t for t in TEAMS if t.startswith(argument.value.lower())]
    return Completion(values=matches, total=len(matches), has_more=False)

async def list_resources_paged(ctx, params: PaginatedRequestParams | None) -> ListResourcesResult:
    """Return the static resources PAGE_SIZE at a time. The client sends nextCursor back."""
    everything = await mcp.list_resources()
    start = int(params.cursor) if params and params.cursor else 0
    nxt = str(start + PAGE_SIZE) if start + PAGE_SIZE < len(everything) else None
    return ListResourcesResult(resources=everything[start:start + PAGE_SIZE], next_cursor=nxt)

mcp._lowlevel_server.add_request_handler("resources/list", PaginatedRequestParams, list_resources_paged)

if __name__ == "__main__":
    mcp.run()          # default transport: stdio

# %% [markdown]
# ### 2. Start the server and list its resources
# Start the server as a subprocess and talk JSON-RPC over stdin and stdout, as in lesson 03. Every request carries `_meta`. In the 2026-07-28 protocol the client sends `server/discover` first. `llm` is set to `None` here so that the model step can tell whether it ran.

# %%
import json, queue, subprocess, sys, threading, itertools
sys.path.insert(0, "..")   # the course helpers (llm_setup, llm_replay) import from here
import llm_replay
SERVER = (APP_DIR / "trackr_server.py").resolve()
server = subprocess.Popen([sys.executable, str(SERVER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=open(APP_DIR / "server.log", "w"), text=True, bufsize=1)
replies: queue.Queue = queue.Queue()
threading.Thread(target=lambda: [replies.put(l) for l in server.stdout], daemon=True).start()
META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientInfo": {"name": "lesson-04-notebook", "version": "0.1"},
        "io.modelcontextprotocol/clientCapabilities": {}}
ids = itertools.count(1)
llm = None   # filled by the model cell; stays None if that cell is skipped

def rpc(method: str, **params) -> dict:
    """Send one JSON-RPC request and return the whole reply (it has 'result' or 'error')."""
    msg = {"jsonrpc": "2.0", "id": next(ids), "method": method, "params": {**params, "_meta": META}}
    server.stdin.write(json.dumps(msg) + "\n"); server.stdin.flush()
    try:
        return json.loads(replies.get(timeout=10))
    except queue.Empty:
        raise TimeoutError(f"no reply to {method} within 10s") from None

print("server up:", rpc("server/discover")["result"]["supportedVersions"][0])

# %% [markdown]
# Now ask for the first page of resources. The server returns two of its three static resources, and a `nextCursor` that says more are waiting.

# %%
page1 = rpc("resources/list")["result"]
for r in page1["resources"]:
    print(f"{r['uri']:<22} title={r['title']!r} mime={r['mimeType']}")
print("nextCursor:", page1.get("nextCursor"))

# %% [markdown]
# ### 3. Read a static resource and a template
# A resource is read by its URI. A template is listed under `resources/templates/list`, and a URI that matches its pattern is read the same way. The host decides when to call `resources/read`. The model does not.

# %%
templates = rpc("resources/templates/list")["result"]["resourceTemplates"]
print("templates:", [t["uriTemplate"] for t in templates])
teams_read = rpc("resources/read", uri="trackr://teams")["result"]["contents"][0]
print("trackr://teams ->", teams_read["text"])
web = rpc("resources/read", uri="runbook://web")["result"]["contents"][0]
print("runbook://web, first line:", web["text"].splitlines()[0])
bad = rpc("resources/read", uri="runbook://sales")
print("runbook://sales -> error", bad["error"]["code"], "|", bad["error"]["message"])

# %% [markdown]
# ### 4. Follow the cursor to the next page
# The cursor is opaque to the client. Here it is an offset, but the client must not read meaning into it. It sends the cursor back as `cursor` until `nextCursor` is missing.

# %%
pages, cursor = [], None
while True:
    params = {} if cursor is None else {"cursor": cursor}
    page = rpc("resources/list", **params)["result"]
    pages.append([r["uri"] for r in page["resources"]])
    cursor = page.get("nextCursor")
    if cursor is None:
        break
for n, uris in enumerate(pages, start=1):
    print(f"page {n}: {uris}")

# %% [markdown]
# ### 5. Prompts: the user picks one and fills in the arguments
# `prompts/list` shows the menu. `prompts/get` fills in the arguments and returns the messages. The wire carries argument values as strings, so `"4"` reaches the function as the integer `4`. An argument pair that does not match is rejected as invalid params.

# %%
listed = rpc("prompts/list")["result"]["prompts"]
print("prompts:", [(p["name"], [a["name"] for a in p["arguments"]]) for p in listed])
got = rpc("prompts/get", name="triage_issue", arguments={"issue_id": "4", "team": "mobile"})["result"]
print("role:", got["messages"][0]["role"])
print(got["messages"][0]["content"]["text"])
mismatch = rpc("prompts/get", name="triage_issue", arguments={"issue_id": "2", "team": "mobile"})
print("issue 2 is not a mobile issue -> error", mismatch["error"]["code"])

# %% [markdown]
# ### 6. Completion: suggest the team as the user types
# The client sends `completion/complete` with a reference to the prompt or the template, the argument name and the partial value. The server answers with the values that match. Nothing is sent to the model here.

# %%
def complete(ref: dict, value: str) -> list[str]:
    reply = rpc("completion/complete", ref=ref, argument={"name": "team", "value": value})["result"]
    return reply["completion"]["values"]

PROMPT_REF = {"type": "ref/prompt", "name": "triage_issue"}
TEMPLATE_REF = {"type": "ref/resource", "uri": "runbook://{team}"}
print("prompt, typed 'm':", complete(PROMPT_REF, "m"))
print("template, typed '':", complete(TEMPLATE_REF, ""))

# %% [markdown]
# ### 7. Checks as code
# Each assertion matches one line of output above. If one fails, look at `trackr_server.py` in step 1.

# %%
assert [r["uri"] for r in page1["resources"]] == ["trackr://teams", "trackr://severities"]
assert page1["nextCursor"] == "2"
assert pages == [["trackr://teams", "trackr://severities"], ["trackr://issues/open"]]
assert json.loads(teams_read["text"]) == TEAMS
assert web["text"].splitlines()[0] == "Web runbook" and bad["error"]["code"] == -32602
assert got["messages"][0]["role"] == "user" and "Triage Trackr issue 4" in got["messages"][0]["content"]["text"]
assert mismatch["error"]["code"] == -32602
assert complete(PROMPT_REF, "m") == ["mobile"] and len(complete(TEMPLATE_REF, "")) == 4
print("resource, prompt and completion checks passed")

# %% [markdown]
# ### 8. The host attaches a runbook and a prompt; a real model drafts the note (`needs-llm`)
# This is the host's job. It fetches the prompt with the user's arguments, reads the runbook for that team by its URI, and sends both to the model. The notebook makes one model call. If the model cell is skipped, no note is drafted and the rest of the lesson still runs.

# %% tags=["needs-llm"]
from langchain_core.messages import HumanMessage
from llm_setup import get_llm
llm_replay.start("04_mcp-resources-and-prompts")   # record once, replay everywhere (at most 4 calls by default)
llm = get_llm()
prompt_text = rpc("prompts/get", name="triage_issue", arguments={"issue_id": "4", "team": "mobile"})["result"]["messages"][0]["content"]["text"]
runbook_text = rpc("resources/read", uri="runbook://mobile")["result"]["contents"][0]["text"]
note = llm.invoke([HumanMessage(f"{runbook_text}\n\n{prompt_text}")])
print(note.text)

# %% [markdown]
# If the model cell was skipped, `llm` is still `None` and this cell says so.

# %%
if llm is None:   # fallback: the model cell was skipped, so no note was drafted
    print("model cell skipped: no triage note drafted (no key and no recording)")

# %% [markdown]
# ## At work
# - Companies publish runbooks and wiki pages as resources, so one server feeds every team's host. The host decides which page to attach. Text from a wiki is untrusted input for the model, so it is a prompt-injection surface → lesson 30.
# - Long directories are paged in production. A list of thousands of resources cannot go in one reply, and every token of listing text is paid on each call → lesson 24 (the token cost of catalogues).
# - Remote servers run the same resource and prompt calls over Streamable HTTP, behind a load balancer. Paging must work across replicas → lesson 06.

# %% [markdown]
# ## What just happened
# - The server published three kinds of content with three controllers. Resources are read by the host when it chooses. The prompt is picked by the user. The tools from lesson 03 are requested by the model.
# - `resources/list` returned two resources and a `nextCursor`. The client sent the cursor back and got the third resource, then no cursor, which ends the listing.
# - The template `runbook://{team}` answered for any team the server knows. An unknown team came back as an invalid-params error, not a crash.
# - Completion suggested only the teams the server knows, so the suggestions match what the template accepts.
# - The model received the runbook and the prompt as plain text in one message. It drafted the note without calling any tool.

# %% [markdown]
# ## Common mistakes
# Reading only the first page and treating it as the whole list. The first page has two items here, so this check fails:

# %% tags=["raises-exception"]
page = rpc("resources/list")["result"]
assert len(page["resources"]) == 3, f"expected 3 resources, got {len(page['resources'])}"   # AssertionError: one page only

# %% [markdown]
# Fix: follow `nextCursor` until it is missing, as in step 4.
#
# A second mistake is to think the model picks resources. It cannot. A resource is read by the host, so the host decides what enters the context. If you want the model to read a runbook on its own, you must give it a tool, and then the usual tool rules from lesson 03 apply.

# %% [markdown]
# ## Try it
# Without the model, complete the team name for the prompt when the user has typed `i`. Then read `runbook://infra` and print its second line. Then fetch page 2 of `resources/list` using the cursor from `page1`, and print its URIs. The server is still running.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
print("completion for 'i':", complete(PROMPT_REF, "i"))
print("infra runbook, line 2:", rpc("resources/read", uri="runbook://infra")["result"]["contents"][0]["text"].splitlines()[1])
print("page 2 URIs:", [r["uri"] for r in rpc("resources/list", cursor=page1["nextCursor"])["result"]["resources"]])

# %% [markdown]
# Stop the server now. Close the server's stdin so it exits, then tell the recorder the lesson is done.

# %%
server.stdin.close(); _ = server.wait(timeout=5)
llm_replay.stop()
print("lesson 04 done: resources, a template, a prompt, completion and paging, used by a host and a model")

# %% [markdown]
# ## Key terms
# - **resource** — read-only data a server publishes under a URI. The application decides when to read it and what to attach.
# - **resource template** — a resource whose URI has a variable, such as `runbook://{team}`. One definition serves many URIs.
# - **prompt** — a reusable message template a server publishes. The user picks it and fills in its arguments.
# - **completion** — the `completion/complete` request that suggests values for an argument while the user types.
# - **pagination cursor** — an opaque string in a list result (`nextCursor`). The client sends it back as `cursor` to get the next page.
# - **controller** — who decides to use a primitive: the model for tools, the application for resources, the user for prompts.
