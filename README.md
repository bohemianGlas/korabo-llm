## Notice
>This program was coded with the assistance of AI.
>Use it at your own risk.
>The English text is machine-translated, and I am not a native English speaker.

# korabo_llm — Master LLM × Sub LLM Collaboration System

*(日本語版は [README_JPN.md](README_JPN.md) をご覧ください / Japanese version: [README_JPN.md](README_JPN.md))*

korabo_llm is a local-first web app where a **Master LLM** (narrator / director) orchestrates
multiple **Sub LLMs** (characters), each with its own role prompt and persistent Markdown memory,
to run agent simulations and collaborative story generation.

- **Master LLM** — Reads the master prompt and the situation prompt, calls the right role at the
  right time, integrates their replies, and composes the **main log** (the story).
- **Sub LLM (role)** — Runs from its own role prompt and owns an external memory Markdown file
  (`memo_md`) that it can write to.
- **WebUI (Gradio)** — Real-time display, full configuration editing, and live user intervention
  from the browser. Switchable between **Japanese / English**.

## Setup

```bash
pip install -r requirements.txt
python korabo_llm.py
```

The WebUI opens at http://127.0.0.1:7860.

The default endpoint is `mock` (a built-in dummy that needs no LLM), so you can press **▶ Start**
right after installing to see the whole flow working.

- **On first launch, if `config/config.jsonc` does not exist it is auto-generated from
  `config/config.example.jsonc`.** `config.jsonc` is git-ignored, so API keys typed into the WebUI
  are never committed.
