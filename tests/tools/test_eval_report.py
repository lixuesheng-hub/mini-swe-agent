import json
import math
from pathlib import Path

import pytest

import tools.eval_report as er


# --------------------------------------------------------------------------- #
# fixtures: build a minimal but *real* run layout on disk
# --------------------------------------------------------------------------- #
def _traj(steps_commands: list[str], exit_status="Submitted", patch="diff --git a/x b/x\n+++ b/src/x.py\n+y\n"):
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "task"}]
    for cmd in steps_commands:
        msgs.append({
            "role": "assistant",
            "content": "",
            "reasoning_content": "think " * 10,
            "tool_calls": [{"id": f"c{len(msgs)}", "function": {"name": "bash", "arguments": json.dumps({"command": cmd})}}],
        })
        msgs.append({"role": "tool", "content": "<output>ok</output>"})
    msgs.append({"role": "exit", "content": patch})
    return {"info": {"exit_status": exit_status, "submission": patch}, "messages": msgs}


def _make_run(root: Path, name: str, *, model_dir: str, run_id: str,
              resolved: list[str], unresolved: list[str], trajs: dict[str, dict],
              p2p_fail: dict[str, int] | None = None) -> None:
    run = root / "runs" / name
    run.mkdir(parents=True)
    for iid, traj in trajs.items():
        d = run / iid
        d.mkdir()
        (d / f"{iid}.traj.json").write_text(json.dumps(traj))
        (run / "preds.json").write_text("{}")
    report = {
        "completed_instances": len(resolved) + len(unresolved),
        "resolved_instances": len(resolved),
        "resolved_ids": resolved,
        "unresolved_ids": unresolved,
        "completed_ids": resolved + unresolved,
        "infra_failure_ids": [],
        "empty_patch_ids": [],
        "error_ids": [],
    }
    (run / "report").mkdir()
    (run / "report" / f"{model_dir}.{run_id}.json").write_text(json.dumps(report))
    for iid in resolved + unresolved:
        d = root / "logs" / run_id / model_dir / iid
        d.mkdir(parents=True)
        (d / "report.json").write_text(json.dumps({iid: {
            "resolved": iid in resolved,
            "tests_status": {
                "FAIL_TO_PASS": {"success": ["t::ok"], "failure": [] if iid in resolved else ["t::bad"]},
                "PASS_TO_PASS": {"success": [], "failure": ["t::reg"] * (p2p_fail or {}).get(iid, 0)},
            },
        }}))


@pytest.fixture
def workspace(tmp_path):
    _make_run(
        tmp_path, "base", model_dir="openai__m-1.5", run_id="base",
        resolved=["django__django-1", "sphinx-doc__sphinx-2"],
        unresolved=["django__django-3"],
        trajs={
            "django__django-1": _traj(["grep -n x src/a.py", "pytest tests/t.py -q"]),
            "sphinx-doc__sphinx-2": _traj(["curl -sL https://api.github.com/repos/a/b | head", "pytest tests/t.py"]),
            "django__django-3": _traj(["pytest tests/t.py"] * 3, exit_status="Submitted"),
        },
        p2p_fail={"django__django-3": 2},
    )
    return tmp_path


# --------------------------------------------------------------------------- #
# unit tests
# --------------------------------------------------------------------------- #
def test_wilson_ci_bounds_and_width():
    lo, hi = er._wilson_ci(30, 50)
    assert 0.45 < lo < 0.50 and 0.70 < hi < 0.75
    assert all(math.isnan(v) for v in er._wilson_ci(0, 0))
    # identical proportion on a bigger sample must yield a narrower interval
    narrow = er._wilson_ci(300, 500)
    assert (hi - lo) > (narrow[1] - narrow[0])


def test_modified_files_only_counts_new_side():
    patch = "diff --git a/x b/x\n--- a/x\n+++ b/src/x.py\n+y\ndiff --git a/y b/y\n+++ b/src/y.py\n"
    assert er._modified_files(patch) == ["src/x.py", "src/y.py"]


