#!/usr/bin/env bash
# 全量 50 题：doubao-lite + github_fetch 工具（原版提示词，仅注册工具）
# 唯一变量 = model.extra_tools=[github_fetch]；提示词、模型、并发与基线一致。
# 断点续跑：撞 5h 配额或中断后，直接重跑本脚本（已完成的实例会跳过）。
set -x
cd "$(dirname "$0")/../.."   # 仓库根目录（脚本位于 experiments/verified_mini_baseline/）

# 火山方舟是国内端点 -> 直连；数据集用本地副本，避免 HF 需要代理
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
export MSWEA_COST_TRACKING=ignore_errors

# 清理残留容器（同一时刻只能有一个 swebench 批量任务！）
docker ps -a --filter name=minisweagent- --format '{{.Names}}' | xargs -r docker rm -f

RUN_DIR=experiments/runs/retrieval-tool-50
mkdir -p "$RUN_DIR"

# 首次运行写元数据（exploratory：出结论后再改 confirmed）
if [ ! -f "$RUN_DIR/run_meta.json" ]; then
  cat > "$RUN_DIR/run_meta.json" <<JSON
{
  "status": "exploratory",
  "model": "openai/doubao-seed-2-1-lite-260915",
  "instances": 50,
  "variable": "原版提示词 + 注册 github_fetch 工具（无提示引导）",
  "report_ref": null,
  "started": "$(date +%Y-%m-%d)",
  "started_at": "$(date -Is)"
}
JSON
fi

exec uv run python -m minisweagent.run.benchmarks.swebench \
  --subset data/swe-bench-verified-mini --split test \
  -m "openai/doubao-seed-2-1-lite-260915" \
  -c swebench.yaml \
  -c experiments/verified_mini_baseline/enable_github_tool.yaml \
  -c agent.mode=yolo \
  -w 2 \
  -o "$RUN_DIR"
