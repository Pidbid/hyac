import uuid
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class LspSession:
    session_id: str
    app_id: str
    mode: str
    created_at: datetime


class LspSessionManager:
    def __init__(self):
        self._sessions: dict[str, LspSession] = {}

    def create(self, app_id: str, mode: str) -> LspSession:
        session = LspSession(
            session_id=str(uuid.uuid4()),
            app_id=app_id,
            mode=mode,
            created_at=datetime.now(timezone.utc),
        )
        self._sessions[session.session_id] = session
        return session

    def remove(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def size(self) -> int:
        return len(self._sessions)
