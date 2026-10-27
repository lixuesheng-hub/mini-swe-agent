# 实验报告：SWE Agent 脚手架与检索策略

> 一句话结论：**在同一模型、同一基准上，决定成败的关键变量是"何时、以何种方式获取外部信息"，而非模型档位本身**——但这条结论目前只有一个 n=2 的探针支撑，需要全量验证。

- 基准：SWE-bench verified-mini，50 题（django 25 + sphinx 25）
- 框架：mini-swe-agent 2.4.6，默认配置（`swebench.yaml`，step_limit 250，yolo）
- 判分：官方 harness（`swebench` 5.0.2，docker，本地执行，不消耗模型额度）
- 日期：2026-10

<!-- TLDR:START -->
基线 **30/50 = 60%**（95% CI 46–72%）；单次结果不足以判定小幅改进。
- 失败分三类：能力型 / 边界噪声型 / 早提交型（后者无法靠加工具解决）
- 工具版全量（`github_fetch`）：resolved **36/50 = 72%（+12pp）**，但与基线区间**重叠 58%** → 方向为正、未超噪声
- 工具被用起来（22/50 实例），但“用过工具”组成功率反而更低（64% vs 79%），是难度混淆而非因果
<!-- TLDR:END -->

> **文档分工**：本报告是证据层（方法、完整数据、负结果与局限）；根目录 `README.md` 是门面层
> （定位、三条头条结论、快速上手）。两者的 `TL;DR` 块必须逐字一致，由
> `uv run python tools/check_docs_sync.py` 检查——数字的唯一来源是 `runs/_dashboard.md`（脚本生成），
> 不要手工改 README 里的结论。

---

## 1. 方法

**为什么用这套基准**：SWE-bench 有客观判分（跑测试，而不是人看输出），才能把"感觉变好了"变成"确实变好了"；verified-mini 只需约 5 GB 镜像、保持与全量 verified 相近的难度分布，适合高频迭代。

**噪声控制**：
- 每个 run 记录 `metrics.json`（步数、截断次数、重复命令、检索实例数）与 harness 报告（F2P/P2P 明细）；
- 汇总表统一给出 **Wilson 95% 置信区间**，并统计 `PASS_TO_PASS` 回归数作为细粒度质量信号；
- 每个变体一次只改一个变量，功能代码默认关闭（`extra_tools` 为空时与基线逐字节一致）。

**指标定义**：
| 指标 | 含义 |
|---|---|
| resolved | FAIL_TO_PASS 全部通过且无 PASS_TO_PASS 回归（官方口径） |
| 回归数 | 新弄坏的旧测试数量（区分"接近正确"与"完全跑偏"） |
| 检索实例数 | 轨迹中出现网络请求（curl/wget/urllib + URL）的实例数 |
| 步数 | assistant 消息数（≈ API 调用次数） |

**怎么判断"这个改动有没有用"**（仪表盘 `vs baseline` 列的口径）：

1. **先看区间，不看单点**：每个 resolved 率都带 Wilson 95% 区间；n=50 时区间宽约 ±13pp，
   所以"60% → 70%"这种量级本身不足以支撑结论。
2. **只用同任务集的 run 互相比较**：`vs baseline` 仅在同一批题上计算。n=2 探针与 50 题基线
   任务集不同，显示「—（任务集不同）」——它们的区间宽达 [34%, 100%]，不可比。
3. **重叠比例作快速判断**：

   | 重叠宽度 ÷ 较窄区间宽度 | 判读 |
   |---|---|
   | `0%` | 不重叠，可称显著 |
   | `< 20%` | 边缘（再差 1–2 题就分开） |
   | `20–50%` | 部分重叠，说不准 |
   | `> 50%` | 明显重叠，视为无差异 |

   实测参考：基线 30/50 的区间是 [46%, 72%]；**新版要到 43/50（+13 题）才完全不重叠**，
   40/50 时仍重叠 25%。
4. **正式结论看差值区间**：重叠判据偏保守——实测 40/50 时两区间仍重叠 25%，但差值区间
   `[+2.0, +36.4]pp` 已不含 0。因此报告里写"显著"时以**差值区间是否跨 0** 为准
   （同题配对可用 McNemar）。

---