def test_split_report_stem_handles_dotted_model(tmp_path):
    logs = tmp_path / "logs"
    (logs / "myrun").mkdir(parents=True)
    old = er.EVAL_LOGS
    try:
        er.EVAL_LOGS = logs
        assert er._split_report_stem("openai__glm-5.3.myrun") == ("openai__glm-5.3", "myrun")
    finally:
        er.EVAL_LOGS = old


def test_traj_metrics_counts_steps_tests_network_and_repeats():
    m = er.traj_metrics_from_dict(_traj([
        "pytest tests/a.py -q",
        "pytest tests/a.py -q",          # exact repeat
        "curl -sL https://api.github.com/x",
        "grep -n foo src/a.py",
    ]))
    assert m["steps"] == 4
    assert m["n_test_cmd"] == 2
    assert m["n_network_cmd"] == 1
    assert m["repeat_cmds"] == 1
    assert m["n_cmd"] == 4
    assert m["files"] == 1


def test_summarize_run_none_without_report(tmp_path):
    (tmp_path / "run").mkdir()
    assert er.summarize_run(tmp_path / "run") is None


# --------------------------------------------------------------------------- #
# end-to-end
# --------------------------------------------------------------------------- #
def test_dashboard_end_to_end(workspace):
    runs = er.main(
        runs_dir=workspace / "runs", eval_logs=workspace / "logs",
        out_md=workspace / "dash.md", out_csv=workspace / "dash.csv", quiet=True,
    )
    assert len(runs) == 1
    s = runs[0]
    assert (s.resolved, s.evaluated) == (2, 3)
    assert s.model == "openai/m-1.5"
    # one instance introduced PASS_TO_PASS regressions
    assert s.instances_with_regression == 1 and s.regressions_total == 2
    # exactly one instance fetched from the network
    assert s.retrieved_ids == {"sphinx-doc__sphinx-2"}

    md = (workspace / "dash.md").read_text()
    assert "| base |" in md and "2/3" in md and "67%" in md
    header, first = (workspace / "dash.csv").read_text().splitlines()[:2]
    assert header.startswith("run,status,model,resolved")
    cols = first.split(",")
    assert cols[0] == "base" and cols[1] == "unknown" and cols[2] == "openai/m-1.5" and cols[3] == "2/3"


def test_status_comes_from_run_meta(workspace):
    (workspace / "runs" / "base" / "run_meta.json").write_text(
        json.dumps({"status": "confirmed", "variable": "prompt hint"})
    )
    runs = er.main(
        runs_dir=workspace / "runs", eval_logs=workspace / "logs",
        out_md=workspace / "dash.md", out_csv=workspace / "dash.csv", quiet=True,
    )
    assert [(s.name, s.status, s.variable) for s in runs] == [("base", "confirmed", "prompt hint")]
    assert "| base |" in (workspace / "dash.md").read_text() and "| confirmed |" in (workspace / "dash.md").read_text()


# --------------------------------------------------------------------------- #
# overlap vs baseline
# --------------------------------------------------------------------------- #
def test_overlap_ratio_bounds():
    same = (0.2, 0.6)
    assert er._overlap_ratio(same, same) == 1.0          # 完全相同 -> 1
    assert er._overlap_ratio((0.1, 0.2), (0.8, 0.9)) == 0.0  # 不相交 -> 0
    # 基线 30/50 与 42/50 的实测值约 4.5%（区间几乎相接）
    r = er._overlap_ratio(er._wilson_ci(30, 50), er._wilson_ci(42, 50))
    assert 0.03 < r < 0.06
    assert er._overlap_label(r) == "边缘"
    assert er._overlap_label(0.0) == "不重叠(显著)"
    assert er._overlap_label(0.9) == "明显重叠"


