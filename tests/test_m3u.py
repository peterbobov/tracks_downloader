"""Tests for the playlist .m3u8 written for Rekordbox import"""

from pathlib import Path

from src.file_manager import write_m3u


def test_writes_extended_m3u_with_absolute_paths_in_order(tmp_path):
    a = tmp_path / 'lib' / 'Vol rise' / 'Technotronic - Pump Up The Jam.flac'
    b = tmp_path / 'Old bangers' / 'Robert Miles - Children.aiff'
    out = tmp_path / 'Old bangers' / 'Old bangers.m3u8'

    write_m3u(out, [(b, 243, 'Robert Miles - Children'), (a, 320, 'Technotronic - Pump Up The Jam')])

    assert out.read_text(encoding='utf-8').splitlines() == [
        '#EXTM3U',
        '#EXTINF:243,Robert Miles - Children',
        str(b.absolute()),
        '#EXTINF:320,Technotronic - Pump Up The Jam',
        str(a.absolute()),
    ]


def test_keeps_non_latin_names(tmp_path):
    track = tmp_path / 'Катя Лель - Мой мармеладный.flac'
    out = tmp_path / 'playlist.m3u8'

    write_m3u(out, [(track, 223, 'Катя Лель - Мой мармеладный')])

    assert 'Катя Лель - Мой мармеладный' in out.read_text(encoding='utf-8')
