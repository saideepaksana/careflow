import secrets

from careflow.config import SESSION_TOKEN_BYTES


class SessionStore:
    """Demo login sessions held in memory; a server restart signs everyone out."""

    def __init__(self) -> None:
        self.patients_by_token: dict[str, str] = {}

    def create(self, patient_id: str) -> str:
        token = secrets.token_urlsafe(SESSION_TOKEN_BYTES)
        self.patients_by_token[token] = patient_id
        return token

    def patient_for(self, token: str) -> str | None:
        return self.patients_by_token.get(token)
