# mini-swe-agent：SWE Agent 实验与评测平台

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Tests](https://img.shields.io/badge/new--feature%20tests-40%20passed-brightgreen)
![Benchmark](https://img.shields.io/badge/benchmark-SWE--bench%20verified--mini%20(50)-informational)

> 本仓库以 [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) 为底座，在其上搭建**可复现、可消融的 SWE Agent 实验台**。
> 上游英文文档见 [`README.upstream.md`](README.upstream.md)；代码结构、风格与提交规范见 [`AGENTS.md`](AGENTS.md)。

---

## 一、背景

**出发点：把 Agent 开发里最容易含糊的环节，变成可度量的实验。**

Agent 的效果差异常被一句"换个更强的模型"带过，实际混了三件事：**模型能力**（会不会、想不想得到）、
**脚手架策略**（提示词 / 工具 / 上下文 / 自检）、**评测噪声**（同配置重跑结果不同）。
不拆开，任何"优化有效"的结论都站不住。

本项目以 SWE-bench verified-mini（50 题、约 5 GB 镜像、一轮全量约 1 小时、判分不消耗模型额度）为固定靶场，
把每项技术**逐项实现、单独消融、用带置信区间的指标判定收益**。定位是**实验与方法学平台**而非产品：
可插拔的工具注册表、默认关闭的开关、可复现的判分链路，以及能区分"真提升"与"噪声"的评测仪表盘。

选 SWE-bench 是因为它有客观判分（跑测试，而非人看输出）；选 mini 子集是因为它保留了与全量 verified
相近的难度分布，却能支撑本地高频迭代。

## 二、当前结论

<!-- TLDR:START -->
基线 **30/50 = 60%**（95% CI 46–72%）；单次结果不足以判定小幅改进。
- 失败分三类：能力型 / 边界噪声型 / 早提交型（后者无法靠加工具解决）
- 工具版全量（`github_fetch`）：resolved **36/50 = 72%（+12pp）**，但与基线区间**重叠 58%** → 方向为正、未超噪声
- 工具被用起来（22/50 实例），但“用过工具”组成功率反而更低（64% vs 79%），是难度混淆而非因果
<!-- TLDR:END -->

基线 `doubao-seed-2-1-lite-260915` 在 50 题上 **resolved 30/50 = 60%**（Wilson 95% CI 46–72%）。
这个区间的宽度本身就是结论：**单次 50 题不足以判定小幅改进**，此后所有实验都以"相对基线 + 置信区间"为准。

- **失败不是一类事**：能力型（多模型卡在同一测试）、边界噪声型（重跑会翻转：100 步失败 → 133 步成功）、早提交型（部分通过却引入多个回归）。
- **检索提高触发率，但不必然提分**：加 `github_fetch` 后全量 50 题 36/50（+12pp），检索实例从 4/50 升到 22/50，但与基线区间重叠 58%，未超噪声。
- **提示引导比单纯给工具更容易触发**：n=2 探针上，一段"先查 issue/PR"的提示让 `sphinx-8056` 从 100 步失败变为 21 步成功；同一题只给工具、无提示时另一题 0 次调用。

| run | 配置 | resolved | 95% CI | 与基线区间重叠 |
|---|---|---:|---|---|
| `runs/baseline` | 默认（bash only） | 30/50 = 60% | [46%, 72%] | —（基线） |
| `runs/retrieval-tool-50` | + `github_fetch` 工具 | **36/50 = 72%** | [58%, 83%] | **58% 明显重叠 → 未超噪声** |

> 另有 7 个 2 题探针（4 个模型、prompt 版、工具版、难例重跑）；完整表格由 `tools/eval_report.py` 生成，
> 见 [`_dashboard.md`](experiments/runs/_dashboard.md)。

完整方法与数据（指标定义、失败三分类、模型横比、负结果与局限）：**[`experiments/REPORT.md`](experiments/REPORT.md)**；
跨 run 明细表（含回归数、步数、检索率）：**[`experiments/runs/_dashboard.md`](experiments/runs/_dashboard.md)**；
可读的样例轨迹（失败 / 检索成功 / 早提交带回归）：**[`experiments/examples/`](experiments/examples/README.md)**。

### 实验台

- **数据**：`MariusHobbhahn/swe-bench-verified-mini`（50 题，django 25 + sphinx 25），本地副本在 `data/`
- **判分**：官方 harness（`swebench` 5.0.2，docker）配新 schema 数据集取交集，纯本地执行、不消耗模型额度
- **汇总**：`tools/eval_report.py` 生成跨 run 对比表；每个 run 带 `run_meta.json`（状态）+ `metrics.json`（步数/截断/检索）+ harness 报告
- **工具扩展**：`EXTRA_TOOLS` 注册表 + `model.extra_tools` 开关，默认空 = 纯 bash（与基线逐字节一致）

## 三、后续方向

- **稳定性**：工具版 +12pp 压在统计边界上（与基线区间重叠 58%），下一步复跑两次取均值，确认方向是否稳定。
- **瓶颈转移**：工具解决的是"查资料"，解决不了"急着交卷"——4 个实例共 8 个回归、`sphinx-8269`/`8475`
  十几步就提交。下一步做**提交前自检 gate**（跑相关测试 + 不许弄坏旧测试才放行），这属于 agent 控制流改动，不是加工具。

### 工程产出

- **工具注册表**：`EXTRA_TOOLS` + `model.extra_tools` 开关 + 参数校验，默认 bash-only，40 项单测覆盖
- **评测仪表盘**：Wilson 置信区间、`PASS_TO_PASS` 回归数、检索率、与基线的区间重叠比例，一条命令汇总全部实验
- **文档一致性**：README 与报告的 TL;DR 块由脚本强制同步，避免数字漂移
- **发布流水线**：白名单同步、密钥扫描、残留清理，默认不提交

## 四、快速上手

```bash
# 1) 跑一个实例（先确认端到端可用）
docker ps -a --filter name=minisweagent- -q | xargs -r docker rm -f
uv run python -m minisweagent.run.benchmarks.swebench_single \
  --subset data/swe-bench-verified-mini --split test \
  -i django__django-11790 -m "openai/<模型ID>" -y --exit-immediately

# 2) 批量跑（断点续跑；同一时刻只跑一个批量任务）
MSWEA_COST_TRACKING=ignore_errors \
uv run python -m minisweagent.run.benchmarks.swebench \
  --subset data/swe-bench-verified-mini --split test \
  -m "openai/<模型ID>" -c swebench.yaml -c agent.mode=yolo \
  -w 2 -o experiments/runs/<run_name>

# 3) 官方 harness 判分（纯本地，不耗模型额度）
HTTP_PROXY=<你的代理> uv run python -m swebench.harness.run_evaluation \
  -d SWE-bench/SWE-bench_Verified -s test \
  -p experiments/runs/<run_name>/preds.json --max_workers 2 \
  -id <run_id> --report_dir experiments/runs/<run_name>/report

# 4) 生成跨 run 对比仪表盘
uv run python tools/eval_report.py

# 5) 单测
uv run pytest tests/models/test_actions_toolcall.py tests/tools/ -q
```

### 环境注意（踩过的坑）

- **火山方舟 API 走直连**（国内端点），socks 代理会让部分模型报 `Connection error`；
  而加载 HF 数据集/harness 需要代理 → 常用组合是「unset 代理 + `--subset data/swe-bench-verified-mini` 本地数据」。
- **同一时刻只跑一个批量任务**：各脚本启动时会全局清理 `minisweagent-*` 容器，两个批量会互相杀。
- **Coding Plan 有 5 小时滚动配额**，并发建议 `-w 2`；economy 档位在 agent 长上下文负载下会挂死，不建议使用。
- 判分必须用 **新 schema** 的 `SWE-bench/SWE-bench_Verified`；直接喂 mini 旧 schema 会因缺 `image` 字段失败。

## 五、目录结构

```
src/minisweagent/          上游框架（本仓库新增：models/utils/actions_toolcall.py 的工具注册表）
tools/
  eval_report.py           跨 run 评测仪表盘（resolved + CI + 回归数 + 检索率）
  publish.sh               发布同步脚本（白名单式、默认不提交）
experiments/
  REPORT.md                ★ 入口报告：方法、基线、三个发现、负结果与局限
  runs/baseline/           全量 50 题基线：NOTES/SUMMARY + preds.json + report/ + metrics.json
  runs/probes/             2 题快速探针（retrieval-prompt、retrieval-tool、hard-case-rerun、models/*）
  runs/_dashboard.md       自动生成的跨 run 对比表
  examples/                3 条代表性轨迹（失败/检索成功/早提交带回回归）
  verified_mini_baseline/  数据集清单、镜像清单、续跑/判分脚本、工具开关配置
data/                      数据集本地副本（mini 旧 schema + verified 新 schema）
tests/                     框架单测 + 本仓库新增功能的测试
```

> 说明：逐实例完整轨迹（约 26 MB）不随仓库发布，仅在本地保留；
> 发布副本只包含轻量、可读、可复验的产物（报告 + preds + metrics + 3 条样例轨迹）。

## 六、许可

沿用上游 [LICENSE.md](LICENSE.md)。
