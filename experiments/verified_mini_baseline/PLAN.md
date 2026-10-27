# SWE-bench verified-mini 基线执行计划（50 任务）

> **运维与命令速查见 [`RUNBOOK.md`](RUNBOOK.md)**；本文是早期计划留档，部分细节已过时。

> 状态：**Phase 0–5 全部完成（2026-10-22）。基线 resolved 30/50 = 60%（django 18/25、sphinx 12/25）。**
> 汇总见 `../runs/baseline_doubao_lite/SUMMARY.md`。关键修正：验证用 swebench 5.0.2 新 harness，数据集须用 `SWE-bench/SWE-bench_Verified`（mini 旧 schema 缺 image 字段）。

## 0. 已确认的事实

- 数据集：`MariusHobbhahn/swe-bench-verified-mini`，仅 **test split，50 条**（django 25 + sphinx 25）。
- 本地副本：`data/swe-bench-verified-mini/test-00000-of-00001.parquet`（181 KB）。
- Schema 为**旧版**：字段 `FAIL_TO_PASS / PASS_TO_PASS / patch / test_patch` 等，**无** `image / eval_script`
  → 跑 agent 无影响；**官方验证必须用旧版 harness（pip 包 `swebench`，princton-nlp 系）**，不能用 SWE-bench/SWE-bench 新 schema harness（否则缺 `image` 报 KeyError）。
- 批量入口：`src/minisweagent/run/benchmarks/swebench.py`
  - `--subset` 可直接传 HF 数据集名或本地路径；自带**断点续跑**（读 `preds.json` 跳过已完成）、`--workers` 并行、每个实例独立 `<id>.traj.json`。
- 镜像：`swebench/sweb.eval.x86_64.<id 小写, __→_1776_>:latest`，每个实例一个，共 50 个；docker pull 走 daemon 代理（8119），与 shell 代理无关。
- 模型：火山 `openai/doubao-seed-2-1-lite-260915`（`~/.config/mini-swe-agent/.env`）；doubao 不在 litellm 价目表，须设 `MSWEA_COST_TRACKING=ignore_errors`。
- 配置：默认 `swebench.yaml`（step_limit 250, cost_limit 3）；批量入口没有 `-y`，需显式 `-c swebench.yaml -c agent.mode=yolo`。
- 代理：如需访问 HF 等外网，按需设置 `HTTP(S)_PROXY`（本机实测可用）。agent 容器跑测试不需要外网，主要拉镜像/拉数据集用。

## 1. 目录约定（为后续消融实验可比）

```
experiments/
  verified_mini_baseline/
    PLAN.md                  # 本文件
    instance_ids.txt         # 50 个 id 固定顺序
    images.txt               # 50 个 docker 镜像名
  runs/
    baseline_doubao_lite/     # 基线（当前配置 + doubao lite）
      preds.json             # 批量脚本自动维护（dict 格式）
      preds.jsonl            # 转换出的官方 harness 输入
      <instance_id>.traj.json# 每个任务完整轨迹（核心基线产物）
      minisweagent.log
      report/                # 官方 harness 验证结果（resolved 等）
    ablate_<name>/           # 后续每个消融一个独立同构目录
```

对比基线时，每个消融实验保持：同数据集顺序、同模型、同 `swebench.yaml`（只改被消融项，用额外 `-c key=value` 或单独 yaml）、同验证 harness。

## 2. 执行阶段

### Phase 0 — 数据准备（✅ 已完成）

- [x] parquet 下载到 `data/swe-bench-verified-mini/`
- [x] 校验 50 行、12 字段、id 列表
- [ ] 执行时生成 `instance_ids.txt` 与 `images.txt`（pandas 读 parquet，按 `__`→`_1776_` 规则）

### Phase 1 — 冒烟测试（1 个实例，验证全链路）

用已踩过坑、镜像可能已缓存的 `django__django-11790`（该 id 在 **test** split）：

```bash
docker ps -a --filter name=minisweagent- --format '{{.Names}}' | xargs -r docker rm -f
cd /path/to/mini-swe-agent
HTTP_PROXY=<你的代理> HTTPS_PROXY=<你的代理> ALL_PROXY=<你的代理> \
MSWEA_COST_TRACKING=ignore_errors \
uv run python -m minisweagent.run.benchmarks.swebench_single \
  --subset MariusHobbhahn/swe-bench-verified-mini --split test \
  -i django__django-11790 \
  -m "openai/doubao-seed-2-1-lite-260915" -y --exit-immediately
```

验收点：
1. 数据集经 HF 缓存正常加载（失败则改用 `--subset data/swe-bench-verified-mini` 本地路径）；
2. docker 镜像能拉能起，容器内 `/testbed`、`conda activate testbed`（BASH_ENV）正常；
3. agent 正常结束并在 `~/.config/mini-swe-agent/last_swebench_single_run.traj.json` 产出 patch；
4. doubao 工具调用格式可被解析（重点观察前几轮有无 tool call 解析失败循环）。

### Phase 2 — 预拉取 50 个 docker 镜像（最大耗时/磁盘项）

- 依据 `images.txt` 串行 `docker pull`（可 `xargs -P2` 并行，daemon 代理已配）。
- 预计总下载量数十 GB（同 repo 共享层），**执行前确认 WSL/docker 数据盘剩余空间 ≥ 80 GB**。
- 拉完用 `docker image inspect` 逐个核对，记录失败清单并重试；镜像不全不进入 Phase 3，避免批量任务中途卡拉取。
- django 镜像约 2–4 GB/个、sphinx 类似；建议后台执行并落日志。

### Phase 3 — 批量跑 50 任务（基线轨迹）

```bash
docker ps -a --filter name=minisweagent- --format '{{.Names}}' | xargs -r docker rm -f
cd /path/to/mini-swe-agent
HTTP_PROXY=<你的代理> HTTPS_PROXY=<你的代理> ALL_PROXY=<你的代理> \
MSWEA_COST_TRACKING=ignore_errors \
uv run python -m minisweagent.run.benchmarks.swebench \
  --subset MariusHobbhahn/swe-bench-verified-mini --split test \
  -m "openai/doubao-seed-2-1-lite-260915" \
  -c swebench.yaml -c agent.mode=yolo \
  -w 2 \
  -o experiments/runs/baseline_doubao_lite
```

要点：
- `-w 2` 起步（doubao 限流未知；冒烟后可调 3–4）；容器相互隔离，镜像已本地缓存。
- **断点续跑**：中断后重跑同一命令自动跳过 `preds.json` 中已有 id；失败实例（exit_status 为异常）用 `--redo-existing --filter '^id$'` 单独重跑。
- 产物：每实例 `<id>.traj.json`（完整轨迹）+ `preds.json` + `minisweagent.log` + `exit_statuses_*.yaml`。
- 预计耗时：单实例约 10–40 分钟（模型能力/步数而定），w=2 时全程约数小时～十几小时，建议 tmux/nohup 后台。
- 成本：doubao lite 单价低，仍记录每实例 token/步数（轨迹内有），供消融对比。

### Phase 4 — 官方 harness 验证 resolved

1. `preds.json`（dict）→ `preds.jsonl`（每行 `{instance_id, model_name_or_path, model_patch}`），空 patch 也要保留行（官方计为未解决）。
2. `.venv` 已装 `swebench`（旧 harness，与 django-11790 同套）；验证前 `python -m swebench.harness.run_evaluation --help` 确认参数名（旧版为 `--dataset_name / --split / --predictions_path / --run_id / --max_workers`）。
3. 执行：

```bash
MSWEA 无关，harness 直接 docker run：
uv run python -m swebench.harness.run_evaluation \
  --dataset_name MariusHobbhahn/swe-bench-verified-mini --split test \
  --predictions_path experiments/runs/baseline_doubao_lite/preds.jsonl \
  --run_id baseline_doubao_lite --max_workers 4
```

- harness 复用同一批 `sweb.eval.*` 镜像起新容器，与 agent 阶段隔离。
- 结果在 harness 报告目录，取 `resolved_instances` 数与明细。

### Phase 5 — 基线汇总（后续对比的表头）

从 50 个 traj + harness 报告汇总到 `experiments/runs/baseline_doubao_lite/SUMMARY.md`：

- **resolved 数 / 50（主指标）**，分 repo（django/sphinx）分别统计；
- exit_status 分布（submitted / 各类异常 / 超限）；
- 每实例 steps、tokens、耗时、成本的均值/中位数/分布；
- 典型失败模式归类（工具调用解析失败、patch 为空、改错文件、测试跑错入口等），为优化点提供依据；
- 固定随机/排序：数据集顺序以 instance_id 排序，消融实验沿用。

## 3. 后续消融实验的对照纪律

1. 每次只改一个变量（prompt 模板 / step_limit / cost_limit / 观察截断长度 / 模型 / agent 策略等），用独立 `ablate_<name>` 目录。
2. 配置改动用额外 `-c key=value` 或新 yaml，**不直接改 swebench.yaml**；基线命令、git commit hash、模型版本写入各目录的 `run_meta.md`。
3. 全部跑同一 50 个 id、同一 harness、同一汇总脚本（Phase 5 脚本届时一并固化）。
4. 比对时同时看 resolved rate（正确性）和 steps/tokens/cost（效率），单看一边会误导。

## 4. 风险与注意

- 磁盘：50 镜像 + 验证容器，预留 ≥ 80 GB。
- doubao 限流/稳定性：冒烟确认；批量用低 workers + 断点续跑兜底。
- 旧 harness + mini 数据集兼容性在 Phase 4 首个实例先小范围验证（可 `--filter` 等价手段或手工裁 JSONL 跑 2 条）。
- 网络报错先测 1080 代理；docker pull 失败查 daemon 的 8119 代理而非 shell。
- 时间成本高：Phase 2/3 均建议后台 + 日志，不阻塞交互。
