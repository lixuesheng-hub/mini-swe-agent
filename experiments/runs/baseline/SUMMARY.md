# Baseline: mini-swe-agent on SWE-bench verified-mini (50)

- 日期：2026-10-22
- 模型：`openai/doubao-seed-2-1-lite-260915`（火山方舟 Coding Plan 端点 `/api/coding/v3`，doubao lite）
- Agent：mini-swe-agent 2.4.6 默认配置（`swebench.yaml`，step_limit=250，cost_limit=3，yolo）
- 数据集：`MariusHobbhahn/swe-bench-verified-mini`（test，50：django 25 + sphinx 25）
- 验证：swebench 5.0.2（新 schema harness）+ `SWE-bench/SWE-bench_Verified` 数据集取交集，max_workers=2
- 产物：每实例 `<id>/<id>.traj.json`、`preds.json`、`report/openai__doubao-seed-2-1-lite-260915.baseline.json`

## 主指标

| 分组 | resolved | 提交率 |
|---|---|---|
| django (25) | **18 / 25 = 72%** | 25/25 |
| sphinx (25) | **12 / 25 = 48%** | 25/25 |
| **总计 (50)** | **30 / 50 = 60%** | 50/50 |

infra failure 0、ambiguous 0、empty patch 0、error 0。

## 效率指标（来自轨迹；成本跟踪在 doubao 下 ignore_errors，无 token/费用数据）

- assistant 步数（≈API 调用数）：全体中位 34 / 均值 45.9 / max 157
- resolved 实例：中位 26 步 / 均值 40.3
- unresolved 实例：中位 48 步 / 均值 54.3（解不出时倾向于多耗步）

## Unresolved 明细（20）

| instance | steps |
|---|---|
| django__django-11848 | 36 |
| django__django-11885 | 72 |
| django__django-11964 | 41 |
| django__django-12273 | 67 |
| django__django-12308 | 20 |
| django__django-12325 | 32 |
| django__django-12406 | 51 |
| sphinx-doc__sphinx-10323 | 91 |
| sphinx-doc__sphinx-10435 | 43 |
| sphinx-doc__sphinx-10673 | 65 |
| sphinx-doc__sphinx-7590 | 44 |
| sphinx-doc__sphinx-7748 | 56 |
| sphinx-doc__sphinx-7985 | 41 |
| sphinx-doc__sphinx-8056 | 100 |
| sphinx-doc__sphinx-8269 | 19 |
| sphinx-doc__sphinx-8475 | 14 |
| sphinx-doc__sphinx-8548 | 83 |
| sphinx-doc__sphinx-8638 | 100 |
| sphinx-doc__sphinx-9230 | 17 |
| sphinx-doc__sphinx-9461 | 94 |

## 复现实验命令

```bash
# 跑 agent（w=2；注意 Coding Plan 5 小时滚动配额）
bash experiments/verified_mini_baseline/resume_baseline.sh
# 官方验证（不消耗模型额度，自动跳过已完成）
bash experiments/verified_mini_baseline/run_eval_full.sh
```

## 已知环境注意（后续消融沿用）

1. 模型端点必须用 `/api/coding/v3`（包月）；`/api/v3` 按量账户曾欠费。
2. Coding Plan 有 5 小时滚动用量配额，w=4 会快速撞顶；固定 w=2。
3. 验证 harness 是新 schema（swebench 5.0.2），数据集必须用 `SWE-bench/SWE-bench_Verified`，不能用 mini 旧 schema 直连。
