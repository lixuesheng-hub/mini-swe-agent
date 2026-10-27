#!/usr/bin/env bash
# 把当前项目复制到一个干净的发布目录，并（可选）提交/推送到 GitHub 公开仓库。
#
# 用法：
#   bash tools/publish.sh                       # 只复制
#   REPO_URL=git@github.com:you/repo.git bash tools/publish.sh   # 复制 + 提交 + 推送
#   DEST_DIR=/path/to/out bash tools/publish.sh # 自定义目标目录
#   DRY_RUN=1 bash tools/publish.sh             # 只看会复制什么
#
# 排除项在下面的 EXCLUDE 数组里增删即可。
set -euo pipefail

# ======================== 配置区 ========================
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST_DIR="${DEST_DIR:-$(cd "$SRC_DIR/.." && pwd)/mini-swe-agent-publish}"
REPO_URL="${REPO_URL:-}"                       # 留空则只复制不推送
BRANCH="${BRANCH:-main}"
COMMIT_MSG="${COMMIT_MSG:-}"
DRY_RUN="${DRY_RUN:-0}"
COMMIT="${COMMIT:-0}"        # 0=只同步不提交（默认，方便看 diff）；1=提交（并可选推送）
PUBLISH_EVIDENCE="${PUBLISH_EVIDENCE:-0}"   # 0=只发布轻量产物（默认）；1=连全量轨迹一起发布发布

# 1) 永远排除：本地环境与构建产物（一般不要动）
ALWAYS_EXCLUDE=(
  .git
  .venv .venv_linux .venv_windows
  __pycache__ .pytest_cache .mypy_cache .ruff_cache
  .idea .vscode
)

# 2) 目标目录额外排除：IDE / 构建残留不传输（已存在的也不删，因为只覆盖）
DEST_CLEAN=(
  .idea .vscode
  __pycache__ .pytest_cache .mypy_cache .ruff_cache
)

# 3) 用户的发布排除清单（不传输；目标里已有同名的也保留，不做删除）
EXCLUDE=(
  roadmap        # 阶段性路线图/实验笔记，暂不公开；以后要公开就删掉这一行
  logs           # harness 原始测试输出，体积大（~15M），关键结论已在 experiments/runs 的报告里
  mydocs         # 个人过程笔记（AGENT_LOG / RUN_REPORT / TRAJECTORY），不公开
  backups        # 本地实验快照 tar 包，体积大且与 experiments/ 冗余
  uv.lock        # 依赖锁定文件不发布（上游 .gitignore 本来就忽略它）
  _local         # 本地归档：未完成的 run / 中断实验 / 被丢弃的中间产物
)

# 3b) 实验产物瘦身：只发布轻量、可读、可复验的产物
#     全量轨迹留本地（65 条约 26MB）；代表性轨迹在 experiments/examples/
EVIDENCE_EXCLUDE=(
  '/experiments/runs/**/*.traj.json'   # 逐实例完整轨迹 → 太大，只保留 examples/
  '*/report/*trial*.json'  # 试跑子集报告，与全量报告重复
  'console.log'            # 终端原始输出
  '*_console.log'          # report/full_console.log 等变体
  'exit_statuses_*.yaml'   # 进度条状态快照
  'minisweagent.log'       # 运行日志（NOTES.md 已提炼）
)

# 4) 保护项：仅保留目标目录已有的版本（不传输、也**不删除**）
#    适用场景：目标目录是你从上游 clone 来的，已带 GitHub 配置等文件。
PROTECT=(
  .github        # CI workflow / issue 模版等，保留目标目录里的版本
)
# =======================================================

die() { echo "ERROR: $*" >&2; exit 1; }
log() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

command -v rsync >/dev/null || die "需要 rsync"
command -v git   >/dev/null || die "需要 git"

log "源目录: $SRC_DIR"
log "目标目录: $DEST_DIR"
echo "排除: ${ALWAYS_EXCLUDE[*]} ${EXCLUDE[*]}"

