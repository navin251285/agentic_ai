"""Scout's tools over one user's notes and one folder (lessons 29, 35, 46)."""
import ast, json, operator
from pathlib import Path

NOTES = [
    {"id": 1, "text": "Mars has two small moons, Phobos and Deimos."},
    {"id": 2, "text": "Venus spins backwards compared with most planets."},
    {"id": 3, "text": "A day on Mars lasts about 24 hours and 39 minutes."},
    {"id": 4, "text": "Jupiter is the largest planet in the solar system."},
    {"id": 5, "text": "The rover Perseverance landed on Mars in February 2021."},
    {"id": 6, "text": "Saturn's rings are mostly made of ice."},
]
OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
HOW = "use numbers, + - * / and brackets, e.g. '24*60+39'"

def evaluate(node):
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -evaluate(node.operand)
    if isinstance(node, ast.BinOp) and type(node.op) in OPS:
        return OPS[type(node.op)](evaluate(node.left), evaluate(node.right))
    raise ValueError(f"'{ast.unparse(node)[:40]}' is not plain arithmetic: {HOW}")

def calculator(expression: str) -> float:
    try:
        return evaluate(ast.parse(expression, mode="eval").body)
    except SyntaxError:
        raise ValueError(f"'{expression}' is not valid arithmetic: {HOW}") from None

def make_tools(notes: list[dict], folder: Path) -> dict:
    """One user's tools: search their notes, calculate, write new files in their folder only."""
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)

    def search_notes(query: str) -> list[dict]:
        q = query.strip().lower()
        if not q:
            raise ValueError("query must not be empty, e.g. query='Mars'")
        return [n for n in notes if q in n["text"].lower()][:5]

    def write_file(filename: str, text: str, overwrite: bool = False) -> str:
        target = (folder / filename).resolve()
        if target.parent != folder:
            raise ValueError(f"'{filename}' is outside Scout's folder. Use a plain file name.")
        if target.exists() and not overwrite:
            raise FileExistsError(f"'{filename}' already exists. Pick a new name.")
        target.write_text(text)
        return f"saved {len(text)} characters to {target.name}"

    return {"search_notes": search_notes, "calculator": calculator, "write_file": write_file}

def _schema(name, description, **params):
    return {"name": name, "description": description, "parameters": {"type": "object",
            "required": [p for p in params if p != "overwrite"],
            "properties": {p: {"type": t} for p, t in params.items()}}}

SCHEMAS = [
    _schema("search_notes", "Search the user's notes for a word or phrase (case-insensitive). "
            "Returns up to 5 notes as {id, text}.", query="string"),
    _schema("calculator", f"Evaluate arithmetic: {HOW}.", expression="string"),
    _schema("write_file", "Save text to a new file in Scout's folder.",
            filename="string", text="string", overwrite="boolean"),
]

def run_tool(call: dict, tools: dict) -> dict:
    """Run one call. Returns {"content": str, "is_error": bool}; never raises (lesson 28)."""
    fn = tools.get(call["name"])
    if fn is None:
        return {"content": f"unknown tool '{call['name']}'. Available: {', '.join(tools)}.", "is_error": True}
    try:
        return {"content": json.dumps(fn(**call["args"])), "is_error": False}
    except Exception as e:
        return {"content": f"{type(e).__name__}: {e}", "is_error": True}

# ---- Scout v3 (lesson 60): a new tool, added outside the loop. The loop does not change. ----
from datetime import date

def days_between(start: str, end: str) -> int:
    """Days from start to end (negative if end is earlier)."""
    try:
        return (date.fromisoformat(end) - date.fromisoformat(start)).days
    except ValueError:
        raise ValueError(f"dates must be YYYY-MM-DD, e.g. start='2021-02-18'; got start={start!r}, "
                         f"end={end!r}. Retry with full dates.") from None

_make_v2_tools = make_tools

def make_tools(notes: list[dict], folder: Path) -> dict:
    """One user's tools: v2's tools, plus days_between."""
    return {**_make_v2_tools(notes, folder), "days_between": days_between}

SCHEMAS.append(_schema("days_between", "Count the days from one date to another. Dates as YYYY-MM-DD.",
                       start="string", end="string"))
