"""Model access for this course: pick any provider and model, get a standard LangChain chat model.

In a lesson (first code cell):

    import sys; sys.path.insert(0, "..")
    from llm_setup import get_llm
    llm = get_llm("12_browser_agent_loop")       # the notebook's file name without .ipynb

get_llm() prints every provider and model, whether its key is set and whether this lesson has a
recording for it, starts llm_replay for the chosen model (one recording per model), and returns
the model from LangChain's init_chat_model(). Everything after that is plain LangChain:
llm.invoke(...), llm.bind_tools(...), AIMessage.tool_calls, ToolMessage.

Choose the model in .env (TUT_LLM_PROVIDER / TUT_LLM_MODEL; TUT_CU_PROVIDER / TUT_CU_MODEL for
computer-use lessons) or in the cell:
    llm = get_llm("12_browser_agent_loop", provider="anthropic", model="claude-sonnet-5-5")

A model with no recording for the lesson and no key stops with an error naming the key to add.
Low cost: each example makes at most 2 model calls, and a lesson stops if it goes over its call
budget (max_calls, default 4); replaying a recording makes no calls at all.
Run `python llm_setup.py` to see which providers can make real calls on this machine.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Model ids from RESEARCH.md section 1.3 (checked 2026-10-11). The first one is the default.
CATALOG = {
    "gemini": {"key": "GOOGLE_CLOUD_API_KEY",
               "models": ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-3.8-flash"],
               "computer_use": ["gemini-3.8-flash", "gemini-3.5-flash-lite"]},
    "anthropic": {"key": "ANTHROPIC_API_KEY",
                  "models": ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-1"],
                  "computer_use": ["claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5", "claude-fable-5-1"]},
    "openai": {"key": "OPENAI_API_KEY",
               "models": ["gpt-6-luna", "gpt-6.1-sol", "gpt-6-astra"],
               "computer_use": ["gpt-6.1-sol", "gpt-6-luna", "gpt-6-astra"]},
    "ollama": {"key": None, "models": ["qwen2.5:7b"], "computer_use": []},
}
ROLE_ENV = {"agent": ("TUT_LLM_PROVIDER", "TUT_LLM_MODEL"), "computer_use": ("TUT_CU_PROVIDER", "TUT_CU_MODEL")}
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")


def _load_env() -> None:
    load_dotenv(Path.cwd().parent / ".env")
    load_dotenv()  # a .env in the current folder, if any


def _ollama_running() -> bool:
    import httpx
    try:
        return httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=1).status_code == 200
    except httpx.HTTPError:
        return False


def key_status() -> dict:
    """provider -> True if it can make real calls here (key set, or Ollama running)."""
    _load_env()
    return {p: bool(os.environ.get(c["key"])) if c["key"] else _ollama_running() for p, c in CATALOG.items()}


def show_models(lesson=None, role="agent", chosen=None) -> None:
    """Print every provider and model, with key status and (for a lesson) which are recorded."""
    import llm_replay
    status = key_status()
    recorded = set(llm_replay.recorded_models(lesson)) if lesson else set()
    print(f"{'provider':10} {'key / server':34} model")
    for p, c in CATALOG.items():
        how = (f"{c['key']} {'set' if status[p] else 'not set'}" if c["key"]
               else f"Ollama {'running' if status[p] else 'not running'}")
        for i, m in enumerate(c["computer_use" if role == "computer_use" else "models"] or ["(none for computer use)"]):
            tags = (["recorded"] if f"{p}:{m}" in recorded else []) + (["<- chosen"] if f"{p}:{m}" == chosen else [])
            left = f"{p:10} {'✓' if status[p] else '✗'} {how:32}" if i == 0 else " " * 45
            print(f"{left} {m}  {' '.join(tags)}")


def get_llm(lesson=None, provider=None, model=None, role="agent", max_calls=None, **kwargs):
    """Pick the model (argument > .env > course default), show the options, start recording or
    replay for `lesson`, and return a LangChain chat model."""
    from langchain.chat_models import init_chat_model

    import llm_replay
    _load_env()
    p_env, m_env = ROLE_ENV[role]
    provider = (provider or os.environ.get(p_env) or os.environ.get("TUT_LLM_PROVIDER") or "gemini").lower()
    if provider not in CATALOG:
        raise ValueError(f"Unknown provider '{provider}'. Choose one of: {', '.join(CATALOG)}")
    env_model = os.environ.get(m_env) or os.environ.get("TUT_LLM_MODEL")
    if any(env_model in c["models"] for p, c in CATALOG.items() if p != provider):
        env_model = None  # .env names another provider's model: use this provider's default
    choices = CATALOG[provider]["computer_use" if role == "computer_use" else "models"]
    model = model or env_model or (choices[0] if choices else None)
    if model is None:
        raise ValueError(f"{provider} has no computer-use model in this course.")
    full = f"{provider}:{model}"
    show_models(lesson, role, chosen=full)
    if lesson:
        llm_replay.start(lesson, model=full, key_env=CATALOG[provider]["key"], max_calls=max_calls)
    print(f"Using {full}")

    key_env = CATALOG[provider]["key"]
    key = (os.environ.get(key_env) or "replay-no-key-needed") if key_env else None  # replay never sends it
    if provider == "gemini":
        return init_chat_model(model, model_provider="google_genai", vertexai=True, api_key=key,
                               temperature=kwargs.pop("temperature", 0), **kwargs)
    if provider == "anthropic":
        # No temperature: current Claude models reject non-default sampling settings (RESEARCH 1.3).
        return init_chat_model(model, model_provider="anthropic", api_key=key,
                               max_tokens=kwargs.pop("max_tokens", 1024), **kwargs)
    if provider == "openai":
        return init_chat_model(model, model_provider="openai", api_key=key, **kwargs)
    return init_chat_model(model, model_provider="ollama", base_url=OLLAMA_HOST,
                           temperature=kwargs.pop("temperature", 0), **kwargs)


if __name__ == "__main__":
    show_models()