# 目标目录安全检查：已存在且非空、又不是我们之前创建的 git 仓库时，默认拒绝覆盖
if [ -d "$DEST_DIR" ] && [ -n "$(ls -A "$DEST_DIR" 2>/dev/null || true)" ] && [ ! -d "$DEST_DIR/.git" ]; then
  [ "${FORCE:-0}" = "1" ] || die "目标目录非空且不是 git 仓库：$DEST_DIR（确认要覆盖请加 FORCE=1）"
fi

mkdir -p "$DEST_DIR"

# 只覆盖，不删除：目标目录里多出来的文件保留（不加 --delete）
# 实验发布策略：只发布 status=confirmed 的 run（默认）；PUBLISH_ALL_RUNS=1 可全发。
PUBLISH_ALL_RUNS="${PUBLISH_ALL_RUNS:-0}"
RSYNC_ARGS=(-a --human-readable --info=stats2)
for e in "${ALWAYS_EXCLUDE[@]}" "${EXCLUDE[@]}" "${PROTECT[@]}"; do
  RSYNC_ARGS+=("--exclude=$e")
done
if [ "$PUBLISH_EVIDENCE" != "1" ]; then
  for e in "${EVIDENCE_EXCLUDE[@]}"; do
    RSYNC_ARGS+=("--exclude=$e")
  done
fi
if [ "$PUBLISH_ALL_RUNS" != "1" ]; then
  # 逐个 run 读 run_meta.json，非 confirmed 的整个目录不发布
  while IFS= read -r meta; do
    run_dir="$(dirname "$meta")"
    status="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('status','unknown'))" "$meta" 2>/dev/null || echo unknown)"
    if [ "$status" != "confirmed" ]; then
      RSYNC_ARGS+=("--exclude=/${run_dir#./}/")
      echo "skip ($status): $run_dir"
    fi
  done < <(find "$SRC_DIR/experiments/runs" -name run_meta.json 2>/dev/null)
fi
# 保险：不把任何形式的密钥文件带出去
RSYNC_ARGS+=(--exclude='.env' --exclude='.env.*' --exclude='*.pem' --exclude='auth.json')

if [ "$DRY_RUN" = "1" ]; then
  log "DRY RUN（不实际写入）"
  rsync "${RSYNC_ARGS[@]}" --dry-run "$SRC_DIR/" "$DEST_DIR/"
  exit 0
fi

log "同步文件（只覆盖、不删除）"
rsync "${RSYNC_ARGS[@]}" "$SRC_DIR/" "$DEST_DIR/"

# ---------------- 清理改名/删除后的残留 run 目录 ----------------
# 默认"只覆盖不删除"；但 experiments/runs/* 是生成物，源仓库已不存在的 run 目录
# 会在目标里累积成重复内容，故提供显式开关。
if [ "${PRUNE_RUNS:-0}" = "1" ] && [ -d "$DEST_DIR/experiments/runs" ]; then
  for d in "$DEST_DIR/experiments/runs"/*/; do
    name="$(basename "$d")"
    if [ ! -e "$SRC_DIR/experiments/runs/$name" ]; then
      echo "prune stale run dir: experiments/runs/$name"
      rm -rf -- "${d%/}"
    fi
  done
fi

# ---------------- .gitignore 覆盖块（幂等重写）----------------
# 上游 .gitignore 全局忽略 *.traj.json / preds.json：
#   - experiments/examples/ 是"策展证据"，任何模式下都必须入库；
#   - experiments/runs/ 的全量轨迹只在 PUBLISH_EVIDENCE=1 时入库。
MARKER="# --- publish override (tools/publish.sh) ---"
{
  echo ""
  echo "$MARKER"
  echo "# IDE 配置（.gitignore 覆盖块里统一忽略）"
  echo ".idea/"
  echo ".vscode/"
  echo "!experiments/examples/**"
  if [ "$PUBLISH_EVIDENCE" = "1" ]; then
    echo "!experiments/runs/**/*.traj.json"
    echo "!experiments/runs/**/preds.json"
  fi
} > /tmp/_publish_gitignore_block

