from authprobe.cli import main


def test_bare_invocation_opens_the_interface(capsys):
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "brute-force by Sugar" in out       # banner tagline
    assert "usage: authprobe" in out           # cheat-sheet
    assert "authprobe --help" in out


def test_help_lists_flags(capsys):
    try:
        main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0
    out = capsys.readouterr().out
    assert "--preset" in out
    assert "--wordlist" in out
