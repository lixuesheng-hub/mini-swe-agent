#!/usr/bin/env bash
# Phase 4: 全量 50 实例官方 harness 验证（纯本地 docker，不消耗模型额度）。
# 新 schema 数据集 SWE-bench/SWE-bench_Verified 含 mini 全部 50 id，自动取交集。
set -x
cd "$(dirname "$0")/../.."   # 仓库根目录（脚本位于 experiments/verified_mini_baseline/）
# 如所在网络需要代理（例如经代理访问 HF），请运行前自行设置：
#   export HTTP_PROXY=... HTTPS_PROXY=... ALL_PROXY=...
exec uv run python -m swebench.harness.run_evaluation \
  -d SWE-bench/SWE-bench_Verified -s test \
  -p experiments/runs/baseline/preds.json \
  --max_workers 2 -id baseline \
  --report_dir experiments/runs/baseline/report
