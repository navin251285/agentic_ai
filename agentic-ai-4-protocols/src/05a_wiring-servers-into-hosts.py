# %% [markdown]
# # 05a · Wiring servers into real hosts: Claude Desktop, Claude Code, VS Code, Cursor
# Level L2 · Part 2 · core · ~25 min · builds on 05

# %% [markdown]
# ## Goal
# By the end you have four host config files (Claude Desktop, Claude Code `.mcp.json`, VS Code `.vscode/mcp.json`, Cursor `.cursor/mcp.json`), all rendered from one Python dict. A validator checks each one the way its host would. Then the `mcpServers` block from the Claude Code file drives the same `MCPAdapter` as lesson 05, and a real model answers through it (2 calls).

# %% [markdown]
# ## The idea
# A host reads its own JSON file when it starts, and that file says which servers to run. The four files look alike but differ in small ways. Three hosts use the top-level key `mcpServers`, but VS Code uses `servers`. VS Code also wants a `type` on every entry. Claude Desktop reads only local servers from its file, and remote ones come from its Connectors screen. A wrong key does not raise an error in the host. The server just does not appear.
#
# So this lesson keeps one dict of servers and renders each host's file from it. A validator then checks each file before any host sees it.
#
# Analogy: a passport office with four forms. The same facts go on each form, but each form has its own box names and rules. You fill in one master sheet, copy it onto the four forms, and check each form before you hand it in.

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart LR
#   D[One Python dict: SERVERS] --> F1[claude_desktop_config.json]
#   D --> F2[.mcp.json for Claude Code]
#   D --> F3[.vscode/mcp.json for VS Code]
#   D --> F4[.cursor/mcp.json for Cursor]
#   F2 --> A[MCPAdapter reads the mcpServers block]
#   A --> T[trackr_* and runbooks_* tools for the model]
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. Name the servers once
# Trackr is the lesson 03 server and the runbooks server is from lesson 05. Both are in `../apps`. The remote entry is only a URL for now. The server behind it is built in lesson 06, so this lesson writes the entry and does not connect to it. The files go to `../apps/05a/hosts/`. Nothing touches your real home folder.

# %%
import json, sys
from pathlib import Path
TRACKR = Path("../apps/03/trackr_server.py").resolve()
RUNBOOKS = Path("../apps/05/runbooks_server.py").resolve()
assert TRACKR.exists() and RUNBOOKS.exists(), "run lessons 03 and 05 first: they write these servers"
HOSTS_DIR = Path("../apps/05a/hosts")
SERVERS = {
    "trackr": {"kind": "stdio", "command": sys.executable, "args": [str(TRACKR)]},
    "runbooks": {"kind": "stdio", "command": sys.executable, "args": [str(RUNBOOKS)]},
    "trackr-remote": {"kind": "remote", "url": "https://trackr.team.example/mcp"},
}
print("servers:", list(SERVERS))

# %% [markdown]
# ### 2. Render one file per host
# `command` must be an absolute path. A host starts the server from its own working folder, not from your notebook's folder, so `../apps/...` would fail there. `sys.executable` is the Python that has the `mcp` package. Each host has its own rule, kept in `RULES`. Claude Desktop skips the remote entry, because its file has no place for it.
# `env` holds extra environment variables for the server process. It is empty here. Secrets do not go in it, because this file is committed to git (see At work).

# %%
RULES = {
    "claude_desktop_config.json": {"top": "mcpServers", "typed": False, "remote": False},
    ".mcp.json": {"top": "mcpServers", "typed": True, "remote": True},
    ".vscode/mcp.json": {"top": "servers", "typed": True, "remote": True},
    ".cursor/mcp.json": {"top": "mcpServers", "typed": False, "remote": True},
}

def render(rule):
    block = {}
    for name, s in SERVERS.items():
        if s["kind"] == "stdio":
            entry = {"type": "stdio"} if rule["typed"] else {}
            entry.update(command=s["command"], args=s["args"], env={})
        elif rule["remote"]:
            entry = {"type": "http"} if rule["typed"] else {}
            entry.update(url=s["url"])
        else:
            continue   # Claude Desktop: remote servers are added in Settings > Connectors
        block[name] = entry
    return {rule["top"]: block}

for file, rule in RULES.items():
    path = HOSTS_DIR / file
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(render(rule), indent=2) + "\n")
    print(f"wrote {file:<28} top key {rule['top']:<10} entries {len(render(rule)[rule['top']])}")

