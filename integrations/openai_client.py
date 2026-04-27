import os

from dotenv import load_dotenv
from openai import AzureOpenAI


load_dotenv()


def get_openai_client() -> AzureOpenAI:
    """Initialises the Azure OpenAI client from environment variables."""
    return AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-05-01-preview"),
    )


def get_openai_deployment() -> str:
    """Returns the configured Azure OpenAI deployment name."""
    return os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-mini")
