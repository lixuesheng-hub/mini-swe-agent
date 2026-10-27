# 运维手册（RUNBOOK）

> 目标：**不依赖任何对话记忆**，照本文即可复现实验、排障、发布。
> 相关：`../REPORT.md`（结论）、`../../roadmap/DECISIONS.md`（决策理由）、`PLAN.md`（早期计划）。

---

## 1. 环境前提

| 项 | 要求 |
|---|---|
| 数据 | `data/swe-bench-verified-mini/`（50 题，旧 schema）与 `data/swe-bench-verified-newschema/`（判分用新 schema） |
| 镜像 | 50 个 `swebench/sweb.eval.x86_64.*:latest`（清单见 `images.txt`） |
| 模型配置 | `~/.config/mini-swe-agent/.env`：`OPENAI_API_BASE=https://ark.cn-beijing.volces.com/api/coding/v3`、`OPENAI_API_KEY=<key>`、`MSWEA_MODEL_NAME` |
| 代理 | 访问 HF / GitHub 需要（例：`<你的代理>`）；**火山方舟 API 必须直连** |
| 并发 | 固定 `-w 2`；**同一时刻只跑一个 swebench 批量任务** |

### 网络与端点的关键事实

- 火山方舟是**国内端点**：走 socks 代理会出现 `Connection error`（部分模型必现）→ 跑 agent 时 `unset` 所有 proxy 变量。
- 数据集用**本地路径**（`--subset data/swe-bench-verified-mini`）以避免 HF 需要代理；判分时才需要代理（HF 新 schema 数据集）。
- 三类报错含义：
  | 报错 | 含义 | 处理 |
  |---|---|---|
  | `AccountOverdueError` / `overdue balance` | 按量账户欠费 | 充值，或用 Coding Plan 端点 |
  | `AccountQuotaExceeded`（5h 滚动额度） | 套餐额度耗尽 | 等重置或换 key |
  | `System protection triggered by request burst` | 瞬时突发限流 | 降到 `-w 1` |

---

## 2. 跑实验（标准流程）

```bash
cd /path/to/mini-swe-agent

# 0) 清残留容器（容器名无任务前缀，两个批量会互相杀）
docker ps -a --filter name=minisweagent- --format '{{.Names}}' | xargs -r docker rm -f

# 1) 单实例冒烟（换模型/端点后必做）
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY MSWEA_COST_TRACKING=ignore_errors \
uv run python -m minisweagent.run.benchmarks.swebench_single \
  --subset data/swe-bench-verified-mini --split test \
  -i django__django-11790 -m "openai/<模型ID>" -y --exit-immediately

# 2) 全量 / 子集（脚本已封装环境设置）
bash experiments/verified_mini_baseline/run_full_retrieval_tool.sh      # 工具版全量
bash experiments/verified_mini_baseline/resume_baseline.sh             # 基线（断点续跑）
bash experiments/verified_mini_baseline/rerun_unresolved.sh            # 重跑指定的 18 个

# 3) 判分（本地 docker，不耗模型额度）
bash experiments/verified_mini_baseline/run_eval_full.sh
# 或指定 run：
uv run python -m swebench.harness.run_evaluation \
  -d SWE-bench/SWE-bench_Verified -s test \
  -p experiments/runs/<run>/preds.json --max_workers 2 \
  -id <run_id> --report_dir experiments/runs/<run>/report

# 4) 汇总（生成 _dashboard.md/.csv，并写各 run 的 metrics.json）
uv run python tools/eval_report.py
```

### 断点续跑

`preds.json` 已存在的实例会自动跳过；中断后**重跑同一条命令**即可。判分同理（已完成实例 skip）。

---

## 3. 一次实验的产出约定

```
experiments/runs/<name>/
  <instance_id>/<instance_id>.traj.json   # 轨迹（不发布）
  preds.json                              # 模型输出（发布，供复验）
  report/*.json                           # harness 判分（发布）
  run_meta.json                           # status/model/instances/variable/时间（必须手写或脚本生成）
  metrics.json                            # 步数/截断/重复/检索 + 起止时间（脚本生成）
  NOTES.md                                # 假设 / 唯一变量 / 结果 / 结论 / 踩坑
  minisweagent.log, console.log            # 原始日志（不发布）
```

新增实验请照 `../REPORT.md` 附录「新增一个实验的标准流程」执行。

---

## 4. 发布

```bash
cd /path/to/mini-swe-agent
PRUNE_RUNS=1 bash tools/publish.sh      # 同步到 ../mini-swe-agent-publish（默认不提交）
```

`publish.sh` 行为：

- **只覆盖不删除**；`PRUNE_RUNS=1` 才清理源仓库已不存在的 run 目录；
- 排除：`roadmap`、`logs`、`mydocs`、`backups`、`uv.lock`、`_local`、`.idea`、`.venv*`；
- 证据瘦身：`experiments/runs/**/*.traj.json`、`console.log`、`*_console.log`、`minisweagent.log`、`exit_statuses_*.yaml`、`*trial*.json` 不发布；`experiments/examples/**` 保留；
- 只发布 `status: confirmed` 的 run（`PUBLISH_ALL_RUNS=1` 可全发）；
- 发布前**密钥扫描**，命中即中止；
- 幂等重写 `.gitignore` 覆盖块（`.idea/`、examples 例外）。

### 提交与推送（WSL）

```bash
cd /path/to/mini-swe-agent-publish
git config user.name "<你的名字>"
git config user.email "<你的邮箱>"
git add -A && git commit -m "docs: ..."      # 已推送过就别 amend，改用新提交
git push origin main
```

**推送通道**（Windows 下 PyCharm 会因 schannel 报 `server closed abruptly`，改用 WSL + SSH over 443）：

```
# ~/.ssh/config
Host github.com
  HostName ssh.github.com
  Port 443
  User git
  IdentityFile ~/.ssh/id_ed25519
  ProxyCommand nc -X 5 -x <PROXY_HOST>:<PROXY_PORT> %h %p
```
远端：`git@github.com:<你的账号>/<仓库>.git`

---

## 5. 排障速查

| 症状 | 原因 | 处理 |
|---|---|---|
| `KeyError: 'image'`（判分） | 用旧 schema 数据集喂新 harness | 判分用 `SWE-bench/SWE-bench_Verified` |
| 批量跑着跑着容器消失 | 起了第二个批量任务（全局清理容器） | 只跑一个；`docker ps` 确认 |
| 打印 `nan` 步数 | 轨迹不在本地（已排除发布） | 看 `metrics.json`；或本地跑一次生成 |
| 仪表盘 `vs baseline` 全是"—（任务集不同）" | 各 run 题目集不同 | 正常；只在同一批题上计算 |
| 提交时间显示很久以前 | `git commit --amend` 保留 author date | `git commit --amend --date=now --no-edit` |
| README 与报告数字不一致 | 手动改了 TL;DR | `uv run python tools/check_docs_sync.py` |
| 发布后链接 404 | 链到未发布的 `roadmap/` 等 | 发布副本跑一次相对链接检查 |

---

## 6. 常用校验

```bash
uv run python tools/check_docs_sync.py                 # 文档 TL;DR 一致
uv run pytest tests/models/test_actions_toolcall.py tests/tools/ -q   # 40 项
uv run python tools/eval_report.py                     # 重新生成仪表盘
```
