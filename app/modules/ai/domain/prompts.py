"""Prompt templates for the AI module."""

from app.shared.ai.prompt_safety import CONTEXT_SAFETY_RULE, wrap_untrusted_context

ASSISTANT_SYSTEM_PROMPT = (
    "You are ProfPlan, a teaching assistant for educators. Answer clearly and "
    "pedagogically. When context from the teacher's documents is provided, base "
    "your answer on it and cite the passages by their [n] markers. If the "
    "context is insufficient, say so instead of inventing facts. " + CONTEXT_SAFETY_RULE
)


def build_rag_prompt(query: str, context: str) -> str:
    """Combine the retrieved context and the question into a prompt."""
    if not context:
        return query
    return f"Context:\n{wrap_untrusted_context(context)}\n\nQuestion: {query}"
