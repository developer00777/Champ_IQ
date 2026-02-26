"""Shared JSON extraction utilities for LLM output parsing.

Consolidates _extract_json (LLMService) and _parse_json_flexible (ResearchWorker)
into a single module. Both parsers handle the same problems:
  - Markdown code fences (```json ... ```)
  - Extra text before/after the JSON
  - Perplexity citation footnotes
  - Both top-level objects ({}) and arrays ([])
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def extract_json_object(text: str, source: str = "LLM") -> dict[str, Any]:
    """Extract the first JSON *object* from LLM output.

    Returns a dict. Raises ValueError if no valid JSON object is found.
    Used by LLMService.research_json() which expects a dict response.
    """
    result = _parse_flexible(text)
    if isinstance(result, dict):
        return result
    raise ValueError(f"{source} returned a JSON array, expected an object")


def extract_json_flexible(text: str) -> list | dict:
    """Extract the first JSON value (object or array) from LLM output.

    Returns a list or dict. Falls back to {"raw_response": text} if parsing fails.
    Used by ResearchWorker for pain_points and trigger_events which may be arrays.
    """
    return _parse_flexible(text)


def _parse_flexible(text: str) -> list | dict:
    """Core parser: strip fences, try direct parse, then brace/bracket match."""
    text = text.strip()

    # Strip markdown code fences
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    # Fast path: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find and extract the first complete [ ... ] or { ... } block
    for start_char, end_char in [("[", "]"), ("{", "}")]:
        start = text.find(start_char)
        if start == -1:
            continue
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            c = text[i]
            if escape:
                escape = False
                continue
            if c == "\\":
                escape = True
                continue
            if c == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == start_char:
                depth += 1
            elif c == end_char:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break

    logger.debug("Could not extract JSON from text: %s", text[:300])
    return {"raw_response": text}
