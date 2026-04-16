from __future__ import annotations

import json
import re
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from prompt_structuring_ai import structure_plain_prompt

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD  # type: ignore
    DND_AVAILABLE = True
except Exception:
    DND_AVAILABLE = False
    TkinterDnD = None  # type: ignore
    DND_FILES = None  # type: ignore


SUPPORTED_EXTENSIONS = {".txt", ".md", ".prompt", ".prompts"}
INLINE_SOURCE_KEY = "__typed_input__"
INLINE_SOURCE_PATH = "Typed in app"
DEFAULT_LLM_MODEL = "qwen2.5:7b"
SPECIALIZED_LIST_FIELDS = {"tags", "actions", "constraints", "deliverables", "structuring_notes"}
SPECIALIZED_FIELDS = {
    "role",
    "goal",
    "context",
    "actions",
    "constraints",
    "deliverables",
    "original_text",
    "structuring_engine",
    "structuring_model",
    "structuring_notes",
}
RECOGNIZED_FIELDS = {
    "title",
    "id",
    "system",
    "user",
    "assistant",
    "description",
    "tags",
    "category",
    "prompt",
    "role",
    "goal",
    "context",
    "actions",
    "constraints",
    "deliverables",
    "original_text",
}
APP_COLORS = {
    "bg": "#dbeafe",
    "panel": "#eff6ff",
    "panel_alt": "#e0f2fe",
    "text_bg": "#f8fbff",
    "text_fg": "#0f172a",
    "muted_fg": "#334155",
    "border": "#93c5fd",
    "button": "#16a34a",
    "button_hover": "#15803d",
    "button_pressed": "#166534",
    "button_text": "#ffffff",
    "selection": "#60a5fa",
}
FIELD_ALIASES = {
    "title": "title",
    "name": "title",
    "id": "id",
    "system": "system",
    "system_prompt": "system",
    "developer": "system",
    "developer_prompt": "system",
    "user": "user",
    "user_prompt": "user",
    "assistant": "assistant",
    "description": "description",
    "tags": "tags",
    "category": "category",
    "prompt": "prompt",
    "role": "role",
    "goal": "goal",
    "context": "context",
    "actions": "actions",
    "steps": "actions",
    "constraints": "constraints",
    "rules": "constraints",
    "deliverables": "deliverables",
    "outputs": "deliverables",
    "original_text": "original_text",
    "raw_text": "original_text",
}
RE_BLOCK_SEPARATOR = re.compile(r"\n\s*---\s*\n", re.MULTILINE)
RE_FIELD = re.compile(r"^([A-Za-z_ ][A-Za-z0-9_ ]*?)\s*:\s*(.*)$")
RE_VARIABLE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


@dataclass
class PromptRecord:
    source_path: str
    block_index: int
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return str(self.data.get("id", ""))

    @property
    def title(self) -> str:
        return str(self.data.get("title", ""))

    @property
    def variables(self) -> list[str]:
        found: set[str] = set()
        for value in self.data.values():
            found.update(extract_variables_from_value(value))
        return sorted(found)


def normalize_key(key: str) -> str:
    key = key.strip().lower().replace(" ", "_")
    return FIELD_ALIASES.get(key, key)


