#!/usr/bin/env bash
# 断点续跑 verified-mini 基线（w=4）。重启电脑后直接运行本脚本。
# 已完成实例靠 ../runs/baseline/preds.json 自动跳过。
set -x
cd "$(dirname "$0")/../.."   # 仓库根目录（脚本位于 experiments/verified_mini_baseline/）

# 1) 清理可能残留的容器
docker ps -a --filter name=minisweagent- --format '{{.Names}}' | xargs -r docker rm -f

# 2) 代理 + doubao 成本跟踪
# 如所在网络需要代理，请运行前自行 export HTTP_PROXY / HTTPS_PROXY / ALL_PROXY
export MSWEA_COST_TRACKING=ignore_errors

# 3) 续跑（输出追加到同一 console.log）
exec uv run python -m minisweagent.run.benchmarks.swebench \
  --subset MariusHobbhahn/swe-bench-verified-mini --split test \
  -m "openai/doubao-seed-2-1-lite-260915" \
  -c swebench.yaml -c agent.mode=yolo \
  -w 2 -o experiments/runs/baseline
