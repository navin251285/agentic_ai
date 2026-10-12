# %% [markdown]
# # 21 · AGENTS.md and Agent Skills
# Level L3 · Part 4 · professional · ~30 min · builds on 05

# %% [markdown]
# ## Goal
# By the end you have an `AGENTS.md` for Trackr and a `triage-runbook` skill that `skills-ref` accepts. A real model answers a question about a late push notification twice: once with only the always-on rules (1 call), and once with the skill, where it asks for the runbook first and then answers (2 calls).

# %% [markdown]
# ## Why it matters
# Without these files, a team has two bad options. It can paste every rule into the system prompt, so every call pays for rules that most questions never use. Or the rule is missing, and the model guesses. Here is the cost of the first option with example numbers:

# %%
runbooks, chars_each = 30, 4_000   # example size: 30 team runbooks of 4,000 characters each
print("pasted into every call:", runbooks * chars_each, "characters")
print("needed for one issue:  ", chars_each, "characters")

# %% [markdown]
# `AGENTS.md` holds the rules that apply to every task in a folder, and the closest file wins. A skill holds a procedure for one kind of task. The model sees a one-line summary of each skill, and it loads the full text only when a task needs it. A rule that applies to every task belongs in `AGENTS.md`, not in a skill. A question that needs no team rule needs neither.

# %% [markdown]
# ## The idea
# - **AGENTS.md** is a plain Markdown file of project rules that a coding agent reads before it works. Where several files exist, the one closest to the code is used.
# - **An Agent Skill** is a folder with a `SKILL.md` file. Its frontmatter (`name`, `description`) is always visible. The body, and any `scripts/`, `references/` or `assets/` files, load only when a task needs them. That order is *progressive disclosure*.
# - **Skills over MCP** is the same folder served by an MCP server, so a host can discover skills from the server and read their files with `resources/read`.
#
# Analogy: `AGENTS.md` is the house rules on the fridge. A skill is the recipe binder on the shelf. The fridge says the binder has a recipe for each dish. You open the binder only when you cook that dish.

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart TD
#   A[AGENTS.md: nearest file wins] --> P[System prompt: always-on rules]
#   K[skills/triage-runbook: name + description] -->|catalogue line only| P
#   P --> M[Model]
#   M -->|asks: load_skill triage-runbook| H[Host reads the SKILL.md body]
#   H --> M
#   M --> R[Answer]
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. Write the Trackr rules and a nested AGENTS.md
# The Trackr project lives in `../data/21/trackr`. The root `AGENTS.md` holds the team rules. The mobile service has its own file, which replaces the root file for code under `services/mobile`.

# %%
from pathlib import Path
ROOT = Path("../data/21/trackr")
Path(ROOT / "services/mobile").mkdir(parents=True, exist_ok=True)
Path(ROOT / "services/web").mkdir(parents=True, exist_ok=True)
print("project folder ready:", ROOT.resolve().name)

# %% [markdown]
# The root file holds the team rules for the whole project. Write it first.

# %%
%%writefile ../data/21/trackr/AGENTS.md
# Trackr: rules for coding agents
- Run the tests before you propose a change.
- Never close an issue without a reason in the comment.
- Use only issue ids that exist in Trackr.

# %% [markdown]
# The mobile service keeps its own rules in its own folder. Its file is written next.

# %%
%%writefile ../data/21/trackr/services/mobile/AGENTS.md
# Mobile service rules
- Reproduce mobile bugs on the Android 14 test device first.
- Ship hotfixes behind a feature flag.
- Put the issue id in every commit message.

# %% [markdown]
# ### 2. Pick the nearest AGENTS.md
# A host does not read every `AGENTS.md` in the repo. It starts at the file being edited and walks up. The first `AGENTS.md` it finds is the one it uses. Walking stops at the project root.

