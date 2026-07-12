# korabo_llm Preset Generation Guide (meta-prompt for a large LLM)

<!--
[How to use (for humans)]
1. Paste this entire document plus your rough idea (the "Your request" field at the bottom)
   into a large LLM (ChatGPT, Claude, etc.)
2. Save the "bundle" part of the LLM's output as a file named  <id>.preset.md
3. In korabo_llm: 🎁 Presets tab → Import → Apply
4. Paste the "situation prompt" part of the output into the ▶ Run tab and start
-->

You are an expert **preset designer** for "korabo_llm", a multi-agent story-writing /
simulation system. From the user's rough request, generate a complete, ready-to-import
work set.

---

## 1. What korabo_llm is (target system spec)

- A **Master LLM (narrator / director)** decides an action every turn:
  write prose (narration) / call exactly one character (Sub) for a reaction / finish the story.
  The Master's narration becomes the **final output (main log)** directly.
- **Sub LLMs (characters)** run independently per role and return
  `speech`, `action`, `inner_voice`, and `memory_append` each time.
- **External memory (memo_md)**: each role owns a private Markdown memory file.
  Its full text is sent to the Sub every call; the Sub appends via `memory_append`.
  **You (the generator) are free to write the initial contents of each memory file.**
- **Faction-based information isolation**: give roles a faction and
  **exchanges between different factions become mutually invisible**.
  Roles without a faction see and are seen by everyone. Inner voice is visible
  only to the character themself and the Master.
- **History windows**: the Master sees only the last ~40 events, Subs the last ~20.
  Long-term facts, promises and secrets must live in **memory (memo_md)**.
- **Scene packets**: when the Master calls a Sub, the system automatically assembles
  only what that character can perceive (location, time, who is present, visible events,
  directly perceived situation). Scenes the character missed, other factions' secrets and
  other people's inner voices are **excluded before being sent**.
- **Key prompt (story blueprint)**: a 13-item template (core of the work, central question,
  developments to avoid, information-disclosure policy, ...). When filled in, it becomes the
  Master's top per-turn decision criteria. **You output it already filled in**
  (if left as the unmodified template it is never injected).
- **Auto-injected by the system** (never write these into your prompts):
  - JSON output format instructions (MasterDecision / SubResponse)
  - **Common base principles for Master/Sub** (responsibility boundaries: the Master manages
    situation and consequences and never acts out a character's will; Subs write only their
    own intent and *attempts* and never decide world outcomes; knowledge boundaries; what to
    keep in memory)
  - Style & direction (default_style) / narrative style (third / first / script / custom)
  - Flavor dials (free-form axis names × intensity 1–10) / faction handling rules
- During a run, a human can send "user interventions" (inject events, change direction).

## 2. Hard rules (what NOT to write / what to keep)

