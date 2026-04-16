from __future__ import annotations

import json
import os
import re
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD  # type: ignore
    DND_AVAILABLE = True
except Exception:
    DND_AVAILABLE = False
    TkinterDnD = None  # type: ignore
    DND_FILES = None  # type: ignore


SUPPORTED_EXTENSIONS = {".txt", ".md", ".prompt", ".prompts"}
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
        for key in ("system", "user", "assistant", "prompt", "description"):
            value = self.data.get(key)
            if isinstance(value, str):
                found.update(RE_VARIABLE.findall(value))
        return sorted(found)


def normalize_key(key: str) -> str:
    key = key.strip().lower().replace(" ", "_")
    return FIELD_ALIASES.get(key, key)


def parse_tags(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[;,]", value) if item.strip()]


def render_template(text: str, variables: dict[str, Any]) -> str:
    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        value = variables.get(name)
        return match.group(0) if value is None else str(value)

    return RE_VARIABLE.sub(repl, text)


def parse_block(block: str, index: int, source_path: str) -> PromptRecord:
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
        data[current_key] = parse_tags(value) if current_key == "tags" else value
        current_key = None
        buffer = []

    for line in lines:
        match = RE_FIELD.match(line)
        if match:
            raw_key, raw_value = match.groups()
            key = normalize_key(raw_key)
            if key in {
                "title",
                "id",
                "system",
                "user",
                "assistant",
                "description",
                "tags",
                "category",
                "prompt",
            }:
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
        data = {
            "id": f"prompt_{index:03d}",
            "title": f"Prompt {index}",
            "prompt": raw_text,
            "tags": [],
        }
    else:
        data.setdefault("id", f"prompt_{index:03d}")
        data.setdefault("title", f"Prompt {index}")
        data.setdefault("tags", [])

    return PromptRecord(source_path=source_path, block_index=index, data=data)


def parse_text_to_prompts(text: str, source_path: str) -> list[PromptRecord]:
    blocks = [b.strip() for b in RE_BLOCK_SEPARATOR.split(text) if b.strip()]
    if not blocks and text.strip():
        blocks = [text.strip()]
    return [parse_block(block, i + 1, source_path) for i, block in enumerate(blocks)]


def prompt_to_messages(prompt: PromptRecord, variables: dict[str, Any] | None = None) -> list[dict[str, str]]:
    variables = variables or {}
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
    model_name: str = "gpt-5",
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
        if not title:
            issues.append({"level": "ERROR", "where": where, "message": "Missing title."})

        has_prompt_content = bool(str(prompt.data.get("user", "")).strip() or str(prompt.data.get("prompt", "")).strip())
        if not has_prompt_content:
            issues.append({
                "level": "ERROR",
                "where": where,
                "message": "Missing USER or PROMPT content.",
            })

        if id_counts.get(prompt.id, 0) > 1:
            issues.append({"level": "ERROR", "where": where, "message": f"Duplicate id '{prompt.id}'."})

        if not prompt.data.get("system"):
            issues.append({
                "level": "WARN",
                "where": where,
                "message": "No SYSTEM field. This is allowed, but you may want one for instruction quality.",
            })

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
        self.prompts_by_file: dict[str, list[PromptRecord]] = {}
        self.current_preview_file: str | None = None

        self.export_mode_var = tk.StringVar(value="Dynamic template")
        self.model_var = tk.StringVar(value="gpt-5")
        self.merge_var = tk.BooleanVar(value=True)

        self._build_ui()
        self._bind_drag_and_drop()

    def _build_ui(self) -> None:
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")

        ttk.Button(top, text="Add Files", command=self.add_files).pack(side="left", padx=4)
        ttk.Button(top, text="Add Folder", command=self.add_folder).pack(side="left", padx=4)
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

        ttk.Label(top, text="Model:").pack(side="left", padx=(18, 4))
        self.model_entry = ttk.Entry(top, textvariable=self.model_var, width=12)
        self.model_entry.pack(side="left")

        ttk.Checkbutton(top, text="Merge all files into one export", variable=self.merge_var).pack(
            side="left", padx=(18, 4)
        )

        tip = ttk.Label(
            self.root,
            text=(
                "Supported fields: TITLE, ID, SYSTEM, USER, ASSISTANT, DESCRIPTION, TAGS, CATEGORY, PROMPT. "
                "Separate prompts with --- . Optional drag-and-drop works with tkinterdnd2."
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
        self.files_list = tk.Listbox(left, exportselection=False)
        self.files_list.pack(fill="both", expand=True)
        self.files_list.bind("<<ListboxSelect>>", self.on_file_select)

        ttk.Label(middle, text="Source text preview").pack(anchor="w")
        self.source_text = ScrolledText(middle, wrap="word")
        self.source_text.pack(fill="both", expand=True)

        ttk.Label(right, text="Generated JSON preview").pack(anchor="w")
        self.json_text = ScrolledText(right, wrap="word")
        self.json_text.pack(fill="both", expand=True)

        bottom = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        bottom.pack(fill="both", expand=False, padx=8, pady=(0, 8))

        variables_frame = ttk.Frame(bottom, padding=8)
        validation_frame = ttk.Frame(bottom, padding=8)
        bottom.add(variables_frame, weight=1)
        bottom.add(validation_frame, weight=2)

        ttk.Label(variables_frame, text="Variable values (JSON object)").pack(anchor="w")
        self.variables_text = ScrolledText(variables_frame, height=10, wrap="word")
        self.variables_text.pack(fill="both", expand=True)
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

    def clear_all(self) -> None:
        self.files = []
        self.prompts_by_file = {}
        self.current_preview_file = None
        self.files_list.delete(0, "end")
        self.source_text.delete("1.0", "end")
        self.json_text.delete("1.0", "end")
        self.validation_text.delete("1.0", "end")

    def refresh_all(self) -> None:
        self.prompts_by_file.clear()
        errors: list[str] = []
        for path in self.files:
            try:
                text = load_text_file(path)
                self.prompts_by_file[path] = parse_text_to_prompts(text, path)
            except Exception as exc:
                errors.append(f"[ERROR] {path}: {exc}")

        self.files_list.delete(0, "end")
        for path in self.files:
            count = len(self.prompts_by_file.get(path, []))
            self.files_list.insert("end", f"{Path(path).name}  ({count} prompt blocks)")

        if self.files:
            self.files_list.selection_clear(0, "end")
            self.files_list.selection_set(0)
            self.files_list.event_generate("<<ListboxSelect>>")
        else:
            self.source_text.delete("1.0", "end")
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
        if index >= len(self.files):
            return
        path = self.files[index]
        self.current_preview_file = path
        try:
            source = load_text_file(path)
        except Exception as exc:
            source = f"Unable to read file: {exc}"
        self.source_text.delete("1.0", "end")
        self.source_text.insert("1.0", source)
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
        prompts = self.preview_prompts()
        try:
            variables = self.parse_variables_json()
            export_mode = self.export_mode_var.get()
            model_name = self.model_var.get().strip() or "gpt-5"
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
        if not self.prompts_by_file:
            messagebox.showwarning("Nothing to export", "Add files or a folder first.")
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

        model_name = self.model_var.get().strip() or "gpt-5"
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
