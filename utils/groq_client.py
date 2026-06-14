# utils/groq_client.py
"""
Shared Groq client initialization. Centralizes API key loading and client
setup so tools.py and agent.py don't each define their own version.
"""
import os

from dotenv import load_dotenv
from groq import Groq

load_dotenv()


def get_groq_client() -> Groq:
    """
    Initialize and return a Groq client using GROQ_API_KEY from .env.
    Raises ValueError if the key is not set.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)