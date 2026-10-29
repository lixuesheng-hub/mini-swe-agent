"""Tests for submit-gate test-target extraction from the agent's command history.

Fairness constraint (see roadmap/stage2): gate targets may ONLY come from
commands the model itself ran. Never from dataset FAIL_TO_PASS/PASS_TO_PASS.
"""
import pytest

from minisweagent.agents.extra.submit_gate import TestTarget, extract_test_targets


def test_extracts_pytest_node_ids_and_files():
    cmds = [
        'cd /testbed && python -m pytest tests/test_build_linkcheck.py::test_anchors_ignored -q',
        'pytest tests/test_foo.py -x -v',
    ]
    targets = extract_test_targets(cmds)
    assert TestTarget("pytest", "tests/test_build_linkcheck.py::test_anchors_ignored") in targets
    assert TestTarget("pytest", "tests/test_foo.py") in targets


def test_extracts_django_runtests_paths_and_remembers_cwd_prefix():
    cmds = [
        'cd /testbed/tests && python runtests.py auth_tests.test_forms -v1',
        'python tests/runtests.py migrations.test_writer',
    ]
    targets = extract_test_targets(cmds)
    assert TestTarget("runtests", "auth_tests.test_forms", runtests_dir="tests") in targets
    assert TestTarget("runtests", "migrations.test_writer", runtests_dir="tests") in targets


def test_deduplicates_same_target_with_different_flags_and_repeats():
    cmds = [
        'pytest tests/test_a.py::test_x -x -q 2>',
        'pytest tests/test_a.py::test_x -v',
        'pytest tests/test_a.py::test_x',
        'python -m pytest tests/test_a.py::test_x -k "x or y"',
    ]
    targets = extract_test_targets(cmds)
    x = [t for t in targets if "test_x" in t.target]
    assert len(x) == 1


def test_node_level_runs_replace_whole_file_when_both_were_run():
    """Model first runs the whole file (exploration) then specific nodes (verification).
    The gate must re-run only the nodes: re-running the whole network-heavy file can
    take 10+ min and spuriously time out at every submission."""
    cmds = [
        'pytest tests/test_build_linkcheck.py -q',
        'pytest tests/test_build_linkcheck.py::test_auth tests/test_build_linkcheck.py::test_anchors_ignored -q',
    ]
    targets = extract_test_targets(cmds)
    assert TestTarget("pytest", "tests/test_build_linkcheck.py") not in targets
    assert TestTarget("pytest", "tests/test_build_linkcheck.py::test_auth") in targets
    assert TestTarget("pytest", "tests/test_build_linkcheck.py::test_anchors_ignored") in targets


def test_file_only_stays_when_no_nodes_were_run():
    targets = extract_test_targets(['pytest tests/test_build_linkcheck.py -q'])
    assert targets == [TestTarget("pytest", "tests/test_build_linkcheck.py")]


def test_when_file_and_its_nodes_both_seen_nodes_win_other_files_kept():
    cmds = [
        'pytest tests/test_a.py::test_x',
        'pytest tests/test_a.py::test_y',
        'pytest tests/test_a.py',
        'pytest tests/test_b.py::test_z',
    ]
    targets = extract_test_targets(cmds)
    # file a dropped in favour of its nodes (regardless of ordering); b has only a node
    assert TestTarget("pytest", "tests/test_a.py") not in targets
    assert TestTarget("pytest", "tests/test_a.py::test_x") in targets
    assert TestTarget("pytest", "tests/test_a.py::test_y") in targets
    assert TestTarget("pytest", "tests/test_b.py::test_z") in targets


def test_ignores_non_test_commands_and_malformed_input():
    cmds = [
        'grep -rn "genindex" sphinx/builders/html/__init__.py',
        'ls -la',
        'pytest',  # bare pytest with no target
        'git diff -- src/x.py',
        '',
    ]
    assert extract_test_targets(cmds) == []


def test_runtests_multiple_targets_in_one_command_all_kept():
    cmds = ['python tests/runtests.py migrations.test_writer.WriterTests.test_a migrations.test_writer.WriterTests.test_b']
    targets = extract_test_targets(cmds)
    assert TestTarget("runtests", "migrations.test_writer.WriterTests.test_a", runtests_dir="tests") in targets
    assert TestTarget("runtests", "migrations.test_writer.WriterTests.test_b", runtests_dir="tests") in targets


def test_max_targets_caps_feedback_cost():
    cmds = [f'pytest tests/test_{i}.py' for i in range(50)]
    targets = extract_test_targets(cmds, max_targets=10)
    assert len(targets) == 10


def test_target_to_command_django_and_pytest():
    t1 = TestTarget("runtests", "auth_tests.test_forms", runtests_dir="tests")
    assert t1.to_command() == "cd tests && python runtests.py auth_tests.test_forms"
    t2 = TestTarget("pytest", "tests/test_x.py::test_y")
    assert t2.to_command() == "python -m pytest tests/test_x.py::test_y -q"
