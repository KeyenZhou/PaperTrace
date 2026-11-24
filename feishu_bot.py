"""Reply to group mentions using the latest local PaperTrace report."""
import argparse
import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from radar import ROOT, tracking_questions
from feishu_inbox import receive


def answer(question):
    query = question.casefold()
    if any(term in query for term in ("方向", "关注什么", "追踪问题")):
        questions = tracking_questions(ROOT / "questions")
        return "PaperTrace 当前关注\n\n" + "\n".join(
            f"{i}. {item['question']}" for i, item in enumerate(questions, 1)
        )
    reports = sorted((ROOT / "reports").glob("????-??-??.md"))
    if not reports:
        return "还没有生成日报。你可以问我「当前关注方向」。"
    report = reports[-1]
    body = re.sub(r"\[([^\]]+)\]\((?!https?://)[^)]+\)", r"\1", report.read_text(encoding="utf-8"))
    groups = [
        (("算子", "gpu", "npu", "加速", "推理"), ("gemm", "乘法", "kv cache", "npu", "算子")),
        (("agent", "智能体", "评测", "人工"), ("agent", "智能体", "人工")),
    ]
    terms = set(re.findall(r"[a-z][a-z0-9.-]{2,}", query))
    for keys, aliases in groups:
        if any(key in query for key in keys):
            terms.update(aliases)
    if terms:
        ranked = []
        for line in body.splitlines():
            if "https://" in line:
                prose = re.sub(r"https?://[^)\s]+", "", line).casefold()
                score = sum(term in prose for term in terms)
                if score:
                    ranked.append((score, line))
        if ranked:
            ranked.sort(key=lambda item: -item[0])
            return f"PaperTrace · {report.stem}\n\n" + "\n\n".join(line for _, line in ranked[:3])
    if not query.strip() or any(word in query for word in ("日报", "推荐", "发现", "进展", "摘要")):
        return body[:10000]
    return "我可以查询最新研究日报。试试「今天有哪些算子优化」「Agent 评测」「最新日报」或「当前关注方向」。"


def cli_binary():
    exe = shutil.which("lark-cli.exe" if os.name == "nt" else "lark-cli")
    if not exe and os.name == "nt":
        wrapper = shutil.which("lark-cli.cmd")
        if wrapper:
            exe = Path(wrapper).parent / "node_modules/@larksuite/cli/bin/lark-cli.exe"
    if not exe or not Path(exe).is_file():
        raise RuntimeError("找不到 lark-cli 可执行文件")
    return str(exe)


def group_question(event, chat, bot):
    if (event.get("chat_id") != chat or event.get("chat_type") != "group"
            or event.get("sender_type") != "user" or not event.get("message_id")):
        return None
    content = event.get("content", "")
    mentioned = False
    for mention in event.get("mentions") or []:
        if mention.get("id") == bot:
            mentioned = True
            for token in (mention.get("key"), "@" + (mention.get("name") or "")):
                if token and token != "@":
                    content = content.replace(token, "")
    return content.strip() if mentioned else None


def listen_cli(chat):
    cli = cli_binary()
    info = subprocess.check_output([cli, "api", "GET", "/open-apis/bot/v3/info", "--as", "bot"])
    bot = json.loads(info)["data"]["open_id"]
    while True:
        with subprocess.Popen([cli, "event", "consume", "im.message.receive_v1", "--as", "bot"],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE) as stream:
            try:
                for raw in stream.stdout:
                    try:
                        event = json.loads(raw)
                        question = group_question(event, chat, bot)
                        if question is None:
                            continue
                        message_id = event["message_id"]
                        response = receive(chat, message_id, question, answer(question))
                        command = [cli, "im", "+messages-reply", "--as", "bot", "--message-id",
                                   message_id, "--idempotency-key", message_id, "--markdown", "-"]
                        for attempt in range(3):
                            result = subprocess.run(command, input=response.encode("utf-8"),
                                                    stdout=subprocess.DEVNULL, timeout=45)
                            if result.returncode == 0:
                                logging.info("Replied to %s", message_id)
                                break
                            time.sleep(2 ** attempt)
                    except (ValueError, OSError, subprocess.SubprocessError):
                        logging.exception("Could not process message")
            finally:
                stream.stdin.close()
        logging.warning("Event stream exited (%s), reconnecting", stream.returncode)
        time.sleep(5)


async def listen_sdk(chat):
    from lark_channel import FeishuChannel

    channel = FeishuChannel(app_id=os.environ["LARK_APP_ID"], app_secret=os.environ["LARK_APP_SECRET"])
    channel.update_policy(group_policy="allowlist", group_allowlist=[chat], require_mention=True)

    async def on_message(msg):
        if msg.chat_id == chat and msg.sender.sender_type == "user":
            response = receive(chat, msg.message_id, msg.content_text, answer(msg.content_text))
            await channel.send(chat, {"markdown": response},
                               {"reply_to": msg.message_id})

    channel.on("message", on_message)
    await channel.connect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chat-id", required=True)
    parser.add_argument("--transport", choices=("cli", "sdk"), default="cli")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    if args.transport == "sdk":
        asyncio.run(listen_sdk(args.chat_id))
    else:
        listen_cli(args.chat_id)
