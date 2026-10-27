"""Aggregate mini-swe-agent runs on verified-mini into one comparison dashboard.

Scans ``experiments/runs/*`` for:
* ``<id>/<id>.traj.json``            -> efficiency / behaviour metrics
* ``report/<model>.<run_id>.json``   -> harness verdict (resolved/...)
* ``logs/run_evaluation/<run_id>/<model_dir>/<id>/report.json``
                                     -> per-instance FAIL_TO_PASS / PASS_TO_PASS detail

Usage:
    uv run python tools/eval_report.py            # writes Markdown + CSV
"""

import json
import math
from datetime import datetime
import statistics
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "experiments" / "runs"
EVAL_LOGS = ROOT / "logs" / "run_evaluation"
IDS_FILE = ROOT / "experiments" / "verified_mini_baseline" / "instance_ids.txt"
OUT_MD = RUNS_DIR / "_dashboard.md"
OUT_CSV = RUNS_DIR / "_dashboard.csv"

DATASET_SIZE = 50


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _load(path: Path):
    return json.loads(path.read_text())


def _wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Two-sided 95% Wilson score interval for a binomial proportion."""
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return max(0.0, center - half), min(1.0, center + half)


def _modified_files(patch: str) -> list[str]:
    return [ln[6:] for ln in patch.splitlines() if ln.startswith("+++ b/")]


# --------------------------------------------------------------------------- #
# trajectory metrics
# --------------------------------------------------------------------------- #
def traj_metrics(traj_path: Path) -> dict:
    return traj_metrics_from_dict(_load(traj_path))


def traj_metrics_from_dict(t: dict) -> dict:
    msgs = t["messages"]
    assistant = [m for m in msgs if m.get("role") == "assistant"]
    tool = [m for m in msgs if m.get("role") == "tool"]

    n_cmd = n_test = n_search = n_network = n_github_fetch = 0
    trunc = repeats = 0
    seen: set[str] = set()
    reasoning_chars = 0

    for m in assistant:
        reasoning_chars += len(str(m.get("reasoning_content") or ""))
        for tc in m.get("tool_calls") or []:
            name = tc["function"]["name"]
            if name == "github_fetch":
                n_github_fetch += 1
            if name != "bash":
                continue
            n_cmd += 1
            try:
                cmd = json.loads(tc["function"]["arguments"])["command"]
            except Exception:
                continue
            if cmd in seen:
                repeats += 1
            seen.add(cmd)
            if "pytest" in cmd or "runtests" in cmd:
                n_test += 1
            elif cmd.startswith(("grep", "rg")) or " find " in cmd:
                n_search += 1
            if any(tok in cmd for tok in ("curl", "wget", "urllib", "requests.get")) and (
                "http://" in cmd or "https://" in cmd
            ):
                n_network += 1

    for m in tool:
        if "characters elided" in str(m.get("content")):
            trunc += 1

    return {
        "steps": len(assistant),
        "exit_status": t["info"].get("exit_status"),
        "patch_chars": len(t["info"].get("submission") or ""),
        "files": len(_modified_files(t["info"].get("submission") or "")),
        "n_cmd": n_cmd,
        "n_test_cmd": n_test,
        "n_network_cmd": n_network,
        "n_github_fetch": n_github_fetch,
        "trunc_events": trunc,
        "repeat_cmds": repeats,
        "reasoning_chars": reasoning_chars,
    }


# --------------------------------------------------------------------------- #
# harness metrics
# --------------------------------------------------------------------------- #
@dataclass
class RunSummary:
    name: str
    model: str = ""
    evaluated: int = 0
    resolved: int = 0
    infra_failure: int = 0
    empty_patch: int = 0
    error: int = 0
    resolved_ids: set = field(default_factory=set)
    evaluated_ids: set = field(default_factory=set)
    regressions_total: int = 0
    instances_with_regression: int = 0
    f2p_partial_ids: list = field(default_factory=list)
    retrieved_ids: set = field(default_factory=set)
    steps: list = field(default_factory=list)
    trunc_total: int = 0
    repeats_total: int = 0
    notes: str = ""
    status: str = "unknown"
    variable: str = ""
    ts: float = 0.0
    ts_str: str = "n/a"


def _instance_test_detail(run_id: str, model_dir: str, iid: str) -> dict | None:
    p = EVAL_LOGS / run_id / model_dir / iid / "report.json"
    if not p.is_file():
        return None
    data = next(iter(_load(p).values()))
    ts = data.get("tests_status", {})
    return {
        "resolved": data.get("resolved", False),
        "f2p_pass": len(ts.get("FAIL_TO_PASS", {}).get("success", [])),
        "f2p_fail": len(ts.get("FAIL_TO_PASS", {}).get("failure", [])),
        "p2p_fail": len(ts.get("PASS_TO_PASS", {}).get("failure", [])),
    }


def _split_report_stem(stem: str) -> tuple[str, str]:
    """``<model_dir>.<run_id>`` -> parts. Model dirs may contain dots (glm-5.3),
    so match against the run ids that actually exist in the harness log tree."""
    if EVAL_LOGS.is_dir():
        for candidate in sorted((p.name for p in EVAL_LOGS.iterdir() if p.is_dir()), key=len, reverse=True):
            if stem.endswith(f".{candidate}"):
                return stem[: -len(candidate) - 1], candidate
    head, _, tail = stem.rpartition(".")
    return (head or stem), tail


def summarize_run(run_dir: Path, name: str | None = None) -> RunSummary | None:
    report_dir = run_dir / "report"
    reports = sorted(report_dir.glob("*.json")) if report_dir.is_dir() else []
    if not reports:
        return None

    # Prefer the report covering the most evaluated instances (skip trial subsets).
    best, best_n = None, -1
    for rp in reports:
        data = _load(rp)
        n = data.get("completed_instances", 0)
        if n > best_n:
            best, best_n = (rp, data), n
    rp, data = best
    model_dir, run_id = _split_report_stem(rp.stem)

    s = RunSummary(name=name or run_dir.name)
    s.model = model_dir.replace("__", "/")
    s.resolved = data.get("resolved_instances", 0)
    s.evaluated = data.get("completed_instances", 0)
    s.infra_failure = len(data.get("infra_failure_ids", []))
    s.empty_patch = len(data.get("empty_patch_ids", []))
    s.error = len(data.get("error_ids", []))
    s.resolved_ids = set(data.get("resolved_ids", []))
    s.evaluated_ids = set(data.get("completed_ids", s.resolved_ids | set(data.get("unresolved_ids", []))))

    # per-instance detail from raw harness logs
    for iid in sorted(s.evaluated_ids):
        detail = _instance_test_detail(run_id, model_dir, iid)
        if not detail:
            continue
        if detail["p2p_fail"] > 0:
            s.regressions_total += detail["p2p_fail"]
            s.instances_with_regression += 1
        if 0 < detail["f2p_pass"] and not detail["resolved"]:
            s.f2p_partial_ids.append(iid)

    # 指标来源：优先读 metrics.json（提交入库的轻量文件），否则从轨迹现算并写回。
    metrics_file = run_dir / "metrics.json"
    if metrics_file.is_file():
        saved = _load(metrics_file)
        s.steps = list(saved.get("steps", []))
        s.trunc_total = saved.get("trunc_events", 0)
        s.repeats_total = saved.get("repeat_cmds", 0)
        s.retrieved_ids = set(saved.get("retrieved_ids", []))
    else:
        # trajectory metrics
        for traj in run_dir.glob("*/*.traj.json"):
            m = traj_metrics(traj)
            iid = traj.name.removesuffix(".traj.json")
            if iid in s.evaluated_ids or s.evaluated >= DATASET_SIZE:
                s.steps.append(m["steps"])
            s.trunc_total += m["trunc_events"]
            s.repeats_total += m["repeat_cmds"]
            if m["n_network_cmd"] or m["n_github_fetch"]:
                s.retrieved_ids.add(iid)
        if s.steps or s.trunc_total or s.retrieved_ids:
            started_at, agent_finished_at = _log_span(run_dir)
            payload = {
                "steps": s.steps,
                "trunc_events": s.trunc_total,
                "repeat_cmds": s.repeats_total,
                "retrieved_ids": sorted(s.retrieved_ids),
                "instances_with_traj": len(list(run_dir.glob("*/*.traj.json"))),
                # 时间：agent 起止取日志首尾，判分完成取 harness 报告 mtime
                "started_at": started_at,
                "agent_finished_at": agent_finished_at,
                "evaluated_at": (
                    datetime.fromtimestamp(max(r.stat().st_mtime for r in report_dir.glob("*.json")))
                    .isoformat(timespec="seconds")
                    if (report_dir.is_dir() and any(report_dir.glob("*.json")))
                    else None
                ),
            }
            metrics_file.write_text(json.dumps(payload, ensure_ascii=False, indent=1))

    # 时间：优先取 harness 报告/mets 的 mtime（≈ 该实验完成时间）
    # 顺序：harness 报告 > preds.json > 目录 mtime
    # （metrics.json 每次生成仪表盘都会刷新，不能用于计时）
    candidates = [*report_dir.glob("*.json")]
    if not candidates and (preds := run_dir / "preds.json").is_file():
        candidates = [preds]
    s.ts = max((f.stat().st_mtime for f in candidates), default=run_dir.stat().st_mtime)
    s.ts_str = datetime.fromtimestamp(s.ts).strftime("%m-%d %H:%M")

    notes_path = run_dir / "NOTES.md"
    if notes_path.is_file():
        s.notes = notes_path.stem

    meta_path = run_dir / "run_meta.json"
    if meta_path.is_file():
        meta = _load(meta_path)
        s.status = meta.get("status", "unknown")
        s.variable = meta.get("variable", "")
    return s


# --------------------------------------------------------------------------- #
# output
# --------------------------------------------------------------------------- #

def _log_span(run_dir: Path) -> tuple[str | None, str | None]:
    """从 minisweagent.log 首/尾行取 agent 阶段的起止时间（秒级）。"""
    log = run_dir / "minisweagent.log"
    if not log.is_file():
        return None, None
    lines = [ln for ln in log.read_text(errors="ignore").splitlines() if ln[:4].isdigit()]
    if not lines:
        return None, None
    fmt = "%Y-%m-%d %H:%M:%S"
    first = datetime.strptime(lines[0][:19], fmt).isoformat(timespec="seconds")
    last = datetime.strptime(lines[-1][:19], fmt).isoformat(timespec="seconds")
    return first, last


def _overlap_ratio(a: tuple[float, float], b: tuple[float, float]) -> float:
    """重叠宽度 / 较窄区间宽度。0 = 完全不重叠，1 = 完全包含。"""
    (la, ua), (lb, ub) = a, b
    if min(ua - la, ub - lb) <= 0:
        return float("nan")
    return max(0.0, min(ua, ub) - max(la, lb)) / min(ua - la, ub - lb)


def _overlap_label(r: float) -> str:
    if math.isnan(r):
        return "n/a"
    if r == 0:
        return "不重叠(显著)"
    if r < 0.20:
        return "边缘"
    if r < 0.50:
        return "部分重叠"
    return "明显重叠"


def repo_split(runs: list[RunSummary]):
    """Resolved counts split by repo (django/sphinx)."""
    rows = {}
    for s in runs:
        dj = sum(1 for i in s.resolved_ids if i.startswith("django"))
        sp = sum(1 for i in s.resolved_ids if i.startswith("sphinx"))
        rows[s.name] = (dj, sp)
    return rows


def find_run_dirs(runs_dir: Path) -> list[Path]:
    """Run dirs = any dir containing report/*.json, found recursively (supports runs/probes/models/x)."""
    return sorted({p.parent.parent for p in runs_dir.rglob("report/*.json")})


def main(runs_dir: Path = RUNS_DIR, eval_logs: Path = EVAL_LOGS, out_md: Path = OUT_MD,
         out_csv: Path = OUT_CSV, quiet: bool = False) -> list[RunSummary]:
    global EVAL_LOGS
    EVAL_LOGS = eval_logs
    runs = []
    for d in find_run_dirs(runs_dir):
        if s := summarize_run(d, name=str(d.relative_to(runs_dir))):
            runs.append(s)
    if not runs:
        raise SystemExit("No evaluated runs found under experiments/runs/")

    splits = repo_split(runs)

    # 基线参照：名为 baseline 的 run（否则取评测题数最多的 run）
    baseline = next((s for s in runs if s.name == "baseline"), None) or max(runs, key=lambda s: s.evaluated)
    base_ci = _wilson_ci(baseline.resolved, baseline.evaluated)

    header = [
        "run", "status", "model", "resolved", "rate", "95% CI", "vs baseline", "django", "sphinx",
        "steps med/mean", "regressions", "trunc", "repeats", "retrieved",
        "infra/empty/err",
    ]
    table = []
    for s in sorted(runs, key=lambda x: (x.ts, x.name)):
        lo, hi = _wilson_ci(s.resolved, s.evaluated)
        med = statistics.median(s.steps) if s.steps else float("nan")
        mean = statistics.mean(s.steps) if s.steps else float("nan")
        dj, sp = splits[s.name]
        if s is baseline:
            vs_base = "—（基线）"
        elif s.evaluated_ids != baseline.evaluated_ids:
            # 任务集不同（如 n=2 探针）时，区间不可比
            vs_base = "—（任务集不同）"
        else:
            r = _overlap_ratio((lo, hi), base_ci)
            vs_base = f"{r * 100:.0f}% {_overlap_label(r)}"
        table.append([
            s.name, s.status, s.model, f"{s.resolved}/{s.evaluated}",
            f"{s.resolved / s.evaluated * 100:.0f}%" if s.evaluated else "n/a",
            f"[{lo * 100:.0f}%, {hi * 100:.0f}%]",
            vs_base,
            f"{dj}", f"{sp}",
            f"{med:.0f}/{mean:.0f}",
            f"{s.instances_with_regression}({s.regressions_total})",
            str(s.trunc_total), str(s.repeats_total),
            f"{len(s.retrieved_ids)}", f"{s.infra_failure}/{s.empty_patch}/{s.error}",
        ])

    # markdown
    lines = ["# Verified-mini run dashboard", "", "| " + " | ".join(header) + " |",
             "|" + "---|" * len(header)]
    for row in table:
        lines.append("| " + " | ".join(row) + " |")
    lines += [
        "",
        "## 说明（中文）",
        "",
        "- `vs baseline`：仅当与基线**跑的是同一批题**时计算（不同任务集或 n=2 探针显示「—（任务集不同）」，因为区间不可比）。数值 = 与基线区间的**重叠宽度 ÷ 较窄区间宽度**。`0%` 不重叠（可称显著）；"
        "`<20%` 边缘（再差 1–2 题就分开）；`20–50%` 部分重叠（说不准）；`>50%` 明显重叠（无差异）。",
        "- 该判据**偏保守**：两区间重叠也可能存在真实差异。正式结论应看**差值区间是否跨 0**"
        "（同题配对时用 McNemar 更稳）。",
        "- `95% CI` 为 Wilson 置信区间：n=50 时约 ±13pp；n=2 的探针区间宽达 [34%,100%]，"
        "其重叠比例仅供参考，不能用来宣称提升。",
        "- 回归数 = 新弄坏的 PASS_TO_PASS 旧测试数；检索 = 轨迹中出现网络请求的实例数；"
        "截断 = 观察超 10k 字符被裁剪的次数。",
        "",
    ]
    for s in runs:
        if s.f2p_partial_ids:
            lines.append(f"- **{s.name}**: F2P partially passing but unresolved: "
                         f"{', '.join(sorted(s.f2p_partial_ids))}")
    OUT_MD, OUT_CSV = out_md, out_csv
    OUT_MD.write_text("\n".join(lines) + "\n")

    # csv
    import csv
    with OUT_CSV.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(table)

    if not quiet:
        print("\n".join(lines))
        print(f"\nwrote {OUT_MD.relative_to(ROOT)} and {OUT_CSV.relative_to(ROOT)}")
    return runs


if __name__ == "__main__":
    main()
