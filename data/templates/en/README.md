# English prompt templates

Simple English starter templates for korabo_llm.

| File | Purpose | Paste into |
|---|---|---|
| `meta_prompt_guide.md` | **Have a large LLM generate a full preset** from your rough idea | paste whole file + your idea into ChatGPT/Claude → save output as `<id>.preset.md` → import in 🎁 Presets tab |
| `master_prompt_novel.md` | Master prompt for novel-style writing | 🧠 Master tab → master prompt |
| `situation_template.md` | Situation template (era, place, opening) | ▶ Run tab → situation prompt |
| `role_template.md` | Character (role) prompt template | 🎭 Roles tab → role prompt |
| `examples/role_example.md` | Filled-in character example | reference |

## How to use

1. Copy a template and fill in the `(...)` placeholders. **Delete lines you don't need** — blank
   fields add noise and hurt quality.
2. A concrete opening scene helps the story start well.
3. For characters, add 2–3 example lines of dialogue to stabilize the voice.
4. The "Secret" field is known only to that character. Combined with factions and inner voice, it
   creates dramatic tension.

> Tip: The UI language (JA/EN) does not set the output language. If you want English output, write
> your prompts in English and add "Always write in English." to the master and role prompts.