# %%
def nearest_agents_md(file: Path) -> Path | None:
    """Walk up from the file's folder; the first AGENTS.md found wins."""
    root = ROOT.resolve()
    for folder in file.resolve().parents:
        if (folder / "AGENTS.md").exists():
            return folder / "AGENTS.md"
        if folder == root:
            break
    return None

for edited in [ROOT / "services/mobile/push.py", ROOT / "services/web/app.py"]:
    found = nearest_agents_md(edited).relative_to(ROOT.resolve())
    print(f"{edited.relative_to(ROOT)} -> {found}")

SYSTEM = nearest_agents_md(ROOT / "services/mobile/push.py").read_text(encoding="utf-8")

# %% [markdown]
# The mobile file won for the push code. The web file has no nested rules, so the root file applies. The mobile file does not add to the root rules. It replaces them for that folder, which is why a team copies any rule it still needs into its own file.

# %% [markdown]
# ### 3. Write the triage-runbook skill
# A skill is a folder whose name matches the `name` field. Its body is the team runbook for one kind of task: a push delay. The frontmatter is what the model sees at all times.

# %%
Path(ROOT / "skills/triage-runbook").mkdir(parents=True, exist_ok=True)
SKILLS_DIR = (ROOT / "skills").resolve()
SKILL_DIR = SKILLS_DIR / "triage-runbook"
print("skill folder:", SKILL_DIR.relative_to(ROOT.resolve()))

# %% [markdown]
# The frontmatter and the body are one file. The cell below writes `SKILL.md` into the skill folder.

# %%
%%writefile ../data/21/trackr/skills/triage-runbook/SKILL.md
---
name: triage-runbook
description: Triage a Trackr issue with the team runbook. Use when someone asks what to do about an issue, how urgent it is, or whether to page the on-call.
metadata:
  owner: ops-desk
  version: "1.0"
---

# Triage runbook

1. Read the issue title and severity in Trackr.
2. Find the symptom in the table and take its first steps.
3. Page the on-call only when the table says so. Say which rule you used.
4. Never close the issue in this step.

| Symptom | First steps | Page when |
|---|---|---|
| Push notifications arrive late | Check the push queue depth. Ask the device owner to re-register the push token. | More than 15 minutes late for 3 or more users: page the mobile on-call. |
| TLS certificate expires within 14 days | Renew with the infra CA. Check the chain on the edge. | Expires within 3 days: page the infra on-call. |

# %% [markdown]
# ### 4. Read the catalogue line and the body
# `skills_ref.read_properties` parses the frontmatter. The catalogue line the model always sees is the name and the description. The body is the rest of the file. Compare the two sizes.

# %%
from skills_ref import read_properties, validate
props = read_properties(SKILL_DIR)
body = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8").split("---", 2)[2]
catalogue_line = f"{props.name}: {props.description}"
print("catalogue line:", len(catalogue_line), "characters")
print("full body:     ", len(body), "characters")

# %% [markdown]
# ### 5. Validate the skill with skills-ref
# `validate` returns a list of problems. An empty list means the skill is valid. A copy with an upper-case name shows the check that fails.

# %%
print("trackr skill:", validate(SKILL_DIR) or "valid")
bad = Path("../data/21/bad-skills/Triage-Runbook")
bad.mkdir(parents=True, exist_ok=True)
(bad / "SKILL.md").write_text((SKILL_DIR / "SKILL.md").read_text(encoding="utf-8").replace("name: triage-runbook", "name: Triage-Runbook"), encoding="utf-8")
print("bad copy:", validate(bad))

# %% [markdown]
# ### 6. Serve the same skill over MCP
# A server that publishes skills puts each `SKILL.md` at a `skill://` URI and reads it with `resources/read`. The in-process server below does that. The host then checks what it read: the SHA-256 digest and byte size must match the bytes on disk. The Skills extension manifest lists exactly these values. This lesson builds the listing entry by hand, because the `mcp` 2.3 SDK has no `skills/list` handler yet.

# %%
import hashlib, json
from mcp import Client
from mcp.server import MCPServer
skills_mcp = MCPServer("Trackr skills")

