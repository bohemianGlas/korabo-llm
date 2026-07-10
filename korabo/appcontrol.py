"""アプリ制御ヘルパ。

Gradioは build_app() を起動時に1度だけ実行してUIを構築するため、言語や
プリセットの切替（UI全体の再構築が必要な変更）はプロセスを再起動して反映する。
"""
from __future__ import annotations

import os
import sys
import threading

# 再起動をトリガした後、ブラウザ側で使う再接続JS。
# 旧サーバが落ちるのを待ってから、新サーバが復帰するまでポーリングし、復帰したら再読込する。
# （再起動時間はまちまちなので固定delayの reload は使わない）
RECONNECT_JS = (
    "() => {"
    " const u = window.location.href;"
    " const ping = () => fetch(u, {cache: 'no-store'})"
    "   .then(r => { if (r.ok) window.location.reload(); else setTimeout(ping, 600); })"
    "   .catch(() => setTimeout(ping, 600));"
    " setTimeout(ping, 1500);"
    "}"
)


def schedule_restart(delay: float = 0.5) -> None:
    """HTTPレスポンスを返した後にプロセスを再起動（同じ引数で os.execv）。

    ブラウザ側は少し遅れて location.reload() し、再起動後のサーバに再接続する。
    """
    def _do() -> None:
        os.execv(sys.executable, [sys.executable, *sys.argv])

    threading.Timer(max(0.1, delay), _do).start()