## 2. 基线

模型 `doubao-seed-2-1-lite-260915`，50 题全量：

| 分组 | resolved | 提交率 |
|---|---:|---:|
| django (25) | 18（72%） | 25/25 |
| sphinx (25) | 12（48%） | 25/25 |
| **合计** | **30/50 = 60%** | 50/50 |

- Wilson 95% CI **[46%, 72%]**——**单次 50 题不足以判定小幅改进**，这是后续所有实验的前提约束
- 基础设施失败 0、空补丁 0；步数中位 34 / 均值 45.9 / 最长 157
- 6 个实例共引入 11 个 `PASS_TO_PASS` 回归

---

## 3. 三个发现

### 3.1 单题存在随机翻转，基线数字本身有噪声

同一配置重跑两个最难实例：

| 实例 | 第一次 | 第二次 |
|---|---|---|
| `sphinx-8638` | ❌ 100 步 | ✅ 133 步 |
| `sphinx-8056` | ❌ 100 步 | ❌ 46 步 |

粗估单次 resolved 的随机误差 **±3–5 个百分点**。含义：消融差异小于 2–3 题时不应下结论。

### 3.2 失败不是一类事——至少三种

| 类型 | 代表实例 | 特征 |
|---|---|---|
| 能力/理解型 | `8056` | 多个模型多次尝试均卡在同一目标测试 |
| 边界噪声型 | `8638` | 所有模型最终都能解，单次结果不可靠 |
| 早提交/回归型 | `8269`、`8475` | 14–19 步就提交，目标测试部分通过却引入多个回归 |

这解释了为什么"只看 resolved 率"会掩盖信息：加 `回归数` 后，`glm-5.3` 那唯一的失败立刻显示为"还弄坏了 1 个旧测试"。

### 3.3 检索策略是决定性变量（**探针结论，n=2**）

探针设计：固定模型（doubao-lite）与框架，只改"检索能力的呈现方式"，在 `8056` + `8638` 两题上对比。

| 变体 | 8056 | 8638 | 检索次数 | 步数 |
|---|:---:|:---:|---:|---:|
| 基线（无提示、无工具） | ❌ | ❌→✅ | 1（被动、晚） | 100 / 100 |
| **prompt 提示**（提示先查 issue/PR） | ✅ | ✅ | 5 | **21** |
| 独立工具 `github_fetch`（无提示） | ✅ | ❌ | 4（仅 8056） | 55 / 98 |
| glm-5.3 | ❌ | ✅ | — | 84 / 66 |
| kimi-k3 | ✅ | ✅ | — | 43 / 54 |
| deepseek-v4-pro | ✅ | ✅ | — | 42 / 75 |
| deepseek-v4.1-flash | ✅ | ✅ | — | **21** / **31** |

读法：
1. **同一模型同一题**，只加一段检索提示：100 步失败 → 21 步成功，且步数与最强模型持平；
2. **工具不会自动被用**：`github_fetch` 无提示时，模型在 8638 上一次都没调用（0 次）→ "给工具"≠"会用工具"，需要提示引导；
3. **基线并非完全不检索**，而是 4/50 实例检索过且多为"卡住后的被动查询"（这 4 个仅 1 个成功，未检索的 46 个成功率 63%）。

### 3.4 全量验证：工具版 +12pp，但仍在噪声内

把同样的工具变体推到**全量 50 题**（唯一改动仍是注册 `github_fetch`，提示词保持原样）：

| 指标 | 基线 | 工具版全量 | 变化 |
|---|---:|---:|---|
| resolved | 30/50 = 60% | **36/50 = 72%** | **+12pp（+6 题）** |
| 95% CI | [46%, 72%] | [58%, 83%] | **重叠 58%** → 明显重叠，不显著 |
| django / sphinx | 18 / 12 | 20 / 16 | +2 / +4 |
| 回归实例（回归数） | 6（11） | 4（8） | 略降 |
| 步数中位 | 34 | 32 | 略降 |
| 检索实例 | 4/50 | **22/50** | 大幅上升 |

逐题：新解决 7 题，新失败 1 题（`sphinx-9229`）。

**关键读法**：

1. **+12pp 不能称为提升**。按区间判据，50 题规模需 +13 题（43/50）才不重叠；
   本次是"方向为正但未超出噪声"的典型样本。