def test_same_task_set_compares_and_subset_does_not(tmp_path):
    ids = ["django__django-1", "django__django-2"]
    # 基线 1/2
    _make_run(tmp_path, "baseline", model_dir="openai__m", run_id="base",
              resolved=[ids[0]], unresolved=[ids[1]],
              trajs={i: _traj(["pytest t.py"]) for i in ids})
    # 同任务集，2/2 -> 应给出重叠比例
    _make_run(tmp_path, "same", model_dir="openai__m", run_id="same",
              resolved=ids, unresolved=[],
              trajs={i: _traj(["pytest t.py"]) for i in ids})
    # 子集（只 1 题）-> 应显示任务集不同
    _make_run(tmp_path, "subset", model_dir="openai__m", run_id="subset",
              resolved=[ids[0]], unresolved=[],
              trajs={ids[0]: _traj(["pytest t.py"])})

    runs = er.main(runs_dir=tmp_path / "runs", eval_logs=tmp_path / "logs",
                   out_md=tmp_path / "d.md", out_csv=tmp_path / "d.csv", quiet=True)
    by = {s.name: s for s in runs}
    assert by["baseline"].evaluated_ids == set(ids)

    md = (tmp_path / "d.md").read_text()
    same_row = next(l for l in md.splitlines() if l.startswith("| same |"))
    subset_row = next(l for l in md.splitlines() if l.startswith("| subset |"))
    assert "%" in same_row and "任务集不同" not in same_row
    assert "任务集不同" in subset_row


def test_rows_sorted_by_time_ascending(tmp_path):
    """仪表盘按实验完成时间升序（harness 报告 mtime）。"""
    import os

    ids = ["django__django-1"]
    # 先建的 run 时间更早
    for name, hour in [("late", 20), ("early", 10)]:
        _make_run(tmp_path, name, model_dir="openai__m", run_id=name,
                  resolved=ids, unresolved=[],
                  trajs={ids[0]: _traj(["pytest t.py"])})
        reported = tmp_path / "runs" / name / "report" / f"openai__m.{name}.json"
        ts = 1_700_000_000 + hour * 3600
        os.utime(reported, (ts, ts))

    runs = er.main(runs_dir=tmp_path / "runs", eval_logs=tmp_path / "logs",
                   out_md=tmp_path / "d.md", out_csv=tmp_path / "d.csv", quiet=True)
    assert [s.name for s in runs] == ["early", "late"] or [s.name for s in runs] == ["late", "early"]
    # 表格行顺序 = 时间升序
    lines = [l for l in (tmp_path / "d.md").read_text().splitlines() if l.startswith("| early |") or l.startswith("| late |")]
    assert lines[0].startswith("| early |"), "较早完成的 run 应排在前面"
    assert "| when |" not in (tmp_path / "d.md").read_text()


def test_metrics_records_timestamps(tmp_path):
    """metrics.json 记录 agent 起止（日志首尾）与判分完成（报告 mtime）。"""
    ids = ["django__django-1"]
    _make_run(tmp_path, "run1", model_dir="openai__m", run_id="run1",
              resolved=ids, unresolved=[], trajs={ids[0]: _traj(["pytest t.py"])})
    log = tmp_path / "runs" / "run1" / "minisweagent.log"
    log.write_text(
        "2026-10-22 10:00:00,000 - x - INFO - start\n"
        "2026-10-22 11:30:00,000 - x - INFO - done\n"
    )
    er.main(runs_dir=tmp_path / "runs", eval_logs=tmp_path / "logs",
            out_md=tmp_path / "d.md", out_csv=tmp_path / "d.csv", quiet=True)
    m = json.loads((tmp_path / "runs" / "run1" / "metrics.json").read_text())
    assert m["started_at"] == "2026-10-22T10:00:00"
    assert m["agent_finished_at"] == "2026-10-22T11:30:00"
    assert m["evaluated_at"] is not None
