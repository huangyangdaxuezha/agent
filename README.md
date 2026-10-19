# 会议小助手（meeting-agent）

最小可用的 Agent 骨架项目。v1 定位：**通用会议问答小助手**（会议问答 / 纪要整理 / 待办抽取），
模型尚未接入，默认使用离线占位模型跑通全链路，后续只需配置即可换成真实模型。

交互形态：CLI（桌面端后续再做）。

## 目录结构

```
src/meeting_agent/
├─ cli.py                # 入口层：参数解析、交互式 REPL、敏感操作人工确认
├─ config.py             # 配置层：环境变量读取（前缀 MEETING_AGENT_）
├─ core/                 # 核心层：与具体模型/工具无关
│   ├─ types.py          #   数据契约：Message / ToolCall / ToolResult / LLMResponse
│   ├─ prompt.py         #   系统提示词与上下文拼装
│   └─ loop.py           #   主循环：think → act(工具) → observe，含步数上限
├─ llm/                  # 模型层：可替换供应商
│   ├─ base.py           #   抽象接口 LLMClient + LLMError
│   ├─ echo.py           #   离线占位模型（默认，无需 Key）
│   └─ http.py           #   OpenAI 兼容接口实现（标准库 urllib，零依赖）
├─ tools/                # 能力层
│   ├─ registry.py       #   工具注册、Schema、敏感操作确认
│   └─ builtin/          #   v1 为空：内置工具待后续添加
├─ memory/               # 记忆层
│   ├─ short_term.py     #   会话历史与裁剪
│   └─ store.py          #   JSON 会话持久化
└─ observability/        # 可观测层
    └─ logger.py         #   统一日志
tests/                   # 单元测试（离线，不发网络请求）
```

依赖方向单向：`cli → core → (llm / tools / memory)`，core 只依赖抽象接口。

## 快速开始（Windows 双击）

1. 双击 **`setup.cmd`**：创建 `.venv` 并安装依赖（首次约 1 分钟）
2. 双击 **`run.cmd`**：启动 CLI（首次会自动生成 `.env` 并打开记事本让你填密钥）
3. 关闭窗口即退出

> 启动脚本内部固定使用项目内的 `.venv`，不依赖系统 `python` 命令。

命令行方式：

```powershell
# 1. 创建虚拟环境
python -m venv .venv
.venv\Scripts\Activate.ps1

# 2. 安装（开发模式）+ 测试依赖
pip install -e ".[dev]"

# 3. 跑一次（默认离线占位模型）
python -m meeting_agent.cli --once "帮我整理这份会议记录的重点"

# 4. 交互式
python -m meeting_agent.cli
```

REPL 命令：`/help` `/history` `/clear` `/save [路径]` `/exit`。

## 配置

复制 `.env.example` 为 `.env` 后填写：

| 变量 | 说明 |
|---|---|
| `MEETING_AGENT_PROVIDER` | `echo`（离线占位）或 `openai_compatible` |
| `MEETING_AGENT_BASE_URL` | 兼容接口地址，如 `https://api.openai.com/v1` |
| `MEETING_AGENT_API_KEY` | 接口密钥 |
| `MEETING_AGENT_MODEL` | 模型名称 |
| `MEETING_AGENT_TEMPERATURE` | 采样温度，默认 0.3 |
| `MEETING_AGENT_MAX_STEPS` | 单轮最大循环步数，默认 5（最小 1） |
| `MEETING_AGENT_MAX_HISTORY` | 保留的历史消息数，默认 40 |
| `MEETING_AGENT_LOG_LEVEL` | 日志级别，默认 INFO |

`.env` 不入库；密钥只通过环境变量或命令行传入。

DeepSeek 示例（改完重启 CLI 生效）：

```ini
MEETING_AGENT_PROVIDER=openai_compatible
MEETING_AGENT_BASE_URL=https://api.deepseek.com/v1
MEETING_AGENT_MODEL=deepseek-chat
MEETING_AGENT_API_KEY=sk-你的密钥
```

密钥在 https://platform.deepseek.com/api_keys 创建。

## 测试

```powershell
pytest -q
```

测试全部离线：使用假模型（`tests/fakes.py`），不发网络请求、不消耗额度。

## 敏感操作护栏

有副作用的工具（如执行命令行、删除文件）注册时必须标记 `sensitive=True`，
执行前会走确认回调（CLI 中为交互式 `y/N` 询问）；**未获确认一律取消**，
并把取消结果回灌给模型。v1 未内置任何执行类工具，该机制已预留。

## 后续路线

1. 接入真实模型（填 `.env` 即可）
2. 添加会议相关工具（读取会议记录、导出纪要、写待办）
3. 持久化与检索（会议历史库）
4. 桌面端 UI（复用 core，替换入口层）
5. 评测集（回归提示词改动）
