"""Tests for the CLI entry point."""
import subprocess
import sys
import os


def _run(*args, cwd):
    return subprocess.run(
        [sys.executable, "main.py", *args],
        cwd=cwd, capture_output=True, text=True, timeout=10,
    )


def test_cli_help(tmp_path, monkeypatch):
    bot_dir = os.path.join(os.path.dirname(__file__), "..")
    result = _run("--help", cwd=bot_dir)
    assert result.returncode == 0
    assert "rank" in result.stdout
    assert "watch" in result.stdout
    assert "backtest" in result.stdout


def test_cli_watch_requires_mode(tmp_path):
    bot_dir = os.path.join(os.path.dirname(__file__), "..")
    result = _run("watch", cwd=bot_dir)
    assert result.returncode != 0


def test_cli_live_requires_confirmation_env(tmp_path, monkeypatch):
    """--live without CONFIRM_LIVE=yes should refuse to run."""
    bot_dir = os.path.join(os.path.dirname(__file__), "..")
    env = os.environ.copy()
    env.pop("CONFIRM_LIVE", None)
    result = subprocess.run(
        [sys.executable, "main.py", "watch", "--live"],
        cwd=bot_dir, capture_output=True, text=True, timeout=10, env=env,
    )
    assert result.returncode != 0
    assert "CONFIRM_LIVE" in (result.stdout + result.stderr)
