"""Shared LLM setup for lessons that call a model.

Copied into a topic folder when that topic's syllabus uses an LLM.
Notebooks import it with:  sys.path.insert(0, ".."); from llm_setup import get_llm

Every key and setting comes from the topic's .env (see tut_env.py); nothing is typed in a notebook.

Default provider is Gemini on Vertex AI, with either
    GOOGLE_CLOUD_API_KEY=...                      (API key; simplest), or
    GOOGLE_CLOUD_PROJECT=... + GOOGLE_CLOUD_LOCATION=...  (+ GOOGLE_APPLICATION_CREDENTIALS=path
                                                   to a service-account file, or gcloud ADC login)
If both are set, the API key is used. A GOOGLE_API_KEY / GEMINI_API_KEY in your shell (AI Studio)
is ignored here, so it can't sign Vertex calls by accident.

Overrides for learners: TUT_LLM_PROVIDER and TUT_LLM_MODEL apply to the course's default
provider (get_llm() with no provider). While a recording replays, TUT_LLM_PROVIDER is ignored
(the recording was made with the course's provider); the model name doesn't matter for replay.

Lessons that teach a
specific vendor's SDK may ask for another provider:
    get_llm()                     # gemini (default, or TUT_LLM_PROVIDER from .env)
    get_llm("anthropic")          # ANTHROPIC_API_KEY, needs langchain-anthropic
    get_llm("openai")             # OPENAI_API_KEY, needs langchain-openai
    get_llm("ollama")             # a local model via Ollama, no key; needs langchain-ollama

When llm_replay is replaying a recording, no key is needed: a placeholder is used and
every call is answered from the recording.
"""
import os
from contextlib import contextmanager

from tut_env import env, is_set, load

DEFAULT_MODELS = {
    "gemini": "gemini-2.5-flash-lite",
    "anthropic": "claude-haiku-4-5-20251001",
    "openai": "gpt-4.1-mini",
    "ollama": "qwen2.5:7b",
}


def _replaying() -> bool:
    try:
        import llm_replay
        return llm_replay.is_replaying()
    except ImportError:
        return False


def _key(env_var: str) -> str:
    if _replaying() and not is_set(env_var):
        return "replay-no-key-needed"
    return env(env_var)  # clear error telling the learner to add it to .env


@contextmanager
def _hidden(*names: str):
    """Hide env vars while a client is created (google-genai lets a project override an API key)."""
    saved = {n: os.environ.pop(n) for n in names if n in os.environ}
    try:
        yield
    finally:
        os.environ.update(saved)


def get_llm(provider: str | None = None, model: str | None = None, **kwargs):
    load()  # reads the topic's .env (keys, project, region, model overrides)
    from_default = provider is None
    if from_default:
        provider = "gemini" if _replaying() else env("TUT_LLM_PROVIDER", "gemini")
    provider = provider.lower()
    if provider not in DEFAULT_MODELS:
        raise ValueError(f"Unknown provider '{provider}'. Use gemini, anthropic, openai or ollama.")
    model = model or (env("TUT_LLM_MODEL", DEFAULT_MODELS[provider]) if from_default else DEFAULT_MODELS[provider])
    settings = {"temperature": 0, **kwargs}

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        tokens = settings.pop("max_output_tokens", 1024)
        if is_set("GOOGLE_CLOUD_API_KEY") or _replaying() or not is_set("GOOGLE_CLOUD_PROJECT"):
            api_key = _key("GOOGLE_CLOUD_API_KEY")
            print("Gemini on Vertex AI · API key loaded:", bool(api_key))
            with _hidden("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION", "GOOGLE_API_KEY", "GEMINI_API_KEY"):
                return ChatGoogleGenerativeAI(model=model, vertexai=True, api_key=api_key,
                                              max_output_tokens=tokens, **settings)
        print("Gemini on Vertex AI · project and location from .env")
        with _hidden("GOOGLE_API_KEY", "GEMINI_API_KEY"):
            return ChatGoogleGenerativeAI(model=model, vertexai=True, project=env("GOOGLE_CLOUD_PROJECT"),
                                          location=env("GOOGLE_CLOUD_LOCATION", "global"),
                                          max_output_tokens=tokens, **settings)
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model, api_key=_key("ANTHROPIC_API_KEY"),
                             max_tokens=settings.pop("max_tokens", 1024), **settings)
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=model, api_key=_key("OPENAI_API_KEY"), **settings)
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(model=model, base_url=env("OLLAMA_BASE_URL", "http://localhost:11434"), **settings)
    raise ValueError(f"Unknown provider '{provider}'. Use gemini, anthropic, openai or ollama.")


if __name__ == "__main__":
    print(get_llm().invoke("Say hello in one short sentence.").text)  # quick connection test
