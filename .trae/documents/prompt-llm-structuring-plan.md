# Prompt LLM Structuring Plan

## Summary

Upgrade the desktop prompt transformer so plain text is automatically rewritten into a specialized prompt structure instead of being wrapped as a single `user` message. The implementation will use a local free AI through Ollama with schema-constrained JSON output, preserve the original raw text, restyle the GUI with blue surfaces and green action buttons, and keep the current export pipeline compatible with the new structured prompt data.

## Current State Analysis

- `prompt_json_transformer_app.py` currently has two behaviors only:
  - If labeled fields such as `SYSTEM:` or `USER:` are present, `parse_block()` stores them.
  - If no labeled fields are present, `parse_block()` stores the entire block as `prompt` with a generated title/id.
- The current serialization logic in `serialize_prompt()` only knows how to emit:
  - raw stored fields,
  - chat-style `template.messages`,
  - or API-ready `input` messages.
- The current plain-text path explains the bad result shown in `analysis/conversao_app.txt`: the text is preserved almost exactly and exported as a single `user` message with no instruction specialization layer.
- `analysis/conversao_gpt_externa.txt` demonstrates the target behavior more clearly: extract intent and normalize it into fields like `role`, `goal`, `context`, `actions`, `constraints`, and `deliverables`.
- The app currently uses `ttk` plus classic Tk widgets (`Listbox`, `ScrolledText`). Because of this mixed widget set, color theming must cover both `ttk.Style()` and direct widget background/foreground configuration.
- The repo currently has no AI provider integration. `requirements.txt` only lists `tkinterdnd2`.

## Assumptions And Decisions

- Plain text without labeled fields will be auto-upgraded by default, as requested.
- Structured prompts will use `role`, `goal`, `context`, `actions`, `constraints`, and `deliverables` as the canonical specialization schema.
- Existing export modes will remain available, but they will now serialize richer data for plain-text inputs.
- The AI integration will use a new local Ollama client module over the local HTTP API (`http://localhost:11434/api/chat`) using the Python standard library instead of adding a required Python package.
- The local model default will be changed from `gpt-5` to an Ollama-oriented default suitable for structured outputs. The implementation should make this user-editable in the existing model field.
- A deterministic fallback will exist when Ollama is unavailable or returns invalid data, so conversion still works offline with reduced quality.
- The original raw text will be preserved in the prompt record for traceability and comparison.

## Proposed Changes

### 1. Add a dedicated AI structuring module

**File:** `prompt_structuring_ai.py` (new)

- Create a small Ollama client using `urllib.request` or equivalent standard-library HTTP support.
- Define the target JSON schema for:
  - `role`
  - `goal`
  - `context`
  - `actions`
  - `constraints`
  - `deliverables`
  - optional support metadata such as `title` and `tags` if the model can infer them reliably
- Send `stream: false`, low temperature, and a schema in the `format` field so the model is constrained to valid JSON.
- Build the system/user instructions so the model:
  - converts raw prompt intent into specialized prompt fields,
  - does not wrap the response in markdown,
  - does not invent unsupported structure outside the schema,
  - preserves the original intent rather than answering the prompt.
- Validate the returned JSON locally before using it.
- Provide a pure-Python fallback transformer that extracts a basic structure heuristically when Ollama is unavailable, times out, or returns invalid content.
- Expose a narrow function such as `structure_plain_prompt(raw_text: str, model: str) -> dict[str, Any]`.

### 2. Enrich the prompt parsing pipeline

**File:** `prompt_json_transformer_app.py`

- Extend `PromptRecord.variables` so variable discovery also inspects the new structured fields, especially lists like `actions` and `constraints`.
- Update `parse_block()` so the no-structured-fields branch no longer stores only:
  - `prompt`
  - generated `title`
  - empty `tags`
- Instead, it should:
  - preserve the original text in a field such as `original_text`,
  - call the new AI structuring function,
  - merge the returned specialized fields into `data`,
  - synthesize compatibility fields needed by the existing export flow.
