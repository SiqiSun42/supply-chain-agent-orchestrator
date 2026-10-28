# Agent Orchestrator

**面向工业供应链采购场景的多智能体决策系统：中枢节点按任务语义路由至专职智能体，工具调用全程类型校验，需人工介入的步骤挂起后可跨进程恢复执行。**

![Python](https://img.shields.io/badge/python-3.12-3776AB)
![LangGraph](https://img.shields.io/badge/LangGraph-1.x-1C3C3C)
![React](https://img.shields.io/badge/React-19-61DAFB)
![License](https://img.shields.io/badge/license-MIT-green)

基于 LangGraph 构建，业务数据落在关系库中，模型只负责任务路由与语言组织，数值核算与方案筛选由确定性代码完成。默认以脚本化 mock 推理层运行，无需任何 API Key 即可跑通全部链路；设置环境变量后可切换到 DeepSeek 等 OpenAI 兼容服务或 Anthropic。

---

## 业务场景

当前覆盖四条端到端链路，均可在 Console 中一键发起：

| 任务 | 链路 |
|---|---|
| 零件库存查询 | 路由至 ops → 读库存快照 → 汇总答复 |
| 客户近三月交易汇总 | 路由至 ops → 聚合出库与收入 → 汇总答复 |
| 补货申请（需审批） | 读库存与多供应商报价 → 服务端组装方案 → **人工审批** → 记录选定方案 |
| 采购单外发（需审批） | 校验供应商可售量 → 生成采购邮件 → **人工审批** → 发送 |

另保留三条框架能力演示任务（人工升级、低置信度终审、长期记忆召回）。

## 数据

业务库为独立 SQLite（`data/supply_chain.db`），由 `archive/` 下的 Meridian 供应链数据集导入，共 12 张表、约 4.5 万行：

- **本企业侧**：物料、仓库、客户、库存快照、历史采购单与出货单等。
- **供应商侧**：`supplier_offer` 表记录各供应商**当前**可售量、单价与交期，共 393 行（20 家供应商覆盖 40 个物料，含零库存行）。该表由历史采购记录推导生成，每次查询即取最新值，不含时间序列。
- 库存类查询以固定业务日期 `2026-01-01` 为基准，取该日期之前最近一次快照。

重建业务库：

```bash
uv run python scripts/load_supply_chain.py
```

## 快速开始

依赖 [uv](https://docs.astral.sh/uv/) 与 Node 20+。

```bash
make install    # uv sync + npm ci
make dev        # API :8000（mock 推理 + SQLite）+ UI :5173
```

打开 http://localhost:5173，点击预制任务「Replenish HYD-08: leadership approval」，可以看到中枢节点派发、工具执行、审批卡片内联出现；通过或驳回后任务从断点继续。

切换真实模型：

```bash
# OpenAI 兼容服务（DeepSeek 等）
LLM_PROVIDER=openai OPENAI_API_KEY=sk-... OPENAI_BASE_URL=https://api.deepseek.com OPENAI_MODEL=deepseek-chat make dev
# Anthropic
LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=sk-ant-... make dev
```

完整 Docker 栈（Postgres、Redis、Chroma、API、worker、UI）：`make up`，随后访问 http://localhost:8080，`make down` 停止并清理。

---

## 设计要点

**路由约束**。中枢节点的决策是结构化输出，取值被限制在四个专职智能体（信息检索、数值分析、业务执行、结果撰写）与 FINISH 构成的闭集内；每个智能体只注册属于自己的工具子集，派发错误时也无法触达采购类工具。委派轮数、单智能体访问次数、工具调用轮次三层上限约束路由空间，最坏情况是提前收敛而非无限循环。

**工具契约**。16 个工具的参数以 Pydantic 建模并导出为 JSON Schema，调用前强制校验，校验失败作为可恢复错误回传模型重试。补货场景中模型只传物料、仓库、数量三个语义参数，完整审批载荷由服务端依库存与报价确定性组装，避免模型手工拼装长 JSON。

**人工审批与恢复**。风险策略（而非模型）决定哪些步骤需要人工介入：采购类审批、外发邮件、超额退款、显式升级、低置信度终答。触发时执行图挂起并将运行状态落盘，接口层仅入队、由工作进程携带人工决策在另一进程续跑，单任务内多次中断可链式串联。中断点位于工具调用中途时，恢复前重建消息序列，保证模型侧 `tool_calls` 与工具返回严格配对。状态流转采用原子条件转移，重复提交的审批决定不会导致工具二次执行。

**采购审批交互**。补货审批不是单一动作的通过或拒绝：审批卡片展示数据事实、分析结论、推荐方案与备选方案（含跨供应商拆单），驳回后可选择备选方案或自由填写，修订后重新进入审批，直到通过才恢复执行图。

**可观测与审计**。每次工具执行、拒绝与报错写入审计表（入参、返回、状态、所属智能体、耗时）；步骤级事件先落库再发布，前端通过 SSE 先重放历史再跟随实时流，断线按 `Last-Event-ID` 续播，因此任意一次运行都可逐条回放。

---

## 配置

全部配置通过环境变量提供，详见 [`.env.example`](.env.example)。常用项：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `LLM_PROVIDER` | `mock` | `mock` / `openai` / `anthropic` |
| `OPENAI_BASE_URL` | 未设置 | 指向 OpenAI 兼容服务；设置后结构化输出降级为 `json_object` |
| `OPENAI_MODEL` / `ANTHROPIC_MODEL` | `gpt-5-mini` / `claude-sonnet-5` | 执行与终答模型 |
| `SUPERVISOR_MODEL` | 未设置 | 可为路由单独指定模型 |
| `SUPPLY_CHAIN_DB_PATH` | `./data/supply_chain.db` | 业务库路径 |
| `DATABASE_URL` | `sqlite:///./data/orchestrator.db` | 运行记录库；生产可换 `postgresql+psycopg://...` |
| `CHECKPOINTER` | `auto` | `postgres` / `sqlite` / `memory` |
| `RUN_EXECUTOR` | `inline` | `inline` 进程内线程池，或 `celery` |
| `MAX_SUPERVISOR_STEPS` | `6` | 单次运行最大委派轮数 |
| `MAX_AGENT_VISITS` | `2` | 同一智能体最大访问次数 |
| `MAX_TOOL_ROUNDS` | `4` | 单个智能体回合内最大工具往返次数 |
| `CONFIDENCE_THRESHOLD` | `0.55` | 终答置信度低于此值转人工复核 |
| `EMAIL_REQUIRES_APPROVAL` | `true` | 外发邮件需审批 |
| `LONG_TERM_MEMORY_ENABLED` | `false` | 长期记忆（Chroma 语义召回） |

复杂任务建议上调三层上限，例如 `MAX_SUPERVISOR_STEPS=10 MAX_AGENT_VISITS=3 MAX_TOOL_ROUNDS=8`。

## 接口

交互式文档位于 `/docs`。主要端点：

| 方法与路径 | 说明 |
|---|---|
| `POST /api/runs` | 发起任务 `{task, user_id, thread_id?}` |
| `GET /api/runs/{id}` | 运行详情，含待处理审批 |
| `GET /api/runs/{id}/stream` | SSE：历史重放 + 实时事件 |
| `GET /api/runs/{id}/audit` | 该次运行的工具审计记录 |
| `GET /api/approvals` | 审批收件箱 |
| `POST /api/approvals/{id}/decision` | `approve` / `reject` / `revise` / `edit` |
| `GET /api/config` · `GET /api/graph` | 运行配置、风险策略、工具 Schema；执行图结构 |
| `GET /health/ready` | 就绪探针（数据库、事件总线、向量库、checkpointer） |

## 目录结构

```
src/orchestrator/
├── agents/          # 执行图、智能体名册与提示、风险策略、工具执行器
├── supply_chain/    # 业务查询、补货决策引擎、采购单外发、数据导入与报价生成
├── llm/             # 提供方接口、OpenAI/Anthropic 适配、脚本化 mock、消息修复与 JSON 解析
├── api/             # FastAPI 应用与路由
├── db/              # SQLAlchemy 模型与仓储
├── runtime/         # 运行与恢复、派发、事件总线、checkpointer、容器
├── tools/           # 工具框架与内置工具
└── config.py        # pydantic-settings 配置
frontend/            # React + Vite + TypeScript 控制台
spec/                # 分阶段改造说明与采购审批交互规范
tests/               # 离线测试（101 项）
```

## 开发

```bash
make test        # pytest，全离线
make lint        # ruff + eslint
make typecheck   # mypy --strict + tsc
make check       # CI 全量检查
```

测试覆盖工具参数校验、风险策略、执行图（委派、上限、失败处理）、补货与采购链路、审批中断与恢复、提供方适配与消息修复，以及完整 HTTP 流程。

## 现状与计划

已完成：库存与交易查询、单物料补货审批、采购单外发审批，mock 与真实 API 两条路径均可端到端运行；供应商报价数据已扩充至 20 家。

计划中：

- 采购单生命周期模拟（供应商确认、发货、签收、延误）与库存联动写入
- 多物料联合采购引擎：批量扫描低于补货点的物料，生成含同供应商凑单、运费与折扣关联的整单方案
- 后端定时调度与访问鉴权
- 文档截图更新

## License

[MIT](LICENSE)
