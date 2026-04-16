# Prompt Text → JSON Transformer (Desktop GUI)

A Python desktop app to convert prompt text files into JSON with:

- GUI desktop interface
- direct typing/pasting inside the app
- automatic plain-text prompt structuring with local Ollama JSON output
- heuristic fallback when Ollama is unavailable
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
- `ROLE`
- `GOAL`
- `CONTEXT`
- `ACTIONS`
- `CONSTRAINTS`
- `DELIVERABLES`

Prompts are separated with:

```txt
---
```

## Install

Python 3.10+ recommended.

### Required

This app uses the standard library Tkinter.

On Windows, Tkinter usually comes with Python.

### Optional local AI structuring with Ollama

Plain text typed into the app or loaded from files is now automatically upgraded into a specialized prompt structure when it does not already use labeled fields.

Recommended local model for this project:

```powershell
ollama pull qwen2.5:7b
```

Make sure the Ollama local server is installed and running before you start the app.

The app sends a schema-constrained request to:

```text
http://localhost:11434/api/chat
```

If Ollama is not available, the app still works by using a built-in heuristic fallback. The fallback keeps the app usable but the prompt restructuring quality is lower than the local LLM path.

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

## Type Prompt Text In The App

You can create prompt text directly inside the program without saving a `.txt` file first.

1. Click **Write In App**
2. Type or paste one or more prompt blocks into the **Source text preview / typed input** panel
3. Click **Convert Typed Text**
4. Review the JSON preview and validation results
5. Click **Export JSON** to save the generated output

The typed content behaves like another source in the left panel, alongside imported files and folders.

For plain text without labels, the app now auto-structures the request into fields such as:

- `role`
- `goal`
- `context`
- `actions`
- `constraints`
- `deliverables`

## How the export modes work

### 1. Raw archive
Stores parsed prompt fields, including the AI-structured fields and the preserved original raw text.

### 2. Dynamic template
Creates a reusable JSON structure and extracts variables like `{{name}}`. For plain text, it maps the structured prompt fields into developer/user chat messages automatically.

### 3. API-ready
Builds a final JSON object with variables resolved using the values in the **Variable values** panel.

## Validation rules included

The app checks for:

- missing `TITLE`
- missing prompt content or missing specialized `goal`/`actions`
- duplicate `ID`
- missing variable values in API-ready mode
- missing `SYSTEM` as a warning
- fallback structuring usage
- Ollama availability and structuring repair notes
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

## Plain Text Example

Input text:

```text
we should never again call steams original API.
This should have been changed already.
Plan for this change on inventory calls,
have only SteamWebAPI be used in the entire platform,
theres no more need for the other APIs (CSFloat and Steam's original API) except for login,
auth etc. But regarding inventory and Item information, its only SteamWebAPI
```

The app now aims to convert that into a specialized JSON shape like:

```json
{
  "title": "Steamwebapi Inventory Standardization",
  "role": "senior refactoring agent",
  "goal": "Standardize the platform to use only SteamWebAPI for inventory and item information.",
  "context": "Steam's original API and CSFloat should no longer be used for inventory or item data. Login and authentication flows remain exceptions.",
  "actions": [
    "Find every inventory-related call in the project.",
    "Find every item information call in the project.",
    "Replace those calls with SteamWebAPI."
  ],
  "constraints": [
    "Do not keep mixed implementations for inventory or item data.",
    "Do not change auth flows unless necessary."
  ],
  "deliverables": [
    "List of changed files",
    "Summary of replaced endpoints",
    "Confirmation that SteamWebAPI is now the single source for inventory and item data"
  ]
}
```
