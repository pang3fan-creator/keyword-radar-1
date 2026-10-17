"""The project reads its keys from .env at the repository root."""
import os

from radar import env


def test_load_sets_keys_and_overrides_the_shell(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_TEST_A", "old")
    monkeypatch.delenv("RADAR_TEST_B", raising=False)
    path = tmp_path / ".env"
    path.write_text('RADAR_TEST_A="new"\nRADAR_TEST_B=two\n# comment\n\n', encoding="utf-8")

    assert env.load(path) == 2
    assert os.environ["RADAR_TEST_A"] == "new"
    assert os.environ["RADAR_TEST_B"] == "two"


def test_load_keeps_the_shell_value_when_not_overriding(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_TEST_A", "old")
    path = tmp_path / ".env"
    path.write_text("RADAR_TEST_A=new\n", encoding="utf-8")

    assert env.load(path, override=False) == 0
    assert os.environ["RADAR_TEST_A"] == "old"


def test_load_ignores_comments_blank_lines_and_invalid_lines(tmp_path, monkeypatch):
    monkeypatch.delenv("RADAR_TEST_C", raising=False)
    path = tmp_path / ".env"
    path.write_text("# comment\n\nNOVALUE\nRADAR_TEST_C='three'\n", encoding="utf-8")

    assert env.load(path) == 1
    assert os.environ["RADAR_TEST_C"] == "three"


def test_load_missing_file_is_a_noop(tmp_path):
    assert env.load(tmp_path / "missing.env") == 0
