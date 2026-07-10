"""プロンプト一括プリセット（再ポイント方式・作品一式）。

presets/<preset_id>/
  preset.jsonc            # マニフェスト（パスはpreset基準の相対）
  master/master_prompt.md # + 任意の include 子md（outline/style/note 等）
  roles/<id>.md
  memories/<id>.md

- 適用(apply_preset): マニフェストの相対パスを presets/<id>/… に解決して config へ書き込む。
  接続先(endpoints) と各 role.endpoint 名は保持（=マシン非依存）。
- 保存(save_current_as_preset): 現在の config から作品一式を presets/<id>/ にスナップショット。
- 「再ポイント方式」: 適用後は config が preset 内ファイルを直接指すため、
  プレイ中の記憶追記も preset 内に蓄積し、切替→復帰で各presetの記憶が保たれる。
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import json5

from .config import load_config, save_config
from .prompts import find_includes
from .schemas import AppConfig, Dial, MasterConfig, RoleConfig, RunConfig, SubDefaults

PRESETS_DIR = Path("presets")
_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _preset_dir(preset_id: str) -> Path:
    return PRESETS_DIR / preset_id


def list_presets() -> list[tuple[str, str]]:
    """(preset_id, display_name) の一覧を返す。"""
    if not PRESETS_DIR.exists():
        return []
    out: list[tuple[str, str]] = []
    for d in sorted(PRESETS_DIR.iterdir()):
        manifest = d / "preset.jsonc"
        if d.is_dir() and manifest.exists():
            try:
                data = json5.loads(manifest.read_text(encoding="utf-8"))
                out.append((d.name, str(data.get("display_name") or d.name)))
            except Exception:
                out.append((d.name, d.name))
    return out


def active_preset_id(cfg: AppConfig | None = None) -> str | None:
    """現在の config がどのプリセットを指しているか（presets/<id>/ 配下か）を判定する。"""
    cfg = cfg or load_config()
    pf = Path(cfg.master.prompt_file)
    try:
        parts = pf.resolve().relative_to(PRESETS_DIR.resolve()).parts
        return parts[0] if parts else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 適用
# ---------------------------------------------------------------------------

def apply_preset(preset_id: str, cfg: AppConfig | None = None) -> str:
    d = _preset_dir(preset_id)
    manifest = d / "preset.jsonc"
    if not manifest.exists():
        raise ValueError(f"プリセット '{preset_id}' が見つかりません")
    data = json5.loads(manifest.read_text(encoding="utf-8"))
    cfg = cfg or load_config()

    def rel(path: str) -> str:
        # preset 基準の相対パスを、リポジトリルートからの相対パス文字列へ
        return (d / path).as_posix()

    m = data.get("master", {})
    cfg.master = MasterConfig(
        endpoint=cfg.master.endpoint,  # 接続先は保持
        model=str(m.get("model", "")),
        prompt_file=rel(m.get("prompt_file", "master/master_prompt.md")),
        temperature=float(m.get("temperature", cfg.master.temperature)),
    )

    sd = data.get("sub_defaults", {})
    cfg.sub_defaults = SubDefaults(
        endpoint=cfg.sub_defaults.endpoint,  # 接続先は保持
        model=str(sd.get("model", "")),
        temperature=float(sd.get("temperature", cfg.sub_defaults.temperature)),
    )

    roles: list[RoleConfig] = []
    for r in data.get("roles", []):
        roles.append(
            RoleConfig(
                id=str(r["id"]),
                name=str(r.get("name", "")),
                faction=str(r.get("faction", "")),
                endpoint=str(r.get("endpoint", "")),  # 名前参照のみ（ローカルconfigの同名を利用）
                model=str(r.get("model", "")),
                temperature=r.get("temperature"),
                role_prompt_file=rel(r.get("role_prompt_file", f"roles/{r['id']}.md")),
                memory_file=rel(r.get("memory_file", f"memories/{r['id']}.md")),
            )
        )
    cfg.roles = roles

    run = data.get("run", {})
    cfg.run = RunConfig(
        default_mode=cfg.run.default_mode,
        default_max_turns=cfg.run.default_max_turns,
        default_style=str(run.get("default_style", "")),
        dials=[Dial(label=str(x.get("label", "")), value=int(x.get("value", 5))) for x in run.get("dials", [])],
        sub_in_main_log=bool(run.get("sub_in_main_log", True)),
        sub_main_show_name=bool(run.get("sub_main_show_name", True)),
        sub_main_show_inner=bool(run.get("sub_main_show_inner", True)),
        narrative_style=str(run.get("narrative_style", "third")),
        pov_role=str(run.get("pov_role", "")),
        narrative_custom=str(run.get("narrative_custom", "")),
    )

    save_config(cfg)
    return f"プリセット「{data.get('display_name', preset_id)}」を適用しました"


# ---------------------------------------------------------------------------
# 保存（現在の構成をスナップショット）
# ---------------------------------------------------------------------------

def _copy_into(src: str, dst: Path) -> None:
    s = Path(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if s.exists():
        shutil.copyfile(s, dst)
    else:
        dst.write_text("", encoding="utf-8")


def save_current_as_preset(preset_id: str, display_name: str = "") -> str:
    preset_id = (preset_id or "").strip()
    if not _ID_RE.match(preset_id):
        raise ValueError("idは英数字・ハイフン・アンダースコアのみで入力してください")
    cfg = load_config()
    d = _preset_dir(preset_id)
    (d / "master").mkdir(parents=True, exist_ok=True)
    (d / "roles").mkdir(parents=True, exist_ok=True)
    (d / "memories").mkdir(parents=True, exist_ok=True)

    # master プロンプト本体
    master_src = Path(cfg.master.prompt_file)
    _copy_into(cfg.master.prompt_file, d / "master" / "master_prompt.md")
    # master が include する子md も一緒にコピー
    if master_src.exists():
        for name in find_includes(master_src.read_text(encoding="utf-8")):
            child = master_src.parent / name
            if child.exists():
                _copy_into(str(child), d / "master" / name)

    # ロールごとの prompt / memory
    roles_manifest = []
    for r in cfg.roles:
        _copy_into(r.role_prompt_file, d / "roles" / f"{r.id}.md")
        _copy_into(r.memory_file, d / "memories" / f"{r.id}.md")
        roles_manifest.append(
            {
                "id": r.id,
                "name": r.name,
                "faction": r.faction,
                "endpoint": r.endpoint,
                "model": r.model,
                "temperature": r.temperature,
                "role_prompt_file": f"roles/{r.id}.md",
                "memory_file": f"memories/{r.id}.md",
            }
        )

    manifest = {
        "display_name": display_name.strip() or preset_id,
        "master": {
            "model": cfg.master.model,
            "temperature": cfg.master.temperature,
            "prompt_file": "master/master_prompt.md",
        },
        "sub_defaults": {"model": cfg.sub_defaults.model, "temperature": cfg.sub_defaults.temperature},
        "roles": roles_manifest,
        "run": {
            "default_style": cfg.run.default_style,
            "dials": [{"label": x.label, "value": x.value} for x in cfg.run.dials],
            "sub_in_main_log": cfg.run.sub_in_main_log,
            "sub_main_show_name": cfg.run.sub_main_show_name,
            "sub_main_show_inner": cfg.run.sub_main_show_inner,
            "narrative_style": cfg.run.narrative_style,
            "pov_role": cfg.run.pov_role,
            "narrative_custom": cfg.run.narrative_custom,
        },
    }
    text = json.dumps(manifest, ensure_ascii=False, indent=2)
    (d / "preset.jsonc").write_text(text + "\n", encoding="utf-8")
    return f"現在の構成をプリセット「{preset_id}」として保存しました"


# ---------------------------------------------------------------------------
# 単一ファイル・バンドル（Markdownバンドル）でのエクスポート/インポート
# ---------------------------------------------------------------------------
# 本文(md)は ``` フェンスを含み得るため、フェンスで包まず「## FILE:」見出しで区切る。

_BUNDLE_VERSION = "korabo-preset-bundle v1"
_FILE_HEADING = re.compile(r"^## FILE:[ \t]*(.+?)[ \t]*$", re.MULTILINE)
_META_JSON = re.compile(r"^## META[ \t]*$.*?```json[ \t]*\n(.*?)\n```", re.DOTALL | re.MULTILINE)


def _serialize_bundle(manifest: dict, files: dict[str, str]) -> str:
    parts = [
        f"# korabo_llm preset: {manifest.get('display_name', '')}",
        f"<!-- {_BUNDLE_VERSION} -->",
        "",
        "## META",
        "",
        "```json",
        json.dumps(manifest, ensure_ascii=False, indent=2),
        "```",
    ]
    for path, body in files.items():
        parts.append("")
        parts.append(f"## FILE: {path}")
        parts.append("")
        parts.append(body.rstrip("\n"))
    return "\n".join(parts) + "\n"


def _parse_bundle(text: str) -> tuple[dict, dict[str, str]]:
    text = text.replace("\r\n", "\n")
    mm = _META_JSON.search(text)
    if not mm:
        raise ValueError("バンドルに ## META（```json ブロック）が見つかりません")
    manifest = json5.loads(mm.group(1))

    files: dict[str, str] = {}
    matches = list(_FILE_HEADING.finditer(text))
    for i, m in enumerate(matches):
        path = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip("\n")
        files[path] = body
    return manifest, files


def export_preset_bundle(preset_id: str, out_path: str | Path | None = None) -> Path:
    """既存プリセットを単一Markdownバンドル(.preset.md)へ書き出し、そのパスを返す。"""
    d = _preset_dir(preset_id)
    manifest_path = d / "preset.jsonc"
    if not manifest_path.exists():
        raise ValueError(f"プリセット '{preset_id}' が見つかりません")
    manifest = json5.loads(manifest_path.read_text(encoding="utf-8"))

    files: dict[str, str] = {}

    def _add(rel_path: str) -> None:
        p = d / rel_path
        if p.exists():
            files[rel_path] = p.read_text(encoding="utf-8")

    master_rel = manifest.get("master", {}).get("prompt_file", "master/master_prompt.md")
    _add(master_rel)
    master_abs = d / master_rel
    if master_abs.exists():
        for name in find_includes(master_abs.read_text(encoding="utf-8")):
            _add((Path(master_rel).parent / name).as_posix())
    for r in manifest.get("roles", []):
        _add(r.get("role_prompt_file", f"roles/{r['id']}.md"))
        _add(r.get("memory_file", f"memories/{r['id']}.md"))

    out = Path(out_path) if out_path else (PRESETS_DIR / f"{preset_id}.preset.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_serialize_bundle(manifest, files), encoding="utf-8")
    return out


def import_preset_bundle(bundle_path: str | Path, preset_id: str = "") -> tuple[str, str]:
    """単一Markdownバンドルを presets/<id>/ に展開する。(preset_id, メッセージ) を返す。"""
    bundle_path = Path(bundle_path)
    text = bundle_path.read_text(encoding="utf-8")
    manifest, files = _parse_bundle(text)

    pid = (preset_id or "").strip()
    if not pid:
        stem = bundle_path.name
        for suffix in (".preset.md", ".md"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
                break
        pid = stem
    if not _ID_RE.match(pid):
        raise ValueError("プリセットidは英数字・ハイフン・アンダースコアのみで指定してください")

    d = _preset_dir(pid)
    existed = d.exists()
    d.mkdir(parents=True, exist_ok=True)
    (d / "preset.jsonc").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for rel_path, body in files.items():
        target = d / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body + "\n" if body and not body.endswith("\n") else body, encoding="utf-8")

    note = "（既存を上書き）" if existed else ""
    return pid, f"プリセット「{manifest.get('display_name', pid)}」をインポートしました{note}"
