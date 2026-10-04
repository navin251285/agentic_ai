"""The only shared code in the tutorial: get_llm() returns a Gemini chat model on Vertex AI.

Only the [LLM] lessons (00's optional test, 19 and 20) call it. Every other lesson runs offline without a key.
"""

import os
from dotenv import load_dotenv


def get_llm():
    load_dotenv()  # reads GOOGLE_CLOUD_API_KEY from a .env file in this directory, if present

    assert os.environ.get("GOOGLE_CLOUD_API_KEY"), (
        "GOOGLE_CLOUD_API_KEY is not set. Create a .env file in this folder with:\n"
        "  GOOGLE_CLOUD_API_KEY=your-key-here\n"
        "or export it in your shell before launching Jupyter. See README.md."
    )
    print("API key loaded:", bool(os.environ.get("GOOGLE_CLOUD_API_KEY")))

    from langchain_google_genai import ChatGoogleGenerativeAI

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash-lite",
        vertexai=True,
        api_key=os.environ.get("GOOGLE_CLOUD_API_KEY"),
        max_output_tokens=1024,
        temperature=0,
    )
    return llm
