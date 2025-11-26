from pydantic import BaseModel


class FilePayload(BaseModel):
    file_path: str

    @classmethod
    def validate_path(cls, file_path: str) -> bool:
        """Placeholder path validator."""
        return bool(file_path)