# %% [markdown]
# ### Where each file goes on a real machine
# Each host reads its file from one place:
#
# | Host | Location | Scope |
# |---|---|---|
# | Claude Desktop | macOS `~/Library/Application Support/Claude/claude_desktop_config.json`; Windows `%APPDATA%\Claude\claude_desktop_config.json` | user; restart fully |
# | Claude Code | `.mcp.json` in the project root; `~/.claude.json` | project; local, user |
# | VS Code | `.vscode/mcp.json` | project; user file via "MCP: Open User Configuration" |
# | Cursor | `.cursor/mcp.json`; `~/.cursor/mcp.json` | project; global |
#
# Claude Code precedence: local, then project, then user. The winning entry is used whole.
#
# To try a file, copy `.mcp.json` into a project folder and open it in Claude Code, which asks you to approve project servers first. Desktop apps are optional.

# %% [markdown]
# ### 3. Check each file the way its host would
# `validate` reads a file's dictionary and raises a `ValueError` with the first problem. It checks the top-level key, the `type` where a host needs one, absolute commands that exist, and the URL shape. Run it on all four files. Each one should say `ok`.

# %%
def validate(doc, rule):
    if rule["top"] not in doc:
        raise ValueError(f"top-level key must be '{rule['top']}', found {sorted(doc)}")
    for name, e in doc[rule["top"]].items():
        if "url" in e:
            if not rule["remote"]:
                raise ValueError(f"{name}: this host does not read url entries from this file")
            if not e["url"].startswith("https://"):
                raise ValueError(f"{name}: url must start with https://")
            if rule["typed"] and e.get("type") != "http":
                raise ValueError(f"{name}: needs \"type\": \"http\"")
        elif "command" in e:
            if not Path(e["command"]).is_absolute() or not Path(e["command"]).exists():
                raise ValueError(f"{name}: command must be an absolute path to a program that exists")
            if rule["typed"] and e.get("type") != "stdio":
                raise ValueError(f"{name}: needs \"type\": \"stdio\"")
        else:
            raise ValueError(f"{name}: needs a command (local server) or a url (remote server)")
    return "ok"

for file, rule in RULES.items():
    doc = json.loads((HOSTS_DIR / file).read_text())   # the file must parse as JSON
    print(f"{file:<28} {validate(doc, rule)}")

# %% [markdown]
# ### 4. One block drives the model
# The adapter from lesson 05 reads an `mcpServers` block. The Claude Code file holds one, so the adapter reads that block. The remote entry needs a live server, which lesson 06 builds, so the adapter gets only the local entries. The names come from the file's own keys.

# %%
import logging, warnings
from contextlib import AsyncExitStack
from langchain_core._api import LangChainBetaWarning
from langchain.mcp import MCPAdapter
warnings.filterwarnings("ignore", category=LangChainBetaWarning)  # the adapter is still beta
logging.getLogger("httpx").setLevel(logging.WARNING)  # hide the model URL line
logging.getLogger("vcr").setLevel(logging.WARNING)
logging.getLogger("google_genai").setLevel(logging.WARNING)
logging.getLogger("fastmcp").setLevel(logging.WARNING)  # set after the import: importing fastmcp resets it
claude_code = json.loads((HOSTS_DIR / ".mcp.json").read_text())["mcpServers"]
stdio_block = {n: e for n, e in claude_code.items() if "command" in e}
stack = AsyncExitStack()   # stays open for the model cells; closed at the end
adapter = await stack.enter_async_context(MCPAdapter({"mcpServers": stdio_block}))
mcp_tools = await adapter.list_tools()
by_name = {t.name: t for t in mcp_tools}
print(sorted(by_name))
assert {"trackr_count_open", "runbooks_get_runbook", "runbooks_search"} <= set(by_name)
sys.path.insert(0, "..")   # so the course helpers (llm_setup, llm_replay) import
import llm_replay
from langchain_core.messages import AIMessage, HumanMessage
QUESTION = HumanMessage("What does the runbook say about issue 7?")
llm = None   # the model cell in step 5 sets this; stays None if that cell is skipped

# %% [markdown]
# ### 5. A real model answers through the host's block (`needs-llm`)
# The question needs the runbooks server. The model asks for a tool, the host runs it through the adapter, and the model writes the answer. Two model calls, the lesson budget.

# %% [markdown]
# The model cell below asks the model for its first reply. `get_llm` picks the model and starts the recording or the replay for this lesson. The line to read is `model asks for`.

# %% tags=["needs-llm"]
from llm_setup import get_llm
llm = get_llm("05a_wiring-servers-into-hosts", max_calls=2)
first = await llm.bind_tools(mcp_tools).ainvoke([QUESTION])
print("model asks for:", [(c["name"], c["args"]) for c in first.tool_calls])

# %% [markdown]
# If the model cell was skipped, a scripted tool call stands in for the model's first reply. The stand-in is labelled.

# %%
if llm is None:   # fallback: the model cell was skipped
    first = AIMessage(content="", tool_calls=[{"name": "runbooks_get_runbook", "args": {"issue_id": 7}, "id": "scripted_1"}])
    print("SCRIPTED stand-in (no model): model asks for:", [(c["name"], c["args"]) for c in first.tool_calls])
