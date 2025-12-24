"""
chatbot.py
----------
Chatbot session logic.

Behavior:
- On the first user message in a brand-new session:
    user_text -> prompts.build_generator_prompt(user_text) -> generator.generate_answer(...)
- On subsequent messages:
    The user's new query is kept "as-is", but we ALSO include the prior chat history
    so the model can respond in-context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict

from .generator import generate_answer
from .prompts import build_generator_prompt, build_patient_prompt, build_doctor_prompt


def _format_history(messages: List[Dict[str, str]], max_turns: int = 12) -> str:
    """
    Convert chat history into a plain-text transcript.

    We keep the newest `max_turns` user+assistant turns to avoid overly long prompts.
    """
    # Keep only user/assistant roles and trim to last N turns.
    filtered = [m for m in messages if m.get("role") in ("user", "assistant")]
    # A "turn" is (user, assistant). Keep last max_turns*2 messages.
    trimmed = filtered[-max_turns * 2 :]

    lines: List[str] = []
    for m in trimmed:
        role = m["role"]
        content = (m.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            lines.append(f"User: {content}")
        else:
            lines.append(f"Assistant: {content}")
    return "\n".join(lines).strip()


@dataclass
class ChatSession:
    """
    Minimal stateful chatbot wrapper.

    `messages` stores the running history for context.
    """
    started: bool = False
    messages: List[Dict[str, str]] = field(default_factory=list)
    user_type: str = "patient"

    def reply(self, user_text: str) -> str:
        user_text = (user_text or "").strip()
        if not user_text:
            return "Please enter a message."

        # Record the user message in history right away
        self.messages.append({"role": "user", "content": user_text})

        # 1) First message: run through build_generator_prompt(...)
        if not self.started:
            self.started = True
            if self.user_type == "doctor":
                prompt = build_doctor_prompt(user_text)
            else:
                prompt = build_patient_prompt(user_text)
            
            # Legacy fallback if you prefer: prompt = build_generator_prompt(user_text)
            
            answer = generate_answer(prompt)
            self.messages.append({"role": "assistant", "content": answer})
            return answer

        # 2) Follow-ups: include history + the new query (kept as-is)
        transcript = _format_history(self.messages[:-1])  # everything before current user msg
        prompt = (
            "You are a helpful assistant in an ongoing conversation.\n"
            "Use the conversation history for context and continuity.\n\n"
            f"Conversation history:\n{transcript}\n\n"
            f"User: {user_text}\n"
            "Assistant:"
        )

        answer = generate_answer(prompt)
        self.messages.append({"role": "assistant", "content": answer})
        return answer
