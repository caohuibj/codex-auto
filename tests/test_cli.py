from pathlib import Path

from codex_auto.cli import main


def test_validate_entry_point(capsys):
    root = Path(__file__).parents[1]

    exit_code = main(
        [
            "validate",
            "--config",
            str(root / "config/orchestrator.example.yml"),
            "--task",
            str(root / "examples/task.example.yml"),
        ]
    )

    assert exit_code == 0
    assert '"valid": true' in capsys.readouterr().out


def test_init_project_entry_point(tmp_path, capsys):
    root = tmp_path / "consumer"
    root.mkdir()
    (root / ".git").mkdir()

    exit_code = main(
        [
            "init-project",
            "--repo-path",
            str(root),
            "--repository",
            "owner/example",
            "--verification",
            "unit=python -m pytest -q",
        ]
    )

    assert exit_code == 0
    assert '"initialized": true' in capsys.readouterr().out
    assert (root / ".agents/skills/codex-auto/SKILL.md").exists()


def test_init_project_reports_invalid_policy_without_traceback(tmp_path, capsys):
    root = tmp_path / "consumer"
    root.mkdir()
    (root / ".git").mkdir()

    exit_code = main(
        [
            "init-project",
            "--repo-path",
            str(root),
            "--repository",
            "owner/example",
            "--verification",
            "unit=python -m pytest -q",
            "--max-fix-cycles",
            "99",
        ]
    )

    assert exit_code == 2
    error = capsys.readouterr().err
    assert '"initialized": false' in error
    assert "max_fix_cycles" in error