# 先删掉旧的覆盖块（从 marker 到文件尾，覆盖块永远在末尾），再追加当前版本
python3 - "$DEST_DIR/.gitignore" "$MARKER" /tmp/_publish_gitignore_block <<'PYEOF'
import sys
from pathlib import Path
target, marker, block = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
text = target.read_text() if target.is_file() else ""
head, sep, _ = text.partition(f"\n{marker}")
target.write_text((head if sep else text.rstrip()) + "\n" + block.read_text())
PYEOF
rm -f /tmp/_publish_gitignore_block

# ---------------- 发布前安全检查：密钥扫描 ----------------
log "安全检查：扫描疑似密钥"
PATTERNS='ark-[0-9a-f]{8}-[0-9a-f]{4}|sk-[A-Za-z0-9]{20,}|OPENAI_API_KEY=["'\'']?[A-Za-z0-9-]{16,}'
if grep -rIlE "$PATTERNS" "$DEST_DIR" \
     --exclude-dir=.git --exclude-dir=backups 2>/dev/null | head -5 | grep -q .; then
  echo "发现疑似密钥的文件：" >&2
  grep -rIlE "$PATTERNS" "$DEST_DIR" --exclude-dir=.git --exclude-dir=backups 2>/dev/null | head -5 >&2
  die "已中止发布，请先清理上述文件"
fi
echo "未发现明文密钥"

# ---------------- git（默认只同步，不提交）----------------
cd "$DEST_DIR"
if [ ! -d .git ]; then
  log "初始化 git 仓库"
  git init -q -b "$BRANCH"
fi
# 避免 Windows 盘符被 autocrlf 改写成 CRLF，导致 diff 全是换行符噪声
git config core.autocrlf false

if [ "$COMMIT" != "1" ]; then
  cat <<EOF

已同步到：$DEST_DIR（未提交，方便 review diff）

  cd "$DEST_DIR"
  git status --short          # 改了/新增了哪些
git diff                     # 看具体改动
git diff --stat              # 只看统计

确认后自己提交：
  git add -A && git commit -m "..."
或让脚本提交并推送：
  COMMIT=1 REPO_URL=git@github.com:<账号>/<仓库名>.git bash tools/publish.sh
EOF
  log "完成（无提交）"
  echo "文件数: $(find "$DEST_DIR" -type f -not -path '*/.git/*' | wc -l)"
  exit 0
fi

if ! git config user.email >/dev/null; then
  git config user.email "publish@localhost"
  git config user.name "publish-script"
fi

git add -A
if git diff --cached --quiet; then
  echo "没有变更需要提交"
else
  [ -n "$COMMIT_MSG" ] || COMMIT_MSG="chore: publish $(date +%Y-%m-%d)"
  log "提交：$COMMIT_MSG"
  git commit -q -m "$COMMIT_MSG"
fi

# ---------------- 推送 ----------------
if [ -n "$REPO_URL" ]; then
  if git remote get-url origin >/dev/null 2>&1; then
    git remote set-url origin "$REPO_URL"
  else
    git remote add origin "$REPO_URL"
  fi
  log "推送到 $REPO_URL ($BRANCH)"
  git push -u origin "$BRANCH"
else
  cat <<EOF

已提交到本地仓库：$DEST_DIR
尚未配置远端。创建 GitHub 公开仓库后执行：

  cd "$DEST_DIR"
  git remote add origin git@github.com:<你的账号>/<仓库名>.git
  git push -u origin $BRANCH

或直接重跑本脚本并传 REPO_URL：
  REPO_URL=git@github.com:<账号>/<仓库名>.git bash tools/publish.sh
EOF
fi

log "完成"
echo "文件数: $(find "$DEST_DIR" -type f -not -path '*/.git/*' | wc -l)"
echo "体积:   $(du -sh --exclude=.git "$DEST_DIR" | cut -f1)"