2. **工具确实被用起来了**：63 次调用、22 个实例（44%），远高于基线自发检索的 4/50。
3. **但"用过工具"组成功率更低**（64% vs 79%）：这是**难度混淆**——题目越难模型才越可能去查，
   不代表工具导致失败。想拆开因果需要同题配对比较，目前数据不支持。
4. **早提交型失败没被改善**：`sphinx-8269`（25 步）、`sphinx-8475`（40 步）仍失败，
   各只用 1 次工具 → 工具教会了"查资料"，但没教会"别急着交卷"。

---

## 4. 负结果与局限（重要）

- **n=2 的探针不能当全量结论**。上表的 100% 只代表两题；必须跑全量 50 题并给出差值 CI，否则不能声称"提升 X 个百分点"。
- **开卷问题**：部分成功来自查阅上游 PR/issue，属于"开卷"能力。报告与评分应区分 **lookup 成功** 与 **独立解出**；混合统计会高估模型能力。
- **失败尝试**：
  - `deepseek-v4.1-flash-economy` 在 agent 真实负载（长 system prompt + 工具历史）下单次请求挂死、并发触发服务端突发保护，**不可用于 agent 场景**；
  - `w=4` 并发会更快撞上套餐 5 小时滚动配额，故统一 `w=2`。
- **相关性≠因果**：工具版里"用过 github_fetch"组成功率更低（64% vs 79%），
  统计上属难度混淆（难题才触发检索），不能据此说工具无效或有害；需同题配对分析。
- **未验证**：`run_test` 精准测试工具、提交自检 gate、上下文压缩、best-of-N 的实际收益目前只有假设与设计，尚无实验数据。

---

## 5. 实验记录（每个 run 一行）

> 规则：**只有 `status: confirmed` 的 run 才能进本表并支撑结论**；探索性实验标 `exploratory`（也列出来，但注明"未采用"），
> 被推翻的标 `superseded`，失败的尝试标 `discarded`。每个 run 目录下的 `run_meta.json` 是该状态的唯一事实源，
> 仪表盘 `runs/_dashboard.md` 会显示 status 列。

| run | 变量（唯一改动） | n | resolved | 结论 | status |
|---|---|---:|---:|---|---|
| `runs/baseline` | 无（默认配置基线） | 50 | 30 | 60%，CI [46,72]；见 §2 | confirmed |
| `runs/probes/hard-case-rerun` | 同配置重跑两难题 | 2 | 1 | 8638 一败一成 → 存在随机翻转；见 §3.1 | confirmed |
| `runs/probes/retrieval-prompt` | prompt 加"先查 issue/PR" | 2 | 2 | 两题全过，8056 仅 21 步；但 n=2；见 §3.3 | confirmed |
| `runs/probes/retrieval-tool` | 新增 `github_fetch`，不加提示 | 2 | 1 | 工具被自发使用但未覆盖 8638（0 次调用）；见 §3.3 | confirmed |
| `runs/probes/models/glm-5.3` | 换模型 | 2 | 1 | 8056 失败且引入 1 个回归 | confirmed |
| `runs/probes/models/kimi-k3` | 换模型 | 2 | 2 | 两题全过 | confirmed |
| `runs/probes/models/ds-v4-pro` | 换模型 | 2 | 2 | 两题全过 | confirmed |
| `runs/probes/models/ds-v4.1-flash` | 换模型 | 2 | 2 | 两题全过，步数最少（21/31） | confirmed |
| `runs/retrieval-tool-50` | 原版提示词 + `github_fetch` 工具 | 50 | 36 | 72%（+12pp），与基线区间重叠 58% → 未显著；见 §3.4 | confirmed |
| `_local/archive/economy-unusable` | deepseek-v4-1-flash-economy | — | — | 真实负载下请求挂死，不可用；见 §4 | discarded |
| `_local/archive/unresolved-rerun-interrupted` | 重跑 18 个 unresolved | — | — | 实验中断，未得出结果 | discarded |

**待补的实验（不写结论）**：工具版复跑 2 次压噪声、提交前自检 gate、`run_test` 工具、上下文压缩（已评估为暂缓，见 §4）。

