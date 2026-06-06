"""Tests for Path of Exile 2 process detection."""

from poe2price.gamewatch import cmdline_is_game, is_game_running


def test_matches_steam_proton_cmdline():
    cmd = ("S:\\common\\Path of Exile 2\\PathOfExileSteam.exe --nopatch")
    assert cmdline_is_game(cmd) is True


def test_matches_standalone_client():
    assert cmdline_is_game("/games/poe2/PathOfExile.exe") is True


def test_match_is_case_insensitive():
    assert cmdline_is_game("PATHOFEXILESTEAM.EXE") is True


def test_does_not_match_unrelated_process():
    assert cmdline_is_game("/usr/bin/firefox --new-window") is False
    assert cmdline_is_game("python -m poe2price") is False


def test_is_game_running_returns_bool():
    # We can't control what's running on the test box, but it must be a bool
    # and must never raise while scanning /proc.
    assert isinstance(is_game_running(), bool)