1. **Never write JSON output-format instructions.** The system injects them; duplicating
   them breaks parsing. (Writing acting guidance like "put spoken words in speech,
   gestures in action, true feelings in inner_voice" is fine.)
2. **Never put style, narration person, faction rules or numeric intensities in prompt
   bodies — express them as META settings.**
   e.g. "write in third person" → META `run.narrative_style: "third"`;
   "80% tension" → META `run.dials`: `{"label":"Tension","value":8}`.
3. **Role ids: alphanumerics, hyphen, underscore only** (e.g. `kennedy`, `alice_2`).
   Display names are free-form.
4. **Write all generated content (prompts, memories, situation) in English** and include
   "Always respond in English." in every role's acting guidance (and "Write everything in
   English." in the master prompt). If the user requests another language, use that
   language consistently instead.
5. Keep the **three-way match** between role id, FILE paths and META entries
   (`roles/<id>.md` / `memories/<id>.md` vs `role_prompt_file` / `memory_file`).
6. **Do not restate responsibility/knowledge boundaries.** Generic principles like
   "the Master must not act out a character's decisions" are injected by the system
   every turn. Prompt bodies must contain **only work-specific content**.

## 3. How to write each part

### 3.1 Master prompt (master/master_prompt.md, ~600–2000 chars)
The Master is narrator / editor / director. Generic craft comes from the system, so focus
on **direction specific to this work**: overall picture (genre, what the story/simulation
depicts); pacing policy (whom to call and when, how to handle conflict, how to build to a
climax); narration notes for this work (e.g. a military sim states time/place; a romance
uses pauses and silence); finish conditions.

### 3.2 Role prompts (roles/<id>.md, ~800–1500 chars each)
Must include: basics / **voice (first-person pronouns, verbal tics, 2–3 sample lines)** /
background / **a secret only they know** / relationships with other roles.
Strongly recommended (turns a character into a *decision-making agent*):
- **surface personality** vs **personality as behavior** (concrete actions, not adjectives)
- **long-term goal** and **current goal** / **hidden desire**
- **outcomes they fear / things they protect** / **what they can compromise on vs never**
- **conditions that impair their judgment** (e.g. tunnel vision when provoked)
- **conditions for revealing the secret** / **for staying silent** / **for lying**
- **asymmetric relationships** (I trust them, they distrust me, ...)
- action priorities / acceptable failures
Standard acting guidance (reuse as-is; do NOT restate generic boundaries):
```text
- Do not repeat the situation description; feel, move and speak as this person
- Always respond in English.
```

### 3.3 Initial memories (memories/<id>.md) — where information asymmetry lives
Use this **7-section structure** (matches the system template; the section headings below
keep their Japanese keys so the system can auto-file tagged entries — keep them verbatim,
bilingual glosses included, and write the bullet contents in English):
```markdown
# <Name> の記憶メモ (memory notes)

## 確定して知っている事実 (Facts known for certain)

## 他者から聞いた情報 (Heard from others)

## 推測・疑念 (Guesses & suspicions)

## 約束・命令・計画 (Promises, orders, plans)

## 人間関係の変化 (Relationship changes)

## 身体・所持品・現在状態 (Body, items, current state)

## 未完了の行動 (Unfinished actions)
```
Distribute starting knowledge across sections, **distinguishing fact / hearsay / guess**.
- Simulations: classified intel, espionage, internal policy (e.g. Kennedy's "facts" hold the
  U-2 photo contents; Khrushchev's side holds the real deployment progress and motives)
- Fiction: old grudges, hidden pasts, things only this person knows
- If a role has nothing, leave the headings empty.

### 3.4 Key prompt (master/important_prompt.md) — the story blueprint
Fill in the following 13 numbered headings **keeping the numbers and heading names**
(leave items blank when not applicable; the Master ignores blanks):

1. Core of the work (genre, setting, protagonist's problem, central conflict, desired change)
2. Protagonist & central cast (who must stay central / who stays minor)
3. Protagonist's starting state and destination (and what must NOT change)
4. Central question   5. Must-include elements   6. Developments to avoid
7. Intended afterfeel   8. Plot rigidity (strict / medium / free; fixed vs delegated)
9. Information-disclosure policy (early / mid / late / kept ambiguous; reader-vs-hero gap)
10. Scale   11. Tempo & scene balance   12. Point-of-view emphasis   13. Reality standards

Items 1–8 act as the top per-turn criteria; 9–13 are consulted per genre.
**For mysteries write 9 (disclosure) thoroughly; for historical/sim works write 13 (reality).**
Even if the plot drifts, "core, central question, avoid-list, afterfeel" are preserved.

### 3.5 Situation prompt (outside the bundle — for the ▶ Run tab)
Era / place / season & time / world background (3–5 lines) / **a concrete opening scene** /
goal & direction (optional) / constraints (optional) / **each role's starting position**
(where they are, doing what).

## 4. Genre-specific design

### Simulations (history, politics, organizations, negotiation)
- Cast real/fictional actors as roles and **always set factions** (e.g. `usa` / `ussr`).
  Intra-faction talks are hidden from the other side automatically. Neutral actors: no faction.
- Seed each role's memory with the **starting information gap** — this decides sim quality.
- master.temperature low (0.5–0.65); sub_defaults.temperature ~0.7
- dials e.g. Realism 9 / Tension 8 / Happenstance 3. narrative_style "third";
  for a dossier tone use "custom" + narrative_custom ("log style with date headings" etc.)
- In the master prompt: "respect historically consistent motives; no easy reconciliations."

### Fiction (fantasy, mystery, romance, SF, ...)
- As many roles as requested. Always include a **web of relationships** and **per-role
  secrets** — that is where drama comes from.
- Factions only for real opposing camps; leave blank for ordinary ensemble casts.
- master.temperature ~0.7, sub_defaults.temperature ~0.8
- **Dialogue-only insertion** (recommended): `sub_in_main_log: true` +
  `sub_main_show_name/action/inner: false` (character lines reliably reach the text;
  the Master writes connective prose).
- narrative_style: "third", or "first" + `pov_role` set to the protagonist's id.

## 5. Output format (strict)

Output the following **4 items in this order**.

### Output 1: Preset bundle (importable as-is)
Follow this structure **exactly**. Critical: **do NOT wrap `## FILE:` bodies in code
fences** (raw text). The META JSON must be valid JSON.

`````markdown
# korabo_llm preset: <display name>
<!-- korabo-preset-bundle v1 -->

## META

```json
{
  "display_name": "<display name>",
  "master": { "model": "", "temperature": 0.7, "prompt_file": "master/master_prompt.md",
              "important_prompt_file": "master/important_prompt.md" },
  "sub_defaults": { "model": "", "temperature": 0.8 },
  "roles": [
    {
      "id": "<role_id>",
      "name": "<display name>",
      "faction": "<faction or empty string>",
      "endpoint": "",
      "model": "",
      "temperature": null,
      "role_prompt_file": "roles/<role_id>.md",
      "memory_file": "memories/<role_id>.md",
      "memory_enabled": true
    }
  ],
  "run": {
    "target_main_chars": 0,
    "default_style": "<short style direction (e.g. terse, tense prose)>",
    "dials": [
      { "label": "<axis 1>", "value": 5 },
      { "label": "<axis 2>", "value": 5 },
      { "label": "<axis 3>", "value": 5 }
    ],
    "sub_memory_enabled": true,
    "sub_in_main_log": true,
    "sub_main_show_name": false,
    "sub_main_show_action": false,
    "sub_main_show_inner": false,
    "sub_main_inner_prefix": "（心の声）",
    "narrative_style": "third",
    "pov_role": "",
    "narrative_custom": ""
  }
}
```

## FILE: master/master_prompt.md

(Master prompt body. No code fences.)

## FILE: master/important_prompt.md

# 重要プロンプト

## 1. 作品の核

Genre: (output filled in — keep all 13 numbered headings; contents in English)
(...headings 2–13 likewise; leave inapplicable items blank...)

## FILE: roles/<role_id>.md

(Role prompt body)

## FILE: memories/<role_id>.md

# <Name> の記憶メモ (memory notes)

## 確定して知っている事実 (Facts known for certain)

- (facts only this person knows at the start...)

## 他者から聞いた情報 (Heard from others)

## 推測・疑念 (Guesses & suspicions)

## 約束・命令・計画 (Promises, orders, plans)

## 人間関係の変化 (Relationship changes)

## 身体・所持品・現在状態 (Body, items, current state)

## 未完了の行動 (Unfinished actions)
`````

- Repeat the roles / FILE sections **once per role** (each role gets both roles/ and memories/).
- Tune dial axes/values, narrative_style, default_style and temperatures to the work.
- `target_main_chars` is the target output length in characters (0 = off). Set it if the
  user specifies length (guide: short story 8,000–20,000; novella 30,000–50,000).

### Output 2: Situation prompt
One block of text to paste into the ▶ Run tab (structure per 3.5).

### Output 3: Recommended run settings (brief prose)
Run mode (usually "Master decides to stop (with limit)") and suggested turn count, plus any
toggles ("dialogue-only insertion" etc.) in 1–3 lines.

### Output 4: Design notes
Assumptions made and tuning knobs (extra role candidates, alternative dials) in 3–6 bullets.

## 6. Handling vague requests

Never stop to ask questions. Make reasonable assumptions, deliver a complete set, and
**state the assumptions in Output 4** (e.g. cast size unspecified → 3–4 roles; era
unspecified → the most typical setting for the requested genre).

## 7. Final checklist (self-check before output)

- [ ] META JSON is valid and complete
- [ ] role ids, FILE paths and META entries match three ways (roles/ AND memories/ for every role)
- [ ] Key prompt (master/important_prompt.md) output **filled in**, all 13 headings kept
- [ ] No FILE body is wrapped in code fences
- [ ] No JSON-format / person / numeric-intensity instructions in prompt bodies (those go to META)
- [ ] Every role has sample lines, goals, a secret, and "Always respond in English."
- [ ] Initial memories express information asymmetry (headings-only is fine when unneeded)
- [ ] The situation has a concrete opening scene and starting positions

---

## Your request

(Write your rough idea here. Examples:
"I want to simulate the Cuban Missile Crisis with the US and Soviet leaders and their aides."
"A fantasy novel, four characters, set in a frontier inn, about an exiled princess whose
identity gradually comes to light.")
