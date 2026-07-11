"""OpenAI互換APIクライアントと、LLM未接続テスト用のMockクライアント。"""
from __future__ import annotations

import json
import re
import time
from typing import Callable, Optional

import json5
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)

from .schemas import EndpointConfig

# 再試行する一過性エラー（ローカル推論エンジンの400は内部500=一過性のことが多いため含める）
_RETRYABLE_ERRORS = (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
    BadRequestError,
)
# 再試行しても直らないため即送出するエラー
_FATAL_ERRORS = (
    AuthenticationError,
    PermissionDeniedError,
    NotFoundError,
)


# ---------------------------------------------------------------------------
# JSON応答の堅牢パース
# ---------------------------------------------------------------------------

def _escape_ctrl_in_strings(text: str) -> str:
    """JSON文字列リテラル内の生制御文字（改行・タブ等）をエスケープして修復する。

    LLMは speech 等の値の中に生の改行（段落分け）を入れがちだが、これは
    json/json5 とも不正。文字列内のみ \\n 等へ置換し、文字列外の整形は保つ。
    """
    out: list[str] = []
    in_string = False
    escape = False
    for ch in text:
        if in_string:
            if escape:
                escape = False
                out.append(ch)
            elif ch == "\\":
                escape = True
                out.append(ch)
            elif ch == '"':
                in_string = False
                out.append(ch)
            elif ch == "\n":
                out.append("\\n")
            elif ch == "\r":
                out.append("\\r")
            elif ch == "\t":
                out.append("\\t")
            else:
                out.append(ch)
        else:
            if ch == '"':
                in_string = True
            out.append(ch)
    return "".join(out)


def _try_parse(text: str) -> dict | None:
    candidates = (text, _escape_ctrl_in_strings(text))
    for candidate in candidates:
        for parser in (json.loads, json5.loads):
            try:
                obj = parser(candidate)
                if isinstance(obj, dict):
                    return obj
            except Exception:
                pass
    return None


def strip_code_fences(text: str) -> str:
    """先頭・末尾のコードフェンス（```lang / ```）を剥がす（本文中は触らない）。"""
    t = text.strip()
    if t.startswith("```"):
        first_nl = t.find("\n")
        if first_nl >= 0:
            t = t[first_nl + 1 :]
        else:
            t = t[3:]
    if t.rstrip().endswith("```"):
        t = t.rstrip()[:-3]
    return t.strip()


def _first_balanced_object(text: str) -> str | None:
    """文字列リテラルを考慮して最初の {...} を切り出す。"""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
    return None


def extract_json(text: str) -> dict:
    """LLM応答からJSONオブジェクトを抽出する。失敗時は ValueError。"""
    obj = _try_parse(text.strip())
    if obj is not None:
        return obj
    for block in re.findall(r"```(?:json)?\s*(.*?)```", text, re.DOTALL):
        obj = _try_parse(block.strip())
        if obj is not None:
            return obj
    candidate = _first_balanced_object(text)
    if candidate:
        obj = _try_parse(candidate)
        if obj is not None:
            return obj
    raise ValueError("応答からJSONを抽出できませんでした")


# ---------------------------------------------------------------------------
# クライアント
# ---------------------------------------------------------------------------

def _empty_usage() -> dict:
    return {"prompt": 0, "completion": 0, "total": 0}


class LLMClient:
    def __init__(
        self,
        endpoint: EndpointConfig,
        model: str,
        temperature: float = 0.7,
        max_retries: int = 2,
        retry_backoff: float = 1.5,
    ):
        self.model = model or endpoint.default_model
        self.temperature = temperature
        self.max_retries = max(0, int(max_retries))
        self.retry_backoff = max(0.0, float(retry_backoff))
        # 直近のchat()呼び出しのトークン使用量（session側が集計に使う）
        self.last_usage: dict = _empty_usage()
        self._client = OpenAI(
            base_url=endpoint.base_url,
            api_key=endpoint.resolve_api_key() or "no-key",
        )

    def chat(self, messages: list[dict], on_retry: Optional[Callable[[int, Exception], None]] = None) -> str:
        """一過性エラーを指数バックオフで再試行しつつ応答本文を返す。

        on_retry(attempt, err): 再試行の直前に呼ばれる任意コールバック（UI表示用）。
        """
        attempts = self.max_retries + 1
        last_err: Exception | None = None
        for attempt in range(attempts):
            try:
                resp = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                )
                self.last_usage = _extract_usage(getattr(resp, "usage", None))
                return resp.choices[0].message.content or ""
            except _FATAL_ERRORS:
                raise
            except _RETRYABLE_ERRORS as e:
                last_err = e
                if attempt + 1 >= attempts:
                    break
                if on_retry is not None:
                    try:
                        on_retry(attempt + 1, e)
                    except Exception:
                        pass
                time.sleep(self.retry_backoff * (2 ** attempt))
        assert last_err is not None
        raise last_err


