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
