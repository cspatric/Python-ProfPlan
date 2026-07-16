"""Pulling a JSON object out of an LLM answer.

Models drift: they wrap the object in a code fence, or preface it with "Here is
the roadmap:", however firmly the prompt says not to. This tolerates both rather
than burning a retry on a response whose JSON is right there.
"""


def extract_json(text: str) -> str:
    """Return the JSON object embedded in an LLM answer.

    Raises ValueError when the answer contains no object at all.
    """
    text = text.strip()
    if "```" in text:
        # take the content of the first fenced block
        parts = text.split("```")
        if len(parts) >= 2:
            block = parts[1]
            block = block[4:] if block.lower().startswith("json") else block
            text = block.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("the answer contains no JSON object")
    return text[start : end + 1]