def parse_tags(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[;,]", value) if item.strip()]


def parse_list_field(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    else:
        items = re.split(r"(?:\r?\n|;)", str(value))
    parsed: list[str] = []
    for item in items:
        cleaned = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", str(item)).strip()
        if cleaned:
            parsed.append(cleaned)
    return parsed


def parse_field_value(key: str, value: str) -> Any:
    if key == "tags":
        return parse_tags(value)
    if key in SPECIALIZED_LIST_FIELDS:
        return parse_list_field(value)
    return value.strip()


def extract_variables_from_value(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, str):
        found.update(RE_VARIABLE.findall(value))
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                found.update(RE_VARIABLE.findall(item))
    return found


def normalize_string_list(value: Any) -> list[str]:
    return parse_list_field(value)


def has_specialized_structure(data: dict[str, Any]) -> bool:
    return any(data.get(key) for key in SPECIALIZED_FIELDS)


def render_list(values: Any, variables: dict[str, Any]) -> list[str]:
    return [render_template(item, variables) for item in normalize_string_list(values)]


def build_specialized_messages(prompt: "PromptRecord", variables: dict[str, Any]) -> list[dict[str, str]]:
    developer_lines: list[str] = []
    user_lines: list[str] = []

    role = render_template(str(prompt.data.get("role", "")).strip(), variables)
    goal = render_template(str(prompt.data.get("goal", "")).strip(), variables)
    context = render_template(str(prompt.data.get("context", "")).strip(), variables)
    actions = render_list(prompt.data.get("actions"), variables)
    constraints = render_list(prompt.data.get("constraints"), variables)
    deliverables = render_list(prompt.data.get("deliverables"), variables)
    original_text = render_template(
        str(prompt.data.get("original_text") or prompt.data.get("prompt", "")).strip(),
        variables,
    )

    if role:
        developer_lines.append(f"Role: {role}")
    if goal:
        developer_lines.append(f"Goal: {goal}")
    if context:
        developer_lines.append(f"Context: {context}")
    if constraints:
        developer_lines.append("Constraints:")
        developer_lines.extend(f"- {item}" for item in constraints)
    developer_lines.append("Preserve the user's intent exactly and produce work aligned with this structure.")

    if actions:
        user_lines.append("Actions:")
        user_lines.extend(f"- {item}" for item in actions)
    if deliverables:
        user_lines.append("Deliverables:")
        user_lines.extend(f"- {item}" for item in deliverables)
    if original_text:
        user_lines.append("Original request:")
        user_lines.append(original_text)

    return [
        {"role": "developer", "content": "\n".join(line for line in developer_lines if line).strip()},
        {"role": "user", "content": "\n".join(line for line in user_lines if line).strip()},
    ]


def render_template(text: str, variables: dict[str, Any]) -> str:
    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        value = variables.get(name)
        return match.group(0) if value is None else str(value)

    return RE_VARIABLE.sub(repl, text)


def parse_block(block: str, index: int, source_path: str, model_name: str = DEFAULT_LLM_MODEL) -> PromptRecord:
    lines = block.strip().splitlines()
    data: dict[str, Any] = {}
    current_key: str | None = None
    buffer: list[str] = []
    found_structured_fields = False

    def flush() -> None:
        nonlocal current_key, buffer
        if current_key is None:
            return
        value = "\n".join(buffer).strip()
        data[current_key] = parse_field_value(current_key, value)
        current_key = None
        buffer = []

    for line in lines:
        match = RE_FIELD.match(line)
        if match:
            raw_key, raw_value = match.groups()
            key = normalize_key(raw_key)
            if key in RECOGNIZED_FIELDS:
                flush()
                current_key = key
                buffer = [raw_value]
                found_structured_fields = True
                continue

        if current_key is not None:
            buffer.append(line)
        else:
            buffer.append(line)

    flush()

    if not found_structured_fields:
        raw_text = block.strip()
        structured = structure_plain_prompt(raw_text, model_name)
        data = {
            "id": f"prompt_{index:03d}",
            "title": str(structured.get("title") or f"Prompt {index}"),
            "prompt": raw_text,
            "original_text": raw_text,
            "tags": normalize_string_list(structured.get("tags")),
        }
        data.update(structured)
    else:
        data.setdefault("id", f"prompt_{index:03d}")
        data.setdefault("title", f"Prompt {index}")
        data.setdefault("tags", [])

    return PromptRecord(source_path=source_path, block_index=index, data=data)


def parse_text_to_prompts(text: str, source_path: str, model_name: str = DEFAULT_LLM_MODEL) -> list[PromptRecord]:
    blocks = [b.strip() for b in RE_BLOCK_SEPARATOR.split(text) if b.strip()]
    if not blocks and text.strip():
        blocks = [text.strip()]
    return [parse_block(block, i + 1, source_path, model_name) for i, block in enumerate(blocks)]


def prompt_to_messages(prompt: PromptRecord, variables: dict[str, Any] | None = None) -> list[dict[str, str]]:
    variables = variables or {}
    if has_specialized_structure(prompt.data):
        return build_specialized_messages(prompt, variables)
    messages: list[dict[str, str]] = []
    if prompt.data.get("system"):
        content = str(prompt.data["system"])
        messages.append({"role": "developer", "content": render_template(content, variables)})
    if prompt.data.get("user"):
        content = str(prompt.data["user"])
        messages.append({"role": "user", "content": render_template(content, variables)})
    elif prompt.data.get("prompt"):
        content = str(prompt.data["prompt"])
        messages.append({"role": "user", "content": render_template(content, variables)})
    if prompt.data.get("assistant"):
        content = str(prompt.data["assistant"])
        messages.append({"role": "assistant", "content": render_template(content, variables)})
    return messages


def serialize_prompt(
    prompt: PromptRecord,
    export_mode: str,
    variables: dict[str, Any] | None = None,
    model_name: str = DEFAULT_LLM_MODEL,
) -> dict[str, Any]:
    variables = variables or {}

    base = {
        "id": prompt.id,
        "title": prompt.title,
        "source_path": prompt.source_path,
        "block_index": prompt.block_index,
        "tags": prompt.data.get("tags", []),
    }
    if prompt.data.get("description"):
        base["description"] = prompt.data["description"]
    if prompt.data.get("category"):
        base["category"] = prompt.data["category"]

    if export_mode == "Raw archive":
        payload = dict(base)
        payload.update({k: v for k, v in prompt.data.items() if k not in payload})
        payload["variables"] = prompt.variables
        return payload

    if export_mode == "Dynamic template":
        payload = dict(base)
        payload["template"] = {"messages": prompt_to_messages(prompt)}
        payload["variables"] = [{"name": name, "required": True} for name in prompt.variables]
        return payload

    if export_mode == "API-ready":
        payload = dict(base)
        payload["model"] = model_name
        payload["input"] = prompt_to_messages(prompt, variables)
        payload["resolved_variables"] = {k: v for k, v in variables.items() if k in prompt.variables}
        return payload

    raise ValueError(f"Unsupported export mode: {export_mode}")


def validate_prompts(
    prompts: list[PromptRecord],
    export_mode: str,
    variables: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    variables = variables or {}
    issues: list[dict[str, str]] = []
    id_counts: dict[str, int] = {}

    for prompt in prompts:
        id_counts[prompt.id] = id_counts.get(prompt.id, 0) + 1

    for prompt in prompts:
        where = f"{Path(prompt.source_path).name} :: block {prompt.block_index} :: {prompt.id}"
        title = prompt.title.strip()
        specialized = has_specialized_structure(prompt.data)
        if not title:
            issues.append({"level": "ERROR", "where": where, "message": "Missing title."})

        has_prompt_content = bool(
            str(prompt.data.get("user", "")).strip()
            or str(prompt.data.get("prompt", "")).strip()
            or str(prompt.data.get("goal", "")).strip()
            or normalize_string_list(prompt.data.get("actions"))
        )
        if not has_prompt_content:
            issues.append({
                "level": "ERROR",
                "where": where,
                "message": "Missing prompt content or specialized goal/actions.",
            })

        if id_counts.get(prompt.id, 0) > 1:
            issues.append({"level": "ERROR", "where": where, "message": f"Duplicate id '{prompt.id}'."})

        if specialized and not str(prompt.data.get("goal", "")).strip():
            issues.append({"level": "WARN", "where": where, "message": "Structured prompt has no goal."})

        if specialized and not normalize_string_list(prompt.data.get("actions")):
            issues.append({"level": "WARN", "where": where, "message": "Structured prompt has no actions."})

        if not specialized and not prompt.data.get("system"):
            issues.append({
                "level": "WARN",
                "where": where,
                "message": "No SYSTEM field. This is allowed, but you may want one for instruction quality.",
            })

        structuring_engine = str(prompt.data.get("structuring_engine", "")).strip()
        if structuring_engine == "heuristic":
            issues.append({
                "level": "WARN",
                "where": where,
                "message": "AI structuring fallback was used instead of Ollama.",
            })
        elif structuring_engine == "ollama":
            issues.append({
                "level": "INFO",
                "where": where,
                "message": f"Structured with Ollama model '{prompt.data.get('structuring_model', DEFAULT_LLM_MODEL)}'.",
            })

        for note in normalize_string_list(prompt.data.get("structuring_notes")):
            lowered = note.lower()
            level = "WARN" if any(token in lowered for token in ("fallback", "unavailable", "invalid", "repaired")) else "INFO"
            issues.append({"level": level, "where": where, "message": note})

        if export_mode == "API-ready":
            missing = [name for name in prompt.variables if variables.get(name) in (None, "")]
            if missing:
                issues.append({
                    "level": "ERROR",
                    "where": where,
                    "message": f"Missing values for variables: {', '.join(missing)}.",
                })

        if export_mode == "Dynamic template" and not prompt.variables:
            issues.append({
                "level": "INFO",
                "where": where,
                "message": "No dynamic variables found. Template is valid but static.",
            })

    return issues


def load_text_file(path: str) -> str:
    encodings = ["utf-8", "utf-8-sig", "cp1252", "latin-1"]
    last_error: Exception | None = None
    for encoding in encodings:
        try:
            return Path(path).read_text(encoding=encoding)
        except Exception as exc:  # noqa: PERF203
            last_error = exc
    raise RuntimeError(f"Unable to read file '{path}': {last_error}")


def collect_files(paths: list[str]) -> list[str]:
    results: list[str] = []
    for raw_path in paths:
        path = raw_path.strip().strip('"')
        if not path:
            continue
        p = Path(path)
        if p.is_dir():
            for sub in p.rglob("*"):
                if sub.is_file() and sub.suffix.lower() in SUPPORTED_EXTENSIONS:
                    results.append(str(sub.resolve()))
        elif p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS:
            results.append(str(p.resolve()))
    return sorted(set(results))


class PromptTransformerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Prompt Text → JSON Transformer")
        self.root.geometry("1500x900")
        self.files: list[str] = []
        self.source_keys: list[str] = []
        self.prompts_by_file: dict[str, list[PromptRecord]] = {}
        self.current_preview_file: str | None = None
        self.inline_source_text = ""
        self.inline_source_enabled = False

        self.export_mode_var = tk.StringVar(value="Dynamic template")
        self.model_var = tk.StringVar(value=DEFAULT_LLM_MODEL)
        self.merge_var = tk.BooleanVar(value=True)

        self._apply_theme()
        self._build_ui()
        self._bind_drag_and_drop()

    def _current_model_name(self) -> str:
        return self.model_var.get().strip() or DEFAULT_LLM_MODEL

    def _apply_theme(self) -> None:
        self.root.configure(bg=APP_COLORS["bg"])
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure("TFrame", background=APP_COLORS["bg"])
        style.configure("TLabel", background=APP_COLORS["bg"], foreground=APP_COLORS["text_fg"])
        style.configure("TCheckbutton", background=APP_COLORS["bg"], foreground=APP_COLORS["text_fg"])
        style.map("TCheckbutton", background=[("active", APP_COLORS["bg"])])
        style.configure("TPanedwindow", background=APP_COLORS["bg"])
        style.configure(
            "TButton",
            background=APP_COLORS["button"],
            foreground=APP_COLORS["button_text"],
            padding=6,
            borderwidth=0,
            focusthickness=0,
        )
        style.map(
            "TButton",
            background=[
                ("active", APP_COLORS["button_hover"]),
                ("pressed", APP_COLORS["button_pressed"]),
            ],
            foreground=[("disabled", "#dcfce7")],
        )
        style.configure(
            "TEntry",
            fieldbackground=APP_COLORS["text_bg"],
            foreground=APP_COLORS["text_fg"],
            insertcolor=APP_COLORS["text_fg"],
        )
        style.configure(
            "TCombobox",
            fieldbackground=APP_COLORS["text_bg"],
            background=APP_COLORS["text_bg"],
            foreground=APP_COLORS["text_fg"],
        )

    def _style_scrolled_text(self, widget: ScrolledText) -> None:
        widget.configure(
            bg=APP_COLORS["text_bg"],
            fg=APP_COLORS["text_fg"],
            insertbackground=APP_COLORS["text_fg"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=APP_COLORS["border"],
            highlightcolor=APP_COLORS["selection"],
            selectbackground=APP_COLORS["selection"],
            selectforeground=APP_COLORS["button_text"],
        )

    def _build_ui(self) -> None:
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")

        ttk.Button(top, text="Add Files", command=self.add_files).pack(side="left", padx=4)
        ttk.Button(top, text="Add Folder", command=self.add_folder).pack(side="left", padx=4)
        ttk.Button(top, text="Write In App", command=self.activate_inline_input).pack(side="left", padx=4)
        ttk.Button(top, text="Convert Typed Text", command=self.convert_inline_text).pack(side="left", padx=4)
        ttk.Button(top, text="Scan & Convert", command=self.refresh_all).pack(side="left", padx=4)
        ttk.Button(top, text="Export JSON", command=self.export_json).pack(side="left", padx=4)
        ttk.Button(top, text="Clear", command=self.clear_all).pack(side="left", padx=4)

        ttk.Label(top, text="Export mode:").pack(side="left", padx=(18, 4))
        self.mode_combo = ttk.Combobox(
            top,
            textvariable=self.export_mode_var,
            values=["Raw archive", "Dynamic template", "API-ready"],
            width=18,
            state="readonly",
        )
        self.mode_combo.pack(side="left")
        self.mode_combo.bind("<<ComboboxSelected>>", lambda _e: self.update_preview())

        ttk.Label(top, text="Model (Ollama):").pack(side="left", padx=(18, 4))
        self.model_entry = ttk.Entry(top, textvariable=self.model_var, width=18)
        self.model_entry.pack(side="left")

        ttk.Checkbutton(top, text="Merge all files into one export", variable=self.merge_var).pack(
            side="left", padx=(18, 4)
        )

        tip = ttk.Label(
            self.root,
            text=(
                "Supported fields: TITLE, ID, SYSTEM, USER, ASSISTANT, DESCRIPTION, TAGS, CATEGORY, PROMPT, "
                "ROLE, GOAL, CONTEXT, ACTIONS, CONSTRAINTS, DELIVERABLES. Plain text is auto-structured with "
                "local Ollama when available, with a built-in fallback when it is not. Separate prompts with --- ."
            ),
            padding=(10, 0, 10, 8),
        )
        tip.pack(fill="x")

        paned = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill="both", expand=True)

        left = ttk.Frame(paned, padding=8)
        middle = ttk.Frame(paned, padding=8)
        right = ttk.Frame(paned, padding=8)
        paned.add(left, weight=1)
        paned.add(middle, weight=2)
        paned.add(right, weight=2)

        ttk.Label(left, text="Files / folders converted").pack(anchor="w")
        self.files_list = tk.Listbox(
            left,
            exportselection=False,
            bg=APP_COLORS["text_bg"],
            fg=APP_COLORS["text_fg"],
            selectbackground=APP_COLORS["selection"],
            selectforeground=APP_COLORS["button_text"],
            highlightthickness=1,
            highlightbackground=APP_COLORS["border"],
            highlightcolor=APP_COLORS["selection"],
            relief="flat",
        )
        self.files_list.pack(fill="both", expand=True)
        self.files_list.bind("<<ListboxSelect>>", self.on_file_select)

        ttk.Label(middle, text="Source text preview / typed input").pack(anchor="w")
        self.source_text = ScrolledText(middle, wrap="word")
        self.source_text.pack(fill="both", expand=True)
        self._style_scrolled_text(self.source_text)

        ttk.Label(right, text="Generated JSON preview").pack(anchor="w")
        self.json_text = ScrolledText(right, wrap="word")
        self.json_text.pack(fill="both", expand=True)
        self._style_scrolled_text(self.json_text)

        bottom = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        bottom.pack(fill="both", expand=False, padx=8, pady=(0, 8))

        variables_frame = ttk.Frame(bottom, padding=8)
        validation_frame = ttk.Frame(bottom, padding=8)
        bottom.add(variables_frame, weight=1)
        bottom.add(validation_frame, weight=2)

        ttk.Label(variables_frame, text="Variable values (JSON object)").pack(anchor="w")
        self.variables_text = ScrolledText(variables_frame, height=10, wrap="word")
        self.variables_text.pack(fill="both", expand=True)
        self._style_scrolled_text(self.variables_text)
        self.variables_text.insert(
            "1.0",
            json.dumps(
                {
                    "name": "Maria",
                    "topic": "project update",
                    "language": "English",
                },
                indent=2,
            ),
        )
        ttk.Button(variables_frame, text="Refresh Preview", command=self.update_preview).pack(anchor="e", pady=(8, 0))

        ttk.Label(validation_frame, text="Validation results").pack(anchor="w")
        self.validation_text = ScrolledText(validation_frame, height=10, wrap="word")
        self.validation_text.pack(fill="both", expand=True)
        self._style_scrolled_text(self.validation_text)

    def _bind_drag_and_drop(self) -> None:
        if not DND_AVAILABLE:
            self.validation_text.insert(
                "end",
                "[INFO] Drag-and-drop disabled. Install tkinterdnd2 to enable it: pip install tkinterdnd2\n",
            )
            return

        for widget in (self.root, self.files_list, self.source_text, self.json_text):
            try:
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", self.on_drop)  # type: ignore[attr-defined]
            except Exception:
                continue

    def parse_variables_json(self) -> dict[str, Any]:
        raw = self.variables_text.get("1.0", "end").strip()
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Variable JSON is invalid: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("Variable values must be a JSON object, not a list or plain value.")
        return data

    def on_drop(self, event: Any) -> None:
        data = getattr(event, "data", "")
        paths = self.root.tk.splitlist(data)
        collected = collect_files(list(paths))
        if not collected:
            messagebox.showwarning("No supported files", "No supported .txt/.md/.prompt files were found.")
            return
        self.add_paths(collected)

    def add_files(self) -> None:
        selected = filedialog.askopenfilenames(
            title="Select prompt text files",
            filetypes=[("Prompt text", "*.txt *.md *.prompt *.prompts"), ("All files", "*.*")],
        )
        if selected:
            self.add_paths(collect_files(list(selected)))

    def add_folder(self) -> None:
        selected = filedialog.askdirectory(title="Select folder")
        if selected:
            self.add_paths(collect_files([selected]))

    def add_paths(self, new_paths: list[str]) -> None:
        merged = sorted(set(self.files).union(new_paths))
        self.files = merged
        self.refresh_all()

    def source_label(self, key: str) -> str:
        if key == INLINE_SOURCE_KEY:
            count = len(self.prompts_by_file.get(INLINE_SOURCE_KEY, []))
            return f"{INLINE_SOURCE_PATH}  ({count} prompt blocks)"
        return f"{Path(key).name}  ({len(self.prompts_by_file.get(key, []))} prompt blocks)"

    def set_source_text_content(self, content: str, editable: bool) -> None:
        self.source_text.config(state="normal")
        self.source_text.delete("1.0", "end")
        self.source_text.insert("1.0", content)
        self.source_text.config(state="normal" if editable else "disabled")

    def sync_inline_source_from_editor(self) -> None:
        if self.current_preview_file == INLINE_SOURCE_KEY:
            self.inline_source_text = self.source_text.get("1.0", "end").strip()

    def parse_inline_source(self) -> None:
        if not self.inline_source_enabled:
            self.prompts_by_file.pop(INLINE_SOURCE_KEY, None)
            return
        if not self.inline_source_text.strip():
            self.prompts_by_file[INLINE_SOURCE_KEY] = []
            return
        self.prompts_by_file[INLINE_SOURCE_KEY] = parse_text_to_prompts(
            self.inline_source_text,
            INLINE_SOURCE_PATH,
            self._current_model_name(),
        )

    def rebuild_sources_list(self, preferred_key: str | None = None) -> None:
        self.source_keys = list(self.files)
        if self.inline_source_enabled:
            self.source_keys.append(INLINE_SOURCE_KEY)

        self.files_list.delete(0, "end")
        for key in self.source_keys:
            self.files_list.insert("end", self.source_label(key))

        if not self.source_keys:
            return

        if preferred_key in self.source_keys:
            index = self.source_keys.index(preferred_key)
        elif self.current_preview_file in self.source_keys:
            index = self.source_keys.index(self.current_preview_file)
        else:
            index = 0

        self.files_list.selection_clear(0, "end")
        self.files_list.selection_set(index)
        self.files_list.event_generate("<<ListboxSelect>>")

    def activate_inline_input(self) -> None:
        self.inline_source_enabled = True
        if not self.inline_source_text.strip():
            self.inline_source_text = (
                "Describe the changes needed in this project.\n"
                "Keep the important constraints.\n"
                "Return a structured prompt definition for another AI."
            )
        self.parse_inline_source()
        self.current_preview_file = INLINE_SOURCE_KEY
        self.rebuild_sources_list(preferred_key=INLINE_SOURCE_KEY)

    def convert_inline_text(self) -> None:
        if self.current_preview_file != INLINE_SOURCE_KEY and not self.inline_source_enabled:
            self.activate_inline_input()
        self.inline_source_enabled = True
        self.sync_inline_source_from_editor()
        self.parse_inline_source()
        self.current_preview_file = INLINE_SOURCE_KEY
        self.rebuild_sources_list(preferred_key=INLINE_SOURCE_KEY)
        self.update_preview()

    def clear_all(self) -> None:
        self.files = []
        self.source_keys = []
        self.prompts_by_file = {}
        self.current_preview_file = None
        self.inline_source_text = ""
        self.inline_source_enabled = False
        self.files_list.delete(0, "end")
        self.set_source_text_content("", editable=True)
        self.json_text.delete("1.0", "end")
        self.validation_text.delete("1.0", "end")

    def refresh_all(self) -> None:
        self.sync_inline_source_from_editor()
        self.prompts_by_file.clear()
        errors: list[str] = []
        for path in self.files:
            try:
                text = load_text_file(path)
                self.prompts_by_file[path] = parse_text_to_prompts(text, path, self._current_model_name())
            except Exception as exc:
                errors.append(f"[ERROR] {path}: {exc}")

        self.parse_inline_source()

        if self.files or self.inline_source_enabled:
            preferred_key = self.current_preview_file if self.current_preview_file in self.source_keys else None
            self.rebuild_sources_list(preferred_key=preferred_key)
        else:
            self.set_source_text_content("", editable=True)
            self.json_text.delete("1.0", "end")

        validation_lines = []
        if errors:
            validation_lines.extend(errors)
        validation_lines.extend(self.build_validation_lines())
        self.validation_text.delete("1.0", "end")
        self.validation_text.insert("1.0", "\n".join(validation_lines) if validation_lines else "No validation issues.")

    def on_file_select(self, _event: Any) -> None:
        selection = self.files_list.curselection()
        if not selection:
            return
        index = selection[0]
        if index >= len(self.source_keys):
            return
        key = self.source_keys[index]
        self.current_preview_file = key
        if key == INLINE_SOURCE_KEY:
            source = self.inline_source_text
            self.set_source_text_content(source, editable=True)
            self.update_preview()
            return
        try:
            source = load_text_file(key)
        except Exception as exc:
            source = f"Unable to read file: {exc}"
        self.set_source_text_content(source, editable=False)
        self.update_preview()

    def all_prompts(self) -> list[PromptRecord]:
        results: list[PromptRecord] = []
        for prompts in self.prompts_by_file.values():
            results.extend(prompts)
        return results

    def preview_prompts(self) -> list[PromptRecord]:
        if self.current_preview_file and self.current_preview_file in self.prompts_by_file:
            return self.prompts_by_file[self.current_preview_file]
        return self.all_prompts()

    def build_validation_lines(self) -> list[str]:
        try:
            variables = self.parse_variables_json()
        except Exception as exc:
            return [f"[ERROR] {exc}"]

        issues = validate_prompts(self.all_prompts(), self.export_mode_var.get(), variables)
        lines = []
        for issue in issues:
            lines.append(f"[{issue['level']}] {issue['where']} — {issue['message']}")
        if not lines:
            lines.append("No validation issues.")
        return lines

    def update_preview(self) -> None:
        if self.current_preview_file == INLINE_SOURCE_KEY:
            self.sync_inline_source_from_editor()
            self.parse_inline_source()
        prompts = self.preview_prompts()
        try:
            variables = self.parse_variables_json()
            export_mode = self.export_mode_var.get()
            model_name = self._current_model_name()
            preview = [serialize_prompt(p, export_mode, variables, model_name) for p in prompts]
            payload: dict[str, Any] | list[dict[str, Any]]
            if self.merge_var.get():
                payload = {"prompts": preview}
            else:
                payload = preview
            rendered = json.dumps(payload, indent=2, ensure_ascii=False)
            self.json_text.delete("1.0", "end")
            self.json_text.insert("1.0", rendered)
        except Exception as exc:
            self.json_text.delete("1.0", "end")
            self.json_text.insert("1.0", f"Preview error: {exc}\n\n{traceback.format_exc()}")

        self.validation_text.delete("1.0", "end")
        self.validation_text.insert("1.0", "\n".join(self.build_validation_lines()))

    def export_json(self) -> None:
        self.sync_inline_source_from_editor()
        self.parse_inline_source()
        if not self.all_prompts():
            messagebox.showwarning("Nothing to export", "Add files, a folder, or typed input first.")
            return

        try:
            variables = self.parse_variables_json()
        except Exception as exc:
            messagebox.showerror("Invalid variable JSON", str(exc))
            return

        issues = validate_prompts(self.all_prompts(), self.export_mode_var.get(), variables)
        errors = [item for item in issues if item["level"] == "ERROR"]
        if errors:
            show = "\n".join(f"- {e['where']}: {e['message']}" for e in errors[:15])
            messagebox.showerror("Fix validation errors first", show)
            return

        model_name = self._current_model_name()
        export_mode = self.export_mode_var.get()

        if self.merge_var.get():
            path = filedialog.asksaveasfilename(
                title="Save merged JSON",
                defaultextension=".json",
                filetypes=[("JSON files", "*.json")],
            )
            if not path:
                return
            payload = {
                "prompts": [serialize_prompt(p, export_mode, variables, model_name) for p in self.all_prompts()]
            }
            Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            messagebox.showinfo("Export complete", f"Saved merged JSON to:\n{path}")
            return

        folder = filedialog.askdirectory(title="Choose output folder")
        if not folder:
            return
        out_dir = Path(folder)
        for source_path, prompts in self.prompts_by_file.items():
            safe_name = Path(source_path).stem + ".json"
            payload = {"prompts": [serialize_prompt(p, export_mode, variables, model_name) for p in prompts]}
            (out_dir / safe_name).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        messagebox.showinfo("Export complete", f"Saved {len(self.prompts_by_file)} JSON file(s) to:\n{folder}")


def build_root() -> tk.Tk:
    if DND_AVAILABLE and TkinterDnD is not None:
        return TkinterDnD.Tk()  # type: ignore[no-any-return]
    return tk.Tk()


def main() -> None:
    root = build_root()
    app = PromptTransformerApp(root)
    app.update_preview()
    root.mainloop()


if __name__ == "__main__":
    main()
