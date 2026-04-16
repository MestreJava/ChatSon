from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any
from urllib import error, request


OLLAMA_API_URL = "http://localhost:11434/api/chat"
DEFAULT_TIMEOUT_SECONDS = 45
LIST_FIELDS = ("actions", "constraints", "deliverables", "tags", "structuring_notes")

STRUCTURED_PROMPT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "role": {"type": "string"},
        "goal": {"type": "string"},
        "context": {"type": "string"},
        "actions": {"type": "array", "items": {"type": "string"}},
        "constraints": {"type": "array", "items": {"type": "string"}},
        "deliverables": {"type": "array", "items": {"type": "string"}},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "title",
        "role",
        "goal",
        "context",
        "actions",
        "constraints",
        "deliverables",
        "tags",
    ],
    "additionalProperties": False,
}


def _trim_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    else:
        items = re.split(r"(?:\r?\n|;)", str(value))
    normalized: list[str] = []
    for item in items:
        cleaned = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", str(item)).strip()
        if cleaned:
            normalized.append(cleaned)
    return normalized


def _slug_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _title_from_text(text: str) -> str:
    words = _slug_words(text)
    if not words:
        return "Prompt 1"
    selected = words[:6]
    return " ".join(word.capitalize() for word in selected)


def _sentence_chunks(text: str) -> list[str]:
    cleaned = re.sub(r"[\r\n]+", " ", text).strip()
    chunks = re.split(r"(?<=[.!?])\s+|,\s+(?=[a-zA-Z])", cleaned)
    results: list[str] = []
    for chunk in chunks:
        value = _trim_text(chunk).rstrip(".,;:")
        if value:
            results.append(value)
    return results


def _infer_role(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ("refactor", "replace", "migration", "standardize")):
        return "senior refactoring agent"
    if any(token in lowered for token in ("review", "audit", "inspect")):
        return "senior review agent"
    if any(token in lowered for token in ("plan", "roadmap", "steps")):
        return "senior implementation planner"
    return "senior prompt engineering agent"


def _extract_constraints(sentences: list[str]) -> list[str]:
    constraints = [
        sentence
        for sentence in sentences
        if any(
            token in sentence.lower()
            for token in ("never", "only", "except", "do not", "don't", "must", "without", "avoid")
        )
    ]
    return constraints


def _extract_actions(sentences: list[str], constraints: list[str]) -> list[str]:
    actions = [sentence for sentence in sentences if sentence not in constraints]
    return actions or sentences[:1]


def _infer_tags(text: str) -> list[str]:
    keywords: list[str] = []
    lowered = text.lower()
    for tag in ("prompt", "json", "api", "inventory", "refactor", "steam", "gui", "validation", "ollama"):
        if tag in lowered:
            keywords.append(tag)
    return keywords[:5]


def _heuristic_structure(raw_text: str, model: str, note: str | None = None) -> dict[str, Any]:
    text = raw_text.strip()
    sentences = _sentence_chunks(text)
    constraints = _extract_constraints(sentences)
    actions = _extract_actions(sentences, constraints)
    goal = actions[0] if actions else _trim_text(text[:160])
    deliverables = ["Structured prompt JSON ready for AI use"]
    if "plan" in text.lower():
        deliverables.append("Implementation plan with affected areas")

    notes = ["Used heuristic structuring fallback."]
    if note:
        notes.append(note)

    return {
        "title": _title_from_text(goal or text),
        "role": _infer_role(text),
        "goal": _trim_text(goal),
        "context": _trim_text(text),
        "actions": _normalize_list(actions),
        "constraints": _normalize_list(constraints),
        "deliverables": _normalize_list(deliverables),
        "tags": _infer_tags(text),
        "structuring_engine": "heuristic",
        "structuring_model": model,
        "structuring_notes": notes,
    }


def _build_messages(raw_text: str) -> list[dict[str, str]]:
    system_prompt = (
        "You convert a raw user request into a specialized prompt definition for another AI system. "
        "Return valid JSON only, with no markdown, no code fences, and no commentary. "
        "Do not answer the request itself. Rewrite the request into a structured instruction object. "
        "Preserve the user's actual intent and constraints. "
        "Use empty strings or empty arrays when information is missing."
    )
    user_prompt = (
        "Convert the following raw prompt into structured JSON for prompt engineering.\n\n"
        "Required meaning:\n"
        "- role: the specialist AI identity best suited to execute the request\n"
        "- goal: the primary objective to accomplish\n"
        "- context: the background information that must be preserved\n"
        "- actions: concrete steps or required actions\n"
        "- constraints: non-negotiable rules, exclusions, or limits\n"
        "- deliverables: what the AI should produce\n"
        "- title: short readable title\n"
        "- tags: short keywords\n\n"
        f"Raw prompt:\n{raw_text}"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _call_ollama(raw_text: str, model: str) -> dict[str, Any]:
    body = {
        "model": model,
        "messages": _build_messages(raw_text),
        "stream": False,
        "format": STRUCTURED_PROMPT_SCHEMA,
        "options": {"temperature": 0},
    }
    payload = json.dumps(body).encode("utf-8")
    req = request.Request(
        OLLAMA_API_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
        raw_response = response.read().decode("utf-8")
    data = json.loads(raw_response)
    message = data.get("message", {})
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Ollama returned an empty structured response.")
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("Ollama returned non-object JSON.")
    return parsed


def _normalize_structured_output(data: dict[str, Any], raw_text: str, model: str) -> dict[str, Any]:
    normalized: dict[str, Any] = {
        "title": _trim_text(data.get("title")) or _title_from_text(raw_text),
        "role": _trim_text(data.get("role")) or _infer_role(raw_text),
        "goal": _trim_text(data.get("goal")) or _trim_text(raw_text[:160]),
        "context": _trim_text(data.get("context")) or _trim_text(raw_text),
        "actions": _normalize_list(data.get("actions")),
        "constraints": _normalize_list(data.get("constraints")),
        "deliverables": _normalize_list(data.get("deliverables")),
        "tags": _normalize_list(data.get("tags")),
        "structuring_engine": "ollama",
        "structuring_model": model,
        "structuring_notes": ["Structured with local Ollama JSON schema output."],
    }
    if not normalized["actions"]:
        normalized["actions"] = [_trim_text(raw_text[:160])]
        normalized["structuring_notes"].append("Actions were repaired locally because the model returned none.")
    return normalized


@lru_cache(maxsize=128)
def _structure_plain_prompt_cached(raw_text: str, model: str) -> str:
    cleaned = raw_text.strip()
    if not cleaned:
        return json.dumps({
            "title": "Prompt 1",
            "role": "senior prompt engineering agent",
            "goal": "",
            "context": "",
            "actions": [],
            "constraints": [],
            "deliverables": [],
            "tags": [],
            "structuring_engine": "heuristic",
            "structuring_model": model,
            "structuring_notes": ["Input was empty."],
        })
    try:
        parsed = _call_ollama(cleaned, model)
        return json.dumps(_normalize_structured_output(parsed, cleaned, model))
    except (error.URLError, TimeoutError, ConnectionError) as exc:
        return json.dumps(_heuristic_structure(cleaned, model, f"Ollama unavailable: {exc}"))
    except (json.JSONDecodeError, ValueError) as exc:
        return json.dumps(
            _heuristic_structure(
                cleaned,
                model,
                f"Invalid structured response repaired with heuristic fallback: {exc}",
            )
        )


def structure_plain_prompt(raw_text: str, model: str) -> dict[str, Any]:
    return json.loads(_structure_plain_prompt_cached(raw_text, model))

