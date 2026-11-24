# PaperTrace · 研究与开源项目追踪 CLI

Codex、WorkBuddy 或其他 AI 请先阅读 [AGENTS.md](AGENTS.md)，其中包含可执行的审阅流程和报告口径。

需要 Python 3.9 或更高版本，使用标准库。在本目录执行：

    python3 radar.py plan
    python3 radar.py scan
    python3 radar.py audit runs/20261123T071202Z-a05f8067.json --all

plan 离线展示源和命中词。scan 读取配置中的 Atom、RSS、论文目录和 API 当前返回的批次，按原文链接合并跨分类条目，保存来源提供的摘要或说明、命中词、来源状态、更新时间和查询快照。任何源失败返回退出码 1，其余源结果仍保存。audit 可离线回看，默认显示命中项，加 --all 包括未命中项。

编辑 sources.json 调整范围，或用 python3 radar.py --config 自定义配置.json plan 预览替代配置。默认含 12 个 arXiv 分类、ACL Anthology、MLSys 2026 目录、OpenReview ICLR 2026、Hugging Face Daily Papers、技术博客、GitHub 项目版本与主分支提交，以及按 topic 发现其他项目的 GitHub Search API。会议年份与 API 条数上限见配置。MLSys 目录按标题匹配；部分订阅包含历史批次。用 audit 运行记录.json --sources 单独查看源清单、实际返回量或失败原因。机构归属、关键发现与证据强度需读原文核实。当前批次可能包含修订；漏跑的历史日期需另外回补。可将 runs 下的 JSON 交给其他 AI 工具审阅。

## AI 审阅

扫描完成后，将本次审计文件交给 Codex、WorkBuddy 或其他 AI，按批读取带原文链接和来源状态的 JSON。例如：

    python3 radar.py review runs/20261123T080819Z-58e38d9d.json --group matched --limit 10

按返回的 next_offset 续读。用 --group unmatched 补查关键词未命中的材料，默认 all 包含两组。日常可以加 --previous 上次运行.json 排除重复材料；首次发现的历史条目也会出现在差集中。请使用同一对扫描文件和同一组参数翻页。CLI 离线整理证据，调用方 AI 完成推理。日报逐条引用原文，注明审阅数量、未读范围与访问失败的来源。

## 团队追踪问题

运行 `python3 radar.py questions list` 查看问题和证据条件。例如：

    python3 radar.py questions add "长上下文推理的显存占用能降多少？" --evidence "相同硬件和任务质量下的峰值显存、吞吐与延迟"

每个问题在 questions/ 中独立保存为 Markdown，首行为问题，其余为要找的证据。可编辑、移除或随项目共享。plan 展示当前问题；review 每次读取当前问题，因此新问题可以直接用于重读历史扫描。问题用于 AI 审阅，全部采集来源与候选仍可检查。

## 飞书群内查询

在已发布的飞书应用中启用长连接、接收消息事件 `im.message.receive_v1`、接收群聊 @ 消息及机器人发送消息权限。在已配置飞书 CLI 的机器上运行：

    python -X utf8 feishu_bot.py --chat-id <群的 open_chat_id>

保持进程运行。在指定群内 @机器人并询问「当前关注方向」「最新日报」「算子优化」或论文关键词。Python 从本地 questions 和最新的 reports/YYYY-MM-DD.md 读取答案，通过已有 CLI 身份接收事件并回复原消息。

也可以使用官方 Python SDK 直连。在独立 Python 环境安装 `lark-channel-sdk==1.4.0`，为进程设置 `LARK_APP_ID` 和 `LARK_APP_SECRET`，使用同一命令并追加 `--transport sdk`。每个机器人同时运行一个监听实例。