@skills_mcp.resource("skill://triage-runbook/SKILL.md", title="triage-runbook", mime_type="text/markdown")
def triage_runbook_skill() -> str:
    return (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

async with Client(skills_mcp) as skills_client:
    listed = await skills_client.list_resources()
    print("resources:", [r.uri for r in listed.resources])
    got = await skills_client.read_resource("skill://triage-runbook/SKILL.md")
    served = got.contents[0].text.encode("utf-8")

on_disk = (SKILL_DIR / "SKILL.md").read_bytes()
entry = {"uri": "skill://triage-runbook/SKILL.md",
         "frontmatter": {"name": props.name, "description": props.description},
         "resources": [{"uri": "skill://triage-runbook/SKILL.md",
                        "digest": "sha256:" + hashlib.sha256(served).hexdigest(), "size": len(served)}]}
print("digest and size match the file on disk:", served == on_disk, entry["resources"][0]["size"])
print(json.dumps(entry, indent=2)[:400])

# %% [markdown]
# ### 7. The model without the skill (`needs-llm`, call 1 of 3)
# The model gets the always-on rules and the question. Nothing else. It has no way to know the team's push rule.

# %%
import sys
sys.path.insert(0, "..")   # so llm_setup and llm_replay import
import llm_replay
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
QUESTION = "Issue 7, 'Push notifications arrive late', has been 20 minutes late for 4 users. What do I do now?"
llm = None   # filled by the model cell; stays None if that cell is skipped
print("question ready; the model cells below need a model (or are skipped)")

# %% [markdown]
# The first model cell. `get_llm` records the call the first time and replays it after that.

# %% tags=["needs-llm"]
import logging
for noisy in ["httpx", "google_genai", "vcr"]:   # their INFO lines print the model URL and project id
    logging.getLogger(noisy).setLevel(logging.WARNING)
from llm_setup import get_llm
llm = get_llm("21_agents-md-and-skills", max_calls=3)
plain = await llm.ainvoke([SystemMessage(SYSTEM), HumanMessage(QUESTION)])
print("without the skill:", plain.text)

# %% [markdown]
# ### 8. The skill is loaded only on request (`needs-llm`, call 2 of 3)
# Now the system prompt also has the catalogue line, not the body. A tool named `load_skill` returns the body. The model asks for it, and the host runs the tool. The body is not in the prompt yet.

# %%
@tool
def load_skill(name: str) -> str:
    """Load the full instructions of a skill from the catalogue. Pass the exact skill name."""
    try:
        return (SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
    except FileNotFoundError:
        # report the path relative to the project, not the absolute folder on this machine
        raise FileNotFoundError(f"skills/{name}/SKILL.md (no such skill in the catalogue)") from None

CATALOGUE = f"Skills you can load (name: description):\n- {props.name}: {props.description}\nCall load_skill with the exact name before you follow a skill."
WITH_SKILL = SYSTEM + "\n\n" + CATALOGUE
print("load_skill ready:", load_skill.name, "| catalogue lines in prompt:", CATALOGUE.count("\n- "))

# %% [markdown]
# The catalogue line goes into the prompt, the body does not. The model now returns a tool call instead of an answer.

# %% tags=["needs-llm"]
asks = await llm.bind_tools([load_skill]).ainvoke([SystemMessage(WITH_SKILL), HumanMessage(QUESTION)])
print("model asks for:", [(c["name"], c["args"]) for c in asks.tool_calls])

# %% [markdown]
# ### 9. The host runs the tool and the model answers (`needs-llm`, call 3 of 3)
# The host runs each requested tool and sends the body back as a tool message. The model then writes its answer from the body.

# %% tags=["needs-llm"]
results = [await load_skill.ainvoke(c) for c in asks.tool_calls]
answer = await llm.bind_tools([load_skill]).ainvoke([SystemMessage(WITH_SKILL), HumanMessage(QUESTION), asks, *results])
print("with the skill:", answer.text)

# %% [markdown]
# Compare the two answers. The first one never mentions paging or the 15-minute, 3-user threshold, because the model had no way to know the team rule. The second one quotes the runbook: it applies the push row, the 15-minute, 3-user threshold, and it names the mobile on-call to page. The cost was 2 model calls instead of 1, plus the 632-character body, which entered the prompt only when the model asked for it.

# %% [markdown]
# Without a model, the cell below still shows what the host would send: the body that `load_skill` returns for the same name.

# %%
if llm is None:   # fallback: no model here, so only the tool side runs
    body_text = load_skill.invoke({"name": "triage-runbook"})
    push_row = [line for line in body_text.splitlines() if "Push notifications" in line][0]
    print("no model here. The host would send this body on request. Its push row:", push_row)

# %% [markdown]
# ## At work
# - Monorepos keep one `AGENTS.md` per service, and the closest one wins. A stale root file then hides a team's rule without any error. Teams check these files in CI, the way they test code → lesson 27.
# - Every skill name and description is in context on every call. Large catalogues cost tokens on each request, so teams keep descriptions short and bodies on demand → lesson 24.
# - A skill is text the model obeys. A skill from another team, or from a shared server, can carry instructions that do harm. Hosts ask the user before they load a skill, and they check digests before they use it → lesson 29.

# %% [markdown]
# ## What just happened
# - The host chose the nearest `AGENTS.md` for the file it edits. The mobile file replaced the root file for that folder.
# - `skills-ref` checked the frontmatter and the folder name. The bad copy failed on its upper-case name.
# - The same bytes came back over `resources/read` as from disk, so the digest matched.
# - The model saw the catalogue line first. It asked for the body, and only then did it have the team's push rule.
- The comparison cost 2 model calls with the skill instead of 1 without it. The 632-character body entered the prompt only when the model asked for it.

# %% [markdown]
# ## Common mistakes
# Asking for a skill by a name that is not in the catalogue. The catalogue says `triage-runbook`. `triage_runbook` with an underscore is another folder, so the tool fails:

# %% tags=["raises-exception"]
load_skill.invoke({"name": "triage_runbook"})

# %% [markdown]
# Fix: pass the exact `name` from the catalogue line. The validator would also have caught a name that does not match its folder.

# %% [markdown]
# ## Try it
# Copy the `triage-runbook` folder to `triage-runbook-copy` without changing the `name` line. Run `validate` on the copy and print the result. Then fix the name so it matches the folder, and validate again. No model is needed.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
import shutil
copy = SKILLS_DIR / "triage-runbook-copy"
shutil.copytree(SKILL_DIR, copy, dirs_exist_ok=True)
print("before:", validate(copy))
text = (copy / "SKILL.md").read_text(encoding="utf-8").replace("name: triage-runbook", "name: triage-runbook-copy", 1)
(copy / "SKILL.md").write_text(text, encoding="utf-8")
print("after:", validate(copy))

# %% [markdown]
# ## Key terms
# - **AGENTS.md** — a Markdown file of project rules for coding agents. The closest file to the code wins.
# - **Agent Skill** — a folder with a `SKILL.md` file whose frontmatter is always visible and whose body loads on request.
# - **SKILL.md frontmatter** — the YAML block at the top of `SKILL.md`. `name` and `description` are required.
# - **progressive disclosure** — loading metadata first, the body when a task needs it, and other files only when they are used.
# - **skill catalogue** — the list of name and description lines the model sees on every call.
# - **Skills over MCP** — the MCP Skills extension (`io.modelcontextprotocol/skills`). A server lists skills with `skills/list`, and the files are read with `resources/read`.
# - **skills-ref** — the reference library and `skills-ref validate` command that check a skill folder against the spec.

# %% [markdown]
# Close the recorder, which saves the recording if this run recorded.

# %%
llm_replay.stop()
print("lesson 21 done: AGENTS.md picks the rules, the skill loads on request, the same skill is served over MCP")