def _extract_usage(usage) -> dict:
    """OpenAI互換レスポンスの usage をトークン数dictに変換する。"""
    if usage is None:
        return _empty_usage()
    prompt = getattr(usage, "prompt_tokens", 0) or 0
    completion = getattr(usage, "completion_tokens", 0) or 0
    total = getattr(usage, "total_tokens", 0) or (prompt + completion)
    return {"prompt": int(prompt), "completion": int(completion), "total": int(total)}


class MockLLMClient(LLMClient):
    """LLM未接続でシステム全体をE2E確認するためのダミー。

    プロンプト内のマーカー（MasterDecision / SubResponse）でMaster用か
    Sub用かを判別し、定型のJSONを返す。Masterはロールを順番に呼び出し、
    ターン6以降で finish を返す。
    """

    FINISH_AT = 6

    def __init__(self, endpoint: EndpointConfig, model: str, temperature: float = 0.7, **_kwargs):
        self.model = model or "mock-model"
        self.temperature = temperature
        self.max_retries = 0
        self.retry_backoff = 0.0
        self.last_usage: dict = _empty_usage()
        self._count = 0

    def chat(self, messages: list[dict], on_retry: Optional[Callable[[int, Exception], None]] = None) -> str:
        self._count += 1
        text = "\n".join(str(m.get("content", "")) for m in messages)
        out = self._mock_master(text) if "MasterDecision" in text else self._mock_sub()
        # 実APIのusageに近い挙動にするため、文字数からトークン数を概算（約3文字=1トークン）
        prompt = len(text) // 3
        completion = len(out) // 3
        self.last_usage = {"prompt": prompt, "completion": completion, "total": prompt + completion}
        return out

    def _mock_master(self, text: str) -> str:
        turn = 1
        m = re.search(r"現在のターン[:：]\s*(\d+)", text)
        if m:
            turn = int(m.group(1))
        roles = re.findall(r"^- ([A-Za-z0-9_-]+)[:：]", text, re.MULTILINE)
        intervened = "# 新しいユーザー介入" in text

        if turn >= self.FINISH_AT:
            decision = {
                "thought": "（モック）物語を締めくくる。",
                "narration": f"こうして不思議な一日は幕を閉じた。（モック応答・T{turn}）",
                "action": "finish",
                "target_role": "",
                "message_to_role": "",
            }
        elif roles and turn % 3 != 0:
            target = roles[(turn - 1) % len(roles)]
            note = "ユーザー介入を反映しつつ、" if intervened else ""
            decision = {
                "thought": f"（モック）ターン{turn}。{target} に話を振る。",
                "narration": f"{note}物語はターン{turn}を迎えた。（モック語り）",
                "action": "call_sub",
                "target_role": target,
                "message_to_role": f"ターン{turn}の状況です。あなたの反応を教えてください。（モック）",
            }
        else:
            decision = {
                "thought": f"（モック）ターン{turn}。語りのみで進める。",
                "narration": f"風が止み、あたりは静まり返った。（ターン{turn}のモック語り）",
                "action": "continue",
                "target_role": "",
                "message_to_role": "",
            }
        return json.dumps(decision, ensure_ascii=False)

    def _mock_sub(self) -> str:
        resp = {
            "speech": f"なるほど、そういうことか（モック応答 #{self._count}）",
            "action": "肩をすくめて小さく頷いた。",
            "inner_voice": "（本当は少し戸惑っている…）",
            "memory_append": (
                f"モックのやり取り #{self._count} を記憶した。" if self._count % 2 == 0 else ""
            ),
        }
        return json.dumps(resp, ensure_ascii=False)


def create_client(endpoint: EndpointConfig, model: str, temperature: float) -> LLMClient:
    if endpoint.base_url.strip().lower() == "mock":
        return MockLLMClient(endpoint, model, temperature)
    return LLMClient(
        endpoint,
        model,
        temperature,
        max_retries=getattr(endpoint, "max_retries", 2),
        retry_backoff=getattr(endpoint, "retry_backoff", 1.5),
    )
