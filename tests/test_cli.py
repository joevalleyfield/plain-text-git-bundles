"""Tests for the ptbundle CLI entrypoint."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from ptbundle import __version__
from ptbundle.cli import main


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert __version__ in captured.out


def test_cli_no_args_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    code = main([])
    assert code == 0
    captured = capsys.readouterr()
    assert "usage: ptbundle" in captured.out
    assert "pack" in captured.out
    assert "unpack" in captured.out


def test_cli_pack_command(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["pack", "main..feature", "-o", "./bundle", "--whitelist-ext", "png,jpg"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Packing main..feature to ./bundle" in captured.out


def test_cli_unpack_command(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["unpack", "./bundle", "--sidechannel", "./quarantine"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Unpacking ./bundle" in captured.out


def test_cli_main_default_argv(capsys: pytest.CaptureFixture[str]) -> None:
    with patch("sys.argv", ["ptbundle"]):
        code = main()
    assert code == 0
    captured = capsys.readouterr()
    assert "usage: ptbundle" in captured.out
