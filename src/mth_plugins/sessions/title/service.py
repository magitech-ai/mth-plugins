"""SessionTitleService managing automatic fallback and LLM titling."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, ClassVar

from anima import Context, Service

from mth_plugins.sessions.title.titler import (
    SessionTitleState,
    clean_llm_title,
    extract_fallback_title,
)

logger = logging.getLogger(__name__)


class SessionTitleService(Service):
    """Service providing automatic fallback and background LLM title generation."""

    inject: ClassVar[list[str]] = ["sessions"]

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx, "session_title")
        self._states: dict[str, SessionTitleState] = {}
        self._background_tasks: set[asyncio.Task[Any]] = set()

    def get_title(self, session_id: str) -> str | None:
        """Returns the current title for a session, if established."""
        state = self._states.get(session_id)
        return state.title if state else None

    def get_state(self, session_id: str) -> SessionTitleState:
        """Returns or creates the titling state for a session."""
        if session_id not in self._states:
            self._states[session_id] = SessionTitleState()
        return self._states[session_id]

    def set_title(
        self,
        session_id: str,
        title: str,
        *,
        pinned: bool = True,
        restored: bool = False,
    ) -> None:
        """Explicitly assigns a title to a session, optionally pinning it."""
        state = self.get_state(session_id)
        state.title = title
        state.source = "restored" if restored else "pinned" if pinned else "manual"
        state.pinned = pinned
        state.restored = restored

    async def evaluate_turn(self, session_id: str, user_text: str) -> str:
        """Evaluates initial user turn for fallback and background titling."""
        state = self.get_state(session_id)
        if state.pinned or state.restored:
            return state.title or "Untitled Session"

        if state.title is None:
            fallback = extract_fallback_title(user_text)
            state.title = fallback
            state.source = "fallback"

            if hasattr(self.ctx, "llm"):
                task = asyncio.create_task(
                    self._generate_llm_title(session_id, user_text)
                )
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)

        return state.title

    async def _generate_llm_title(self, session_id: str, user_text: str) -> None:
        """Generates a concise title using LLM service in the background."""
        state = self.get_state(session_id)
        if state.pinned or state.restored:
            return

        prompt = (
            "Summarize the main topic of this user prompt into a short, concise "
            "title of 3 to 7 words. Return only the title text without quotes:\n\n"
            f"{user_text}"
        )
        try:
            llm_svc = getattr(self.ctx, "llm", None)
            if llm_svc is None:
                return

            resp = await llm_svc.generate(
                [{"role": "user", "content": prompt}],
                model=getattr(llm_svc, "default_model", None),
            )
            if resp and resp.text:
                cleaned = clean_llm_title(resp.text)
                if cleaned and not state.pinned and not state.restored:
                    state.title = cleaned
                    state.source = "llm"
        except Exception as ex:
            logger.debug("Background LLM titling skipped or failed: %s", ex)