- Add helpers to normalize AI output safely:
  - ensure list fields are lists of strings,
  - trim whitespace,
  - fill missing optional fields with safe defaults,
  - derive a readable title when absent.

### 3. Make structured prompts compatible with current export modes

**File:** `prompt_json_transformer_app.py`

- Add a builder that maps the canonical specialized structure into chat messages for reuse by `Dynamic template` and `API-ready`.
- Recommended mapping:
  - `developer/system` message: role + goal + context + constraints + required output behavior
  - `user` message: actions + deliverables + preserved original request
- Update `prompt_to_messages()` to prefer the specialized fields when present, while still supporting legacy `SYSTEM/USER/ASSISTANT/PROMPT` inputs.
- Update `serialize_prompt()`:
  - `Raw archive` should include the structured fields and preserved `original_text`.
  - `Dynamic template` should keep `template.messages` but build them from the specialized structure when available.
  - `API-ready` should keep `input` messages but use the same specialized mapping and current variable resolution rules.
- Keep merge/export behavior unchanged so existing usage patterns still work.

### 4. Improve validation and transparency

**File:** `prompt_json_transformer_app.py`

- Extend `validate_prompts()` so structured plain-text conversions report useful warnings/errors:
  - missing `goal`,
  - empty `actions`,
  - AI fallback used,
  - Ollama unavailable,
  - invalid structured response repaired locally.
- Update the validation panel text so the user can see whether a prompt was AI-structured or fallback-structured.
- Keep validation non-blocking for warnings so users can still export.

### 5. Update the GUI for the new workflow and requested colors

**File:** `prompt_json_transformer_app.py`

- Apply a blue visual theme to the root window and container frames.
- Style action buttons in green using `ttk.Style()` and map pressed/active states to darker green shades.
- Configure classic Tk widgets that ignore `ttk` theme defaults:
  - `Listbox`
  - `ScrolledText`
- Improve labels/tooltips/help copy so the app explains that plain text is now auto-structured into a specialized AI prompt JSON.
- Update the default model field to an Ollama model name suitable for structured tasks.

### 6. Document the new local-AI setup

**File:** `README_prompt_transformer_app.md`

- Replace the current “future upgrade” wording with the actual behavior.
- Add a setup section for Ollama:
  - install Ollama,
  - pull the recommended free local model,
  - confirm the local server is running.
- Explain the fallback mode so the app still works without Ollama but with lower-quality restructuring.
- Add an example showing the before/after behavior for plain text similar to the two files in `analysis/`.

## Verification Steps

1. Manual parsing check
   - Load or paste the text from `analysis/conversao_app.txt`.
   - Confirm the preview is no longer a single raw `user` message.
   - Confirm the JSON contains `role`, `goal`, `context`, `actions`, `constraints`, and `deliverables`.

2. Compatibility check
   - Load `sample_prompts.txt`.
   - Confirm labeled prompts still parse normally and export correctly in all three export modes.

3. Fallback check
   - Simulate Ollama unavailable.
   - Confirm plain text still converts into a minimal structured prompt and the validation panel reports fallback usage.

4. UI check
   - Confirm the main window/background areas are blue-toned.
   - Confirm action buttons are green and readable.
   - Confirm `Listbox` and `ScrolledText` widgets visually match the new palette.

5. Export check
   - Confirm merged export and per-file export still save valid JSON.
   - Confirm `Dynamic template` and `API-ready` use the specialized structure for converted plain text.

6. Diagnostics check
   - Run Python diagnostics on the edited files after implementation.
   - Resolve any syntax or type issues introduced by the refactor.

## Notes For Execution

- Prefer the local Ollama HTTP API over a new Python dependency to minimize setup friction.
- Use schema-constrained JSON output rather than plain “respond in JSON” prompting, because the current problem is reliability and consistency.
- Keep all existing labeled prompt formats working exactly as they do now; the new logic should only enrich unlabeled plain text and improve serialization.
