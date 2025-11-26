class LLMService:
    """Simple wrapper for LLM endpoints (e.g., Ollama)."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url

    def summarize(self, text: str) -> str:
        """Placeholder summarization call."""
        return f"Summary for: {text[:20]}..."