---

## 6. 工程产出

- **可插拔工具注册表**：`src/minisweagent/models/utils/actions_toolcall.py`（`EXTRA_TOOLS` + `get_enabled_tools`），新工具只需 spec + "参数→bash 命令"翻译函数；
- **默认关闭**：`LitellmModelConfig.extra_tools` 默认为空 = 纯 bash，基线行为逐字节可复现；
- **评测仪表盘**：`tools/eval_report.py` → 跨 run 对比表（resolved/CI/回归数/步数/检索率）；
- **发布脚本**：`tools/publish.sh`（白名单式同步、密钥扫描、默认不提交）；
- **测试**：`tests/models/test_actions_toolcall.py`（工具注册与参数校验）、`tests/tools/test_eval_report.py`（指标口径）。

---

## 7. 复现

```bash
# 跑一个实例（先验证端点与镜像）
uv run python -m minisweagent.run.benchmarks.swebench_single \
  --subset data/swe-bench-verified-mini --split test \
  -i django__django-11790 -m "openai/<模型ID>" -y --exit-immediately

# 全量跑（断点续跑；同一时刻只跑一个批量任务）
MSWEA_COST_TRACKING=ignore_errors \
uv run python -m minisweagent.run.benchmarks.swebench \
  --subset data/swe-bench-verified-mini --split test \
  -m "openai/<模型ID>" -c swebench.yaml -c agent.mode=yolo \
  -w 2 -o experiments/runs/<name>

# 官方判分（本地 docker，不耗模型额度）
uv run python -m swebench.harness.run_evaluation \
  -d SWE-bench/SWE-bench_Verified -s test \
  -p experiments/runs/<name>/preds.json --max_workers 2 \
  -id <run_id> --report_dir experiments/runs/<name>/report

# 汇总
uv run python tools/eval_report.py
```

目录：`runs/baseline`（全量 50）、`runs/probes/*`（2 题探针）、`examples/`（3 条代表性轨迹）。

---

## 8. 结论与下一步

**能说的**：基线 60%（CI 46–72%）；失败可分三类；检索策略在同题同模型上带来数量级差异；工具需要提示才会被使用。
**不能说的**：任何"全量提升 X 个百分点"的断言——还没测。

下一步（按优先级）：
1. 把 prompt 检索变体推到全量 50 题，给出带 CI 的差值；
2. 关键配置跑 3 次重复，估计 run 间方差；
3. 再做 `run_test` / 提交 gate / 上下文压缩的单项消融。

---

## 附录：新增一个实验的标准流程

```bash
# 1) 跑实验（默认就是 exploratory，不需要先放临时目录）
MSWEA_COST_TRACKING=ignore_errors uv run python -m minisweagent.run.benchmarks.swebench \
  --subset data/swe-bench-verified-mini --split test -m "openai/<模型>" \
  -c swebench.yaml -c agent.mode=yolo -w 2 -o experiments/runs/probes/<名字>

# 2) 判分
uv run python -m swebench.harness.run_evaluation -d SWE-bench/SWE-bench_Verified -s test \
  -p experiments/runs/probes/<名字>/preds.json --max_workers 2 \
  -id <run_id> --report_dir experiments/runs/probes/<名字>/report

# 3) 落元数据（此时先标 exploratory）
cat > experiments/runs/probes/<名字>/run_meta.json <<'JSON'
{"status": "exploratory", "model": "openai/<模型>", "instances": 50,
 "variable": "<唯一改动>", "report_ref": null, "started": "YYYY-MM-DD"}
JSON

# 4) 写 NOTES.md（假设 / 唯一变量 / 结果表 / 结论 / 踩坑）

# 5) 刷新仪表盘（会自动生成 metrics.json）
uv run python tools/eval_report.py
```

**转正**：当某次实验支撑了报告里的结论 → 把 `run_meta.json` 的 `status` 改成 `confirmed`、
填 `report_ref`、在 §5 表里加一行、必要时更新 §3 与 §8。
**放弃**：改 `discarded` 或移到 `experiments/_local/archive/`（不会发布，但保留痕迹）。

纪律：**任何进报告的数字必须来自 `confirmed` 的 run；任何 `confirmed` 的 run 必须有完整 NOTES。**