- **Prefer environment variables** (each endpoint's `api_key_env`) over hard-coding API keys in
  `config.jsonc`.

### Command-line options

```bash
python korabo_llm.py --listen 0.0.0.0 --port 7860   # expose on LAN
python korabo_llm.py --log-level DEBUG               # verbose console logs
python korabo_llm.py --no-color --no-tokens          # plain logs, no per-turn token lines
```

### You can check the command-line options with
```
python korabo_llm.py --help
```
. They are as follows:

```
options:
  -h, --help            show this help message and exit
  --listen ADDR         Address to bind to. To make it accessible on the LAN, use --listen 0.0.0.0 (default: 127.0.0.1)
  --port PORT           Listening port (default: 7860)
  --share               Generate a temporary public URL for Gradio (gradio.live)
  --log-level {DEBUG,INFO,WARNING,ERROR}
                        Console log detail level (default: INFO)
  --no-color            Disable colored output
  --no-tokens           Disable display of token usage per turn
```
```
python korabo_llm.py --log-level DEBUG     # For debugging (includes thought processes and inner monologue)
python korabo_llm.py                       # Default = INFO
python korabo_llm.py --log-level WARNING   # Virtually silent (only logs errors)
```

## UI language

Use **"言語 / Language"** at the top-right to switch between **日本語 / English** (the page reloads
and rebuilds the UI in the chosen language).
Note: **the UI language does not change the generated story's language** — output language is driven
by your prompts and models.

## Connecting to LLMs

Register OpenAI-compatible endpoints in the **🔌 Endpoints** tab, then pick the endpoint/model in
the **🧠 Master** and **🎭 Roles** tabs.

| Endpoint | base_url | API key |
|---|---|---|
| OpenRouter | `https://openrouter.ai/api/v1` | env `OPENROUTER_API_KEY` or direct |
| LM Studio | `http://localhost:1234/v1` | not required (any string) |
| OpenAI | `https://api.openai.com/v1` | env `OPENAI_API_KEY` or direct |
| mock | `mock` | not required (dummy for testing) |

- API keys support both **direct value** and **environment-variable reference**.
- Master and each role can use **different endpoints/models** (e.g. a large OpenRouter model for the
  Master, a local LLM for the roles).
- If a role's endpoint/model is unset, the `sub_defaults` values are used.

### Local model sizing (llama.cpp)

Context stays bounded regardless of story length because the history windows are fixed
(**Master 40 events / Sub 20 events**); the only steadily-growing input is each role's memory note
(`memo_md`, sent in full every call). Estimated context use (Japanese ≈ 1.2–1.6 chars/token):

| | Typical | Long story / large memory |
|---|---|---|
| **Master input** | 11,000–15,000 tok | 18,000–25,000 tok |
| **Sub input** | 7,000–9,700 tok | 10,000–14,000 tok |

**Recommended `--ctx-size` (n_ctx):** Master **16K min / 24K** for long-form; Sub **8K min / 12K**.

**`--parallel`** — the app calls Master → Sub **sequentially** on a single thread (roles never run
concurrently), and llama.cpp splits `n_ctx` across slots, so:
- **Two dedicated servers (recommended):** each `--parallel 1`.
- **One server for both:** `--parallel 2` and **double the total `n_ctx`** (e.g. 32K → 16K per slot),
  so Master and Sub keep separate cached slots and alternating calls don't re-prefill.
- No need to scale `--parallel` with the number of roles.

**`--batch-size` / `--ubatch-size`** — prefill speed vs VRAM only (not correctness). `-b 2048 -ub 512`
(defaults) is fine; raise `-ub 1024` to speed up prefill of long prompts if VRAM allows.

```bash
# Dedicated Master / Sub servers
llama-server -m master.gguf --ctx-size 16384 --parallel 1 -b 2048 -ub 512
llama-server -m sub.gguf    --ctx-size 12288 --parallel 1 -b 2048 -ub 512
# One server for both
llama-server -m shared.gguf --ctx-size 32768 --parallel 2 -b 2048 -ub 512
```

### Local model sizing (vLLM)

This is a **single-user, strictly sequential** workload (Master → Sub, never concurrent), so each
turn is a large **prefill** (Master 10–25K tok, Sub 7–14K tok) plus a small generation (~500–600 tok).
There are no competing concurrent decodes to protect, so tune toward fast prefill.

- **`--max-model-len`**: same as n_ctx above — Master **16384–24576**, Sub **12288**.
- **`--max-num-batched-tokens`**: set high enough to prefill a full prompt in few chunks (lowers TTFT).
  Master **16384** (8192 if VRAM-tight), Sub **8192**. A single sequence's KV need is modest, so a
  larger value is affordable. With chunked prefill (default), it may be below `--max-model-len` (the
  prompt is just split). On very tight VRAM the default is fine — only TTFT grows, not correctness.
- **`--max-num-seqs`**: 1–2 is plenty (only one request is ever in flight). Use 2 when one server hosts both.
- **`--enable-prefix-caching`** (big win): the stable head of the system prompt (base prompts + work
  master prompt + fixed sections) is reused across turns. Note the memory note (`memo_md`) sits
  mid-prompt, so caching helps up to the memory section.

```bash
# Dedicated Master / Sub servers
vllm serve <master-model> --max-model-len 16384 --max-num-batched-tokens 16384 \
    --max-num-seqs 2 --enable-prefix-caching
vllm serve <sub-model>    --max-model-len 12288 --max-num-batched-tokens 8192 \
    --max-num-seqs 1 --enable-prefix-caching
# One server for both
vllm serve <shared-model> --max-model-len 24576 --max-num-batched-tokens 16384 \
    --max-num-seqs 2 --enable-prefix-caching
```

## Usage

### Run tab

1. Enter a **situation prompt**.
2. Choose an **execution mode**:
   - **One step at a time** — pauses each turn; advance with **⏭ Step**.
   - **Run until N turns** — auto-runs to N turns (ignores the Master's "finish").
   - **Master decides to stop (with limit)** — stops when the Master declares the end, or at the turn limit.
   - **Master decides to stop (unlimited)** — runs until the Master declares the end.
   - **Infinite mode** — runs until you stop it.
3. Press **▶ Start**. The main log (Master's composition) and the detail stream (Master thoughts,
   sub replies, memory updates) update in real time.
4. While running, use **⚡ Send intervention** to inject events / change the situation etc.
   (applied on the next Master turn).
5. **⏩ Continue** resumes a finished/stopped story with new mode/turns; **🔧 Change run settings**
   changes mode/turns live. For these, the turn number means "N more turns from now".

### Other tabs

- **📜 Logs** — Browse past sessions' `main.md` (composition) / `full.md` (everything).
- **🎭 Roles** — Add/edit/delete roles; edit role prompts and memory notes (`memo_md`).
- **🧠 Master** — Edit the master prompt and the Master's endpoint/model/temperature.
- **🔌 Endpoints** — CRUD endpoints and test connections.
- **🎁 Presets** — Save/switch a whole "work set", and export/import single-file bundles.

## Architecture

```
SituationPrompt ─┐
MasterPrompt ────┤
                 ▼
             MasterLLM ⇄ SubLLM1 ⇄ memo_md1 (RolePrompt1)
                 ⇅       SubLLM2 ⇄ memo_md2 (RolePrompt2)
                 ⇅       SubLLM…
                 ▼
          main.md / full.md / events.jsonl
```

- A one-turn graph — "Master decides → (optionally) a Sub replies → back to Master" — is built with
  **LangGraph**, and a session controller loops it according to the selected mode.
- Master ⇔ Sub exchanges use structured JSON (`MasterDecision` / `SubResponse`). To work with local
  models that don't support function-calling, this is done via prompt instructions plus robust
  parsing; if parsing fails, the whole text is treated as narration/speech so the run never stalls.
- **Responsibility boundaries** (system-wide base prompts): the Master manages the world and
  outcomes but never decides a character's speech/decisions/inner thoughts; Subs act as
  limited-knowledge agents that write only their own *attempts*, never outcomes. Sub context is
  assembled as a **scene packet** — invisible information (other factions' secrets, others' inner
  voice, events from scenes the character was absent from) is **excluded before it is sent**, not
  forbidden afterwards. Role memories support a structured 7-section format with tag-based routing
  (［事実］［伝聞］［推測］…) and exact-duplicate suppression — old free-form memories keep working.
  See [docs/prompt-and-state-architecture.md](docs/prompt-and-state-architecture.md).

### Master ⇔ Sub protocol

**MasterDecision** (one Master turn):
```json
{
  "thought": "internal reasoning (full log only)",
  "narration": "prose written to the main log (optional)",
  "action": "call_sub | continue | finish",
  "target_role": "role id when action is call_sub",
  "message_to_role": "situation/question passed to that role"
}
```

**SubResponse** (a character's reply):
```json
{
  "speech": "words said aloud",
  "action": "behavior / gesture / expression",
  "inner_voice": "inner thoughts (not spoken)",
  "memory_append": "note to append to this role's memo_md (optional)"
}
```

### Directory layout

```
├── korabo_llm.py               # entry point
├── config/config.example.jsonc # sample config (shipped / tracked)
├── config/config.jsonc         # actual config (auto-generated from example / git-ignored)
├── korabo/                     # core logic
│   ├── schemas.py              #   data models for config & protocol
│   ├── config.py               #   JSONC read/write
│   ├── llm_client.py           #   OpenAI-compatible client + JSON parsing + Mock
│   ├── master.py / sub.py      #   prompt building & response parsing
│   ├── graph.py                #   LangGraph graph
│   ├── session.py              #   session controller (modes, intervention, stop)
│   ├── memory.py               #   memo_md read/write
│   ├── logger.py               #   Markdown logs + events.jsonl
│   ├── applog.py               #   console logging
│   ├── i18n.py                 #   JA/EN UI strings
│   └── presets.py              #   preset save/apply + bundle export/import
├── ui/                         # Gradio WebUI (one module per tab)
└── data/
    ├── master/master_prompt.md # master prompt
    ├── roles/<id>.md           # role prompts
    ├── memories/<id>.md        # role external memory (memo_md)
    └── templates/              # prompt templates (JA) + templates/en (EN)

logs/session_*/                 # session logs (project root)
presets/<id>/                   # "work set" presets (optional)
```

## Logs

Each session creates `logs/session_YYYYMMDD-HHMMSS/` at the **project root**:

- `main.md` — the Master's final composition (the story).
- `full.md` — full record incl. Master thoughts, sub calls, raw sub replies, memory updates.
- `events.jsonl` — structured events (for programmatic analysis).

## Splitting the master prompt (include)

Instead of writing everything in one file, you can split the master prompt into child files.
Put either of the following in `master_prompt.md` and the child files are read and appended
(if none is present, only the body is used):

```markdown
@include: outline.md, style.md, note.md
```

or under a heading:

```markdown
## Reference files
1. `outline.md` — content, goals, constraints
2. `style.md`   — tone, voice, things to avoid
3. `note.md`    — prior decisions, proper nouns, continuity notes
```

Paths are resolved relative to the folder containing `master_prompt.md`.

## Presets (switch a whole "work set")

In the **🎁 Presets** tab you can save the master prompt (+ include children), roles, memories, and
"flavor" settings together under `presets/<id>/` and switch them with one click.

- **Re-point model** — Applying a preset points the config directly at files inside `presets/<id>/`.
  Play-time memory accumulates inside that preset, so switching away and back preserves each preset's memory.
- **Endpoints (URL / API key) do not switch** — they stay in `config.jsonc` as machine-local settings.
- "Save current setup" turns your current `data/` into a preset.
- **Bundle** — Export/import a preset as a single readable Markdown file `<id>.preset.md`
  (for sharing / backup). The working format stays a directory; endpoints are not included in a bundle.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

All tests run offline with mock/scripted LLM clients (visibility isolation, scene packets,
memory routing/dedup, prompt assembly, and an end-to-end session).
Note: `full.md` is by design the *complete* debug log — it contains inner voices, faction
secrets and scene-packet summaries. Share `main.md` if you only want the story.

## License / Notes

- The bundled prompts and roles under `data/` are Japanese samples; see `data/templates/en/` for
  simple English templates.
- This is a hobby/creative tool. Use a model/endpoint you are authorized to use, and keep API keys
  out of version control.
