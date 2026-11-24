"""Durable handoff between the Feishu listener and its dedicated Codex chat."""
import argparse
import ctypes
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
import time
from contextlib import closing

from radar import ROOT

GROUP = "oc_6ecfdf36fae537286ec9f0bebb18a199"
DB = ROOT / "runs" / "feishu-inbox.sqlite3"


def connect():
    DB.parent.mkdir(exist_ok=True)
    db = sqlite3.connect(DB, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE IF NOT EXISTS mentions (
        message_id TEXT PRIMARY KEY, question TEXT NOT NULL, context TEXT NOT NULL,
        local_only INTEGER NOT NULL, done INTEGER NOT NULL DEFAULT 0, response TEXT
    )""")
    return db


def open_event():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateEventW
    create.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_wchar_p)
    create.restype = ctypes.c_void_p
    event = create(None, False, False, "Local\\PaperTraceFeishuInbox")
    if not event:
        raise ctypes.WinError(ctypes.get_last_error())
    return event


def signal_session():
    if sys.platform == "win32":
        import _winapi
        event = open_event()
        try:
            _winapi.SetEvent(event)
        finally:
            _winapi.CloseHandle(event)


def pending(wait=False):
    import os
    from contextlib import ExitStack

    with ExitStack() as stack:
        event = None
        if wait and os.name == "nt":
            import _winapi
            try:
                event = open_event()
                stack.callback(_winapi.CloseHandle, event)
            except OSError:
                pass
        db = stack.enter_context(closing(connect()))
        while True:
            rows = [dict(row) for row in db.execute(
                "SELECT * FROM mentions WHERE done=0 ORDER BY rowid LIMIT 5")]
            if rows or not wait:
                return rows
            if event is None:
                time.sleep(0.4)
            else:
                _winapi.WaitForSingleObject(event, 500)


def receive(chat, message_id, question, local_answer):
    if chat != GROUP:
        return local_answer
    normalized = question.strip().rstrip("？?。！!").casefold()
    greeting = normalized in ("你好", "您好", "嗨", "哈喽", "hello", "hi", "在吗", "在么")
    if greeting:
        local_answer = "你好，我在！有什么想问的？"
    local_only = greeting or normalized in (
        "日报", "今日日报", "最新日报", "关注方向", "当前关注方向", "追踪问题"
    ) or re.match(r"^本地[\s：:]+\S", question.strip()) is not None
    with closing(connect()) as db, db:
        db.execute("INSERT OR IGNORE INTO mentions(message_id, question, context, local_only) VALUES(?,?,?,?)",
                   (message_id, question, local_answer, local_only))
    try:
        signal_session()
    except OSError:
        pass  # A different logon session can still observe the durable queue.
    if local_only:
        return local_answer
    return "已收到。Codex 会在这里回复你的问题。"


def finish(message_id, text):
    from feishu_bot import cli_binary

    with closing(connect()) as db, db:
        row = db.execute("SELECT * FROM mentions WHERE message_id=?", (message_id,)).fetchone()
        if not row:
            raise ValueError("未知收件记录")
        if row["done"]:
            return
        if not row["local_only"]:
            if not text.strip():
                raise ValueError("分析回复不能为空")
            key = "pt-" + hashlib.sha256(message_id.encode()).hexdigest()[:40]
            subprocess.run([cli_binary(), "im", "+messages-reply", "--as", "bot", "--message-id",
                            message_id, "--idempotency-key", key, "--markdown", "-"],
                           input=text.encode("utf-8"), check=True, timeout=60)
        db.execute("UPDATE mentions SET done=1,response=? WHERE message_id=?", (text, message_id))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("pending")
    commands.add_parser("wait")
    commands.add_parser("finish").add_argument("message_id")
    args = parser.parse_args()
    if args.command in ("pending", "wait"):
        print(json.dumps(pending(wait=args.command == "wait"), ensure_ascii=False))
    else:
        finish(args.message_id, sys.stdin.buffer.read().decode("utf-8-sig").strip())
