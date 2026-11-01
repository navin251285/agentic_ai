"""Draw LangGraph graphs and flowcharts in a notebook: a picture when the drawing service is reachable, the same
diagram as Mermaid text when it is not.

Used by the LangGraph version of the course (notebooks/langraph_version/). Blue nodes run code, amber nodes call a model.

    from graph_view import show_graph, show_mermaid
    show_graph(app, model_nodes=("agent",))     # a compiled LangGraph app
    show_mermaid(MERMAID_TEXT)                  # a hand-written flowchart
"""
from IPython.display import HTML, Image, display
from langchain_core.runnables.graph import NodeStyles
from langchain_core.runnables.graph_mermaid import draw_mermaid_png

MODEL_STYLE = "classDef model fill:#fde68a,stroke:#b45309"  # amber: a node that calls the model


def show_graph(app, model_nodes=()):
    """Draw the compiled graph. The picture comes from the public Mermaid service (mermaid.ink), so it needs internet."""
    text = app.get_graph().draw_mermaid(node_colors=NodeStyles(
        default="fill:#e0f2fe,stroke:#0369a1", first="fill:#f1f5f9", last="fill:#dcfce7"))
    text += f"\n{MODEL_STYLE}\n" + (f"class {','.join(model_nodes)} model\n" if model_nodes else "")
    show_mermaid(text)


def show_mermaid(text):
    """Draw Mermaid text as a picture, or print it when the picture cannot be drawn (offline)."""
    try:
        display(Image(draw_mermaid_png(text)))
    except Exception as e:  # offline, or the service is down: the same diagram as text
        print(f"No picture ({type(e).__name__}). The same flowchart as Mermaid text:\n{text}")


def track_banner(kicker, title, text, start="#1e3a8a", end="#7c3aed"):
    """A title band for a track page: a small label, the track name and one paragraph."""
    display(HTML(
        f'<div style="background:linear-gradient(135deg,{start},{end});color:#fff;padding:28px 32px;'
        f'border-radius:14px;font-family:system-ui,sans-serif;margin-bottom:8px">'
        f'<div style="font-size:12px;letter-spacing:.14em;opacity:.8;text-transform:uppercase">{kicker}</div>'
        f'<div style="font-size:30px;font-weight:700;margin:6px 0 4px">{title}</div>'
        f'<div style="font-size:16px;opacity:.92;max-width:760px;line-height:1.5">{text}</div></div>'))


def lesson_cards(rows, accent="#7c3aed"):
    """One card per lesson. rows: (number, title, one line about what the lesson does)."""
    cards = "".join(
        f'<div style="background:#fff;border:1px solid #e2e8f0;border-left:4px solid {accent};border-radius:10px;'
        f'padding:14px 16px;font-family:system-ui,sans-serif;box-shadow:0 1px 2px rgba(0,0,0,.05)">'
        f'<div style="font-size:12px;color:#64748b;letter-spacing:.06em">LESSON {n}</div>'
        f'<div style="font-weight:650;color:#0f172a;margin:2px 0 4px">{title}</div>'
        f'<div style="font-size:13px;color:#475569;line-height:1.45">{text}</div></div>'
        for n, title, text in rows)
    display(HTML(f'<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));'
                 f'gap:12px;margin:8px 0">{cards}</div>'))