else:
    print("model reply used; no stand-in needed")

# %% [markdown]
# The host runs the requested tool through the adapter, which sends the call to the runbooks server.

# %%
results = [await by_name[c["name"]].ainvoke(c) for c in first.tool_calls]
for r in results:
    print("ToolMessage status:", r.status, "| first line:", r.text.splitlines()[0])

# %% [markdown]
# The model reads the runbook and writes its answer. This is its second and last call (`needs-llm`).

# %% tags=["needs-llm"]
final = await llm.bind_tools(mcp_tools).ainvoke([QUESTION, first, *results])
print("answer:", final.text)

# %% [markdown]
# Without a model there is no written answer, so the fallback prints what the tool returned.

# %%
if llm is None:   # fallback: no model, so no written answer
    print("answer (skipped: no model here). The runbook said:", results[0].text.splitlines()[1])

# %% [markdown]
# ## At work
# - Teams keep the project file (`.mcp.json` or `.vscode/mcp.json`) in git so every developer gets the same servers. Hand-edited copies drift within weeks. Companies move servers behind one gateway with one list, which replaces per-laptop config → lesson 40.
# - A config entry is a trust decision: it starts a program on the developer's machine. In an interactive session, Claude Code prompts for approval before it uses project servers from `.mcp.json`. Organisations keep an approved list of servers so a teammate cannot add an unknown one → lesson 41.
# - Config files get committed, so secrets do not belong in them. Production setups refer to a variable or sign in with OAuth, and keep no static token in git → lesson 16.

# %% [markdown]
# ## What just happened
# - One dict made four files. Each file has the top-level key and entry shape its host expects.
# - The validator checked each file. With a wrong key, a host would find no servers in it, and the error would show up only as a missing tool.
# - The adapter read the `mcpServers` block from the Claude Code file, the same block a desktop host reads. The tool names came from that file's keys.
# - The model asked for `runbooks_get_runbook` with `issue_id: 7`. The host ran it and the model answered from the runbook text.

# %% [markdown]
# ## Common mistakes
# Copying the Claude Code file into VS Code without changing the top-level key. VS Code expects `servers`, so it finds no servers in that file. The validator catches it before any editor does:

# %% tags=["raises-exception"]
pasted = {"mcpServers": render(RULES[".mcp.json"])["mcpServers"]}   # Claude Code's file, copied into VS Code
validate(pasted, RULES[".vscode/mcp.json"])   # ValueError: the top-level key must be 'servers'

# %% [markdown]
# Fix: render each host's file from its own rule, as step 2 does. Do not copy files between hosts.

A relative command fails the same way. `../apps/03/trackr_server.py` works in your notebook, but a desktop host starts from another folder. The validator rejects it:

# %% tags=["raises-exception"]
relative = {"mcpServers": {"trackr": {"command": "python", "args": ["../apps/03/trackr_server.py"]}}}
validate(relative, RULES[".mcp.json"])   # ValueError: command must be an absolute path

# %% [markdown]
# Fix: use `sys.executable` and absolute paths, as step 1 does. The validator also rejects a `url` in Claude Desktop's file, because the host ignores it. Add remote servers through Settings > Connectors instead.
#
# Stdio has more traps that no validator catches, such as a `print()` on stdout that breaks the protocol, and a subprocess with a minimal environment. Lesson 05b covers them.

# %% [markdown]
# ## Try it
# Read `../apps/05a/hosts/.mcp.json` and print each server name with its transport: `stdio` if the entry has a `command`, `http` if it has a `url`. No model is needed.

# %%
# your code here

# %% [markdown]
# ## Key terms
# - **host config file** — the JSON file a host reads at startup to learn which servers to start.
# - **top-level key** — the object name that holds the servers: `mcpServers` in three hosts, `servers` in VS Code.
# - **stdio entry** — a `command` and `args` (and `env`) that tell the host to start a local server as a subprocess.
# - **url entry** — a `url` that tells the host where a remote server is.
# - **project scope** — a config file in the repo, shared with the team through git (`.mcp.json`, `.vscode/mcp.json`, `.cursor/mcp.json`).
# - **user scope** — a config file in your home folder, for your own servers in every project.
# - **absolute path** — a full path from the root of the disk. Hosts need one because they start from their own folder.
# - **validator** — a check that catches a wrong key or shape before the host finds no server in the file.

# %% [markdown]
# Close the adapter, which stops the runbooks and Trackr servers. Then tell the recorder the lesson is done.

# %%
await stack.aclose()
llm_replay.stop()
print("lesson 05a done: four host files from one dict, each validated, one block read by the adapter")
