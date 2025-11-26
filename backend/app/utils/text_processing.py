def normalize_whitespace(text: str) -> str:
    """Compress consecutive whitespace."""
    return " ".join(text.split())

