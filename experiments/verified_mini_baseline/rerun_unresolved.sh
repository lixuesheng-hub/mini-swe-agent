#!/usr/bin/env bash
# 重跑基线的 18 个 unresolved（8056/8638 已单独重跑，结果在 probes/hard-case-rerun）。
# 同模型同配置 w=2，独立目录，断点续跑（preds.json），撞配额可直接重跑本脚本。
set -x
cd "$(dirname "$0")/../.."   # 仓库根目录（脚本位于 experiments/verified_mini_baseline/）
docker ps -a --filter name=minisweagent- --format '{{.Names}}' | xargs -r docker rm -f
# 如所在网络需要代理（例如经代理访问 HF），请运行前自行设置：
#   export HTTP_PROXY=... HTTPS_PROXY=... ALL_PROXY=...
export MSWEA_COST_TRACKING=ignore_errors
exec uv run python -m minisweagent.run.benchmarks.swebench \
  --subset MariusHobbhahn/swe-bench-verified-mini --split test \
  --filter '^(?:django__django-11848|django__django-11885|django__django-11964|django__django-12273|django__django-12308|django__django-12325|django__django-12406|sphinx-doc__sphinx-10323|sphinx-doc__sphinx-10435|sphinx-doc__sphinx-10673|sphinx-doc__sphinx-7590|sphinx-doc__sphinx-7748|sphinx-doc__sphinx-7985|sphinx-doc__sphinx-8269|sphinx-doc__sphinx-8475|sphinx-doc__sphinx-8548|sphinx-doc__sphinx-9230|sphinx-doc__sphinx-9461)$' \
  -m "openai/doubao-seed-2-1-lite-260915" \
  -c swebench.yaml -c agent.mode=yolo \
  -w 2 -o experiments/runs/rerun_unresolved_w2
