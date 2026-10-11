"""Scout's tools, trimmed from lesson 35: note search and a safe calculator (no eval)."""
import ast, operator

NOTES = [
    {"id": 1, "text": "Mars has two small moons, Phobos and Deimos."},
    {"id": 2, "text": "Venus spins backwards compared with most planets."},
    {"id": 3, "text": "A day on Mars lasts about 24 hours and 39 minutes."},
    {"id": 4, "text": "Jupiter is the largest planet in the solar system."},
    {"id": 5, "text": "The rover Perseverance landed on Mars in February 2021."},
    {"id": 6, "text": "Saturn's rings are mostly made of ice."},
]

def search_notes(query: str) -> list[dict]:
    """Search the user's notes for a word or phrase (case-insensitive)."""
    q = query.strip().lower()
    if not q:
        raise ValueError("query must not be empty, e.g. query='Mars'")
    return [n for n in NOTES if q in n["text"].lower()]

OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
       ast.Div: operator.truediv, ast.Mod: operator.mod, ast.Pow: operator.pow}
HOW = "use numbers, + - * / % ** and brackets, e.g. '24*60+39'"

def evaluate(node):
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -evaluate(node.operand)
    if isinstance(node, ast.BinOp) and type(node.op) in OPS:
        left, right = evaluate(node.left), evaluate(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError(f"exponent {right} is too large (max 100)")
        return OPS[type(node.op)](left, right)
    raise ValueError(f"'{ast.unparse(node)[:40]}' is not plain arithmetic: {HOW}")

def calculator(expression: str) -> float:
    """Evaluate an arithmetic expression: numbers, + - * / % ** and brackets."""
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        raise ValueError(f"'{expression}' is not valid arithmetic: {HOW}") from None
    return evaluate(tree.body)

TOOLS = {"search_notes": search_notes, "calculator": calculator}
SCHEMAS = [{"name": name, "description": fn.__doc__} for name, fn in TOOLS.items()]  # short form
