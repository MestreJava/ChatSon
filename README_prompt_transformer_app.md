# Prompt Text → JSON Transformer (Desktop GUI)

A Python desktop app to convert prompt text files into JSON with:

- GUI desktop interface
- automatic validation of missing fields
- variable detection like `{{name}}`, `{{topic}}`, `{{language}}`
- drag-and-drop file/folder conversion
- batch folder scanning
- export modes:
  - Raw archive
  - Dynamic template
  - API-ready

## Supported input fields

Use blocks like this in `.txt`, `.md`, `.prompt`, or `.prompts` files:

```txt
TITLE: Email Writer
ID: email_writer_001
SYSTEM: You are a professional email assistant.
USER: Write an email to {{name}} about {{topic}} in {{language}}.
TAGS: email, business

---
TITLE: Code Reviewer
SYSTEM: You are a senior software engineer.
USER: Review this code and suggest improvements.
TAGS: code, review, python
```

Supported fields:

- `TITLE`
- `ID`
- `SYSTEM`
- `USER`
- `ASSISTANT`
- `DESCRIPTION`
- `TAGS`
- `CATEGORY`
- `PROMPT`

Prompts are separated with:

```txt
---
```

## Install

Python 3.10+ recommended.

### Required

This app uses the standard library Tkinter.

On Windows, Tkinter usually comes with Python.

### Optional drag-and-drop support

To enable drag-and-drop from Explorer into the app:

```powershell
python -m pip install tkinterdnd2
```

If you do not install it, the app still works using **Add Files** and **Add Folder**.

## Run

```powershell
python .\prompt_json_transformer_app.py
```

## How the export modes work

### 1. Raw archive
Stores parsed prompt fields almost exactly as found.

### 2. Dynamic template
Creates a reusable JSON structure and extracts variables like `{{name}}`.

### 3. API-ready
Builds a final JSON object with variables resolved using the values in the **Variable values** panel.

## Validation rules included

The app checks for:

- missing `TITLE`
- missing `USER` or `PROMPT`
- duplicate `ID`
- missing variable values in API-ready mode
- missing `SYSTEM` as a warning
- prompts with no dynamic variables as informational notes

## Example variable JSON

Paste this into the **Variable values (JSON object)** panel:

```json
{
  "name": "Maria",
  "topic": "project update",
  "language": "English"
}
```

## Suggested next upgrades

- per-prompt editing inside the GUI
- schema validator for structured model output
- one-click export ZIP
- EXE build with PyInstaller
- direct OpenAI API send/test button
- import/export profiles for different prompt formats
