"""Tests for library matching: normalization, fuzzy scoring, catalog dedup"""

import hashlib
import sqlite3

import pytest

from src.catalog import LibraryCatalog, match_score, SIMILARITY_THRESHOLD
from src.utils import normalize_for_match


# MARK: - Normalization

@pytest.mark.parametrize('a, b', [
    ('Ultra Naté', 'Ultra Nate'),
    ('Benny Benassi, The Biz', 'Benny Benassi & The Biz'),
    ('Benny Benassi, The Biz', 'Benny Benassi; The Biz'),
    ("Can't Get You out of My Head", 'Cant Get You Out Of My Head'),
    ('  Pump Up  The Jam ', 'pump up the jam'),
])
def test_normalize_equivalent(a, b):
    assert normalize_for_match(a) == normalize_for_match(b)


def test_normalize_keeps_cyrillic():
    assert normalize_for_match('Катя Лель') == normalize_for_match('катя лель')
    assert normalize_for_match('Катя Лель').strip() != ''


def test_track_id_ignores_accents_and_punctuation():
    assert (LibraryCatalog.generate_track_id('Free', 'Ultra Naté')
            == LibraryCatalog.generate_track_id('Free', 'Ultra Nate'))


# MARK: - Fuzzy scoring

@pytest.mark.parametrize('spotify, library', [
    # Extra subtitle on the library copy
    (('Мой мармеладный', 'Катя Лель'), ('Мой мармеладный (Я не права)', 'Катя Лель')),
    # Featured artist in title on one side only
    (('Low (feat. T-Pain)', 'Flo Rida, T-Pain'), ('Low', 'Flo Rida')),
    # Unbracketed feat with a hyphenated artist
    (('Low feat. T-Pain', 'Flo Rida'), ('Low', 'Flo Rida')),
    # "Original Mix" is the default version
    (('Pump Up The Jam - Original Mix', 'Technotronic'), ('Pump Up The Jam', 'Technotronic')),
    # Remaster is the same recording for DJ purposes
    (('Children - Remastered 2021', 'Robert Miles'), ('Children', 'Robert Miles')),
])
def test_similar_tracks_match(spotify, library):
    assert match_score(*spotify, *library) >= SIMILARITY_THRESHOLD


@pytest.mark.parametrize('spotify, library', [
    # Original vs remix
    (('Galvanize', 'The Chemical Brothers, Q-Tip'),
     ('Galvanize (Chris Lake Remix)', 'The Chemical Brothers, Q-Tip')),
    # Extended vs radio version
    (('Satisfaction - Isak Original Extended', 'Benny Benassi, The Biz'),
     ('Satisfaction', 'Benny Benassi, The Biz')),
    # Different remixers
    (('Heads Will Roll - A-Trak Remix', 'Yeah Yeah Yeahs, A-Trak'),
     ('Heads Will Roll - Chris Lake Remix', 'Yeah Yeah Yeahs')),
    # Cover by a different artist
    (("Can't Get You out of My Head", 'Kylie Minogue'),
     ("Can't Get You out of My Head", 'Goldaine, Tropical Tide')),
    # Same artist, different song
    (('Lady - Hear Me Tonight', 'Modjo'), ('Chillin', 'Modjo')),
])
def test_different_tracks_do_not_match(spotify, library):
    assert match_score(*spotify, *library) < SIMILARITY_THRESHOLD


# MARK: - Catalog behaviour

def meta(title, artist):
    return {'title': title, 'artist': artist, 'album': None,
            'duration_seconds': None, 'file_format': None, 'extra_metadata': {}}


@pytest.fixture
def catalog(tmp_path):
    return LibraryCatalog(str(tmp_path / 'catalog.db'))


def make_file(tmp_path, name):
    path = tmp_path / name
    path.write_bytes(b'x' * 2048)
    return path


def test_find_track_matches_accent_variant(catalog, tmp_path):
    catalog.add_track(make_file(tmp_path, 'free.flac'), metadata_override=meta('Free', 'Ultra Nate'))

    assert catalog.find_track('Free', 'Ultra Naté') is not None


def test_rescan_preserves_spotify_id(catalog, tmp_path):
    path = make_file(tmp_path, 'jam.flac')
    catalog.add_track(path, spotify_id='sp123', metadata_override=meta('Pump Up The Jam', 'Technotronic'))

    # Rescan (as `run.py catalog` does) without a spotify_id
    catalog.add_track(path, metadata_override=meta('Pump Up The Jam', 'Technotronic'))

    assert catalog.find_track_by_spotify_id('sp123') is not None


def test_backfill_by_found_track_id(catalog, tmp_path):
    catalog.add_track(make_file(tmp_path, 'jam.flac'), metadata_override=meta('Pump Up The Jam', 'Technotronic'))

    found = catalog.find_track('Pump Up The Jam', 'Technotronic')
    assert catalog.backfill_spotify_id(found.id, 'sp999')
    assert catalog.find_track_by_spotify_id('sp999') is not None


def test_find_similar_returns_best_existing_match(catalog, tmp_path):
    catalog.add_track(make_file(tmp_path, 'a.flac'),
                      metadata_override=meta('Мой мармеладный (Я не права)', 'Катя Лель'))
    catalog.add_track(make_file(tmp_path, 'b.flac'), metadata_override=meta('Galvanize (Chris Lake Remix)', 'The Chemical Brothers'))

    hit = catalog.find_similar('Мой мармеладный', 'Катя Лель')
    assert hit is not None
    assert hit[0].title == 'Мой мармеладный (Я не права)'

    assert catalog.find_similar('Galvanize', 'The Chemical Brothers, Q-Tip') is None


def old_track_id(title, artist):
    return hashlib.md5(f"{artist.lower().strip()}:{title.lower().strip()}".encode()).hexdigest()


def test_migration_rehashes_ids_and_resolves_collisions(tmp_path):
    db = tmp_path / 'catalog.db'
    LibraryCatalog(str(db))  # create schema
    with sqlite3.connect(db) as conn:
        conn.execute('PRAGMA user_version = 0')
        rows = [
            (old_track_id('Free', 'Ultra Naté'), None, 'Free', 'Ultra Naté', make_file(tmp_path, '1.flac')),
            # Collides with the row above once accents are stripped; has spotify_id so it wins
            (old_track_id('Free', 'Ultra Nate'), 'sp1', 'Free', 'Ultra Nate', make_file(tmp_path, '2.flac')),
            (old_track_id('Children', 'Robert Miles'), None, 'Children', 'Robert Miles', make_file(tmp_path, '3.flac')),
        ]
        for track_id, sid, title, artist, path in rows:
            conn.execute(
                'INSERT INTO tracks (id, spotify_id, title, artist, file_path, date_added, file_size) '
                'VALUES (?, ?, ?, ?, ?, ?, ?)',
                (track_id, sid, title, artist, str(path), '2026-01-01', 2048))

    catalog = LibraryCatalog(str(db))

    hit = catalog.find_track('Free', 'Ultra Naté')
    assert hit is not None and hit.spotify_id == 'sp1'
    assert catalog.find_track('Children', 'Robert Miles') is not None
    with sqlite3.connect(db) as conn:
        assert conn.execute('SELECT COUNT(*) FROM tracks').fetchone()[0] == 2
        assert conn.execute('PRAGMA user_version').fetchone()[0] >= 2


def test_find_track_ignores_deleted_files(catalog, tmp_path):
    path = make_file(tmp_path, 'gone.flac')
    catalog.add_track(path, metadata_override=meta('Children', 'Robert Miles'))
    path.unlink()

    assert catalog.find_track('Children', 'Robert Miles') is None


# MARK: - Duplicate copies

@pytest.mark.parametrize('first, second', [('copy.mp3', 'copy.flac'), ('copy.flac', 'copy.mp3')])
def test_lossless_copy_wins_regardless_of_scan_order(catalog, tmp_path, first, second):
    for name in (first, second):
        catalog.add_track(make_file(tmp_path, name), metadata_override=meta('Low', 'Flo Rida'))

    assert catalog.find_track('Low', 'Flo Rida').file_path.endswith('copy.flac')


def test_lossy_copy_replaces_missing_lossless_file(catalog, tmp_path):
    flac = make_file(tmp_path, 'copy.flac')
    catalog.add_track(flac, metadata_override=meta('Low', 'Flo Rida'))
    flac.unlink()

    catalog.add_track(make_file(tmp_path, 'copy.mp3'), metadata_override=meta('Low', 'Flo Rida'))

    assert catalog.find_track('Low', 'Flo Rida').file_path.endswith('copy.mp3')


@pytest.mark.parametrize('a, b', [
    ('Kasper Bjørke', 'Kasper Bjorke'),
    ('Røyksopp', 'Royksopp'),
    ('Ætherial', 'Aetherial'),
    ('Straße', 'Strasse'),
    ('Łukasz', 'Lukasz'),
])
def test_normalize_transliterates_special_latin_letters(a, b):
    assert normalize_for_match(a) == normalize_for_match(b)


def test_migration_rehashes_special_latin_letters(tmp_path):
    db = tmp_path / 'catalog.db'
    LibraryCatalog(str(db))
    with sqlite3.connect(db) as conn:
        conn.execute('PRAGMA user_version = 2')  # IDs from before ø → o transliteration
        conn.execute(
            'INSERT INTO tracks (id, spotify_id, title, artist, file_path, date_added, file_size) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (old_track_id('Heaven', 'Kasper Bjørke'), 'sp9', 'Heaven', 'Kasper Bjørke',
             str(make_file(tmp_path, 'h.flac')), '2026-01-01', 2048))

    catalog = LibraryCatalog(str(db))

    assert catalog.find_track('Heaven', 'Kasper Bjorke').spotify_id == 'sp9'


def test_migration_prefers_existing_file_and_keeps_spotify_id(tmp_path):
    db = tmp_path / 'catalog.db'
    LibraryCatalog(str(db))
    aiff = make_file(tmp_path, 'h.aiff')
    with sqlite3.connect(db) as conn:
        conn.execute('PRAGMA user_version = 2')
        insert = ('INSERT INTO tracks (id, spotify_id, title, artist, file_path, date_added, file_size) '
                  'VALUES (?, ?, ?, ?, ?, ?, ?)')
        # Stale FLAC entry (converted away) holding the spotify_id, under the old hash
        conn.execute(insert, (old_track_id('Heaven', 'Kasper Bjørke'), 'sp9', 'Heaven', 'Kasper Bjørke',
                              str(tmp_path / 'h.flac'), '2026-01-01', 2048))
        # Rescanned AIFF entry without spotify_id
        conn.execute(insert, ('other-id', None, 'Heaven', 'Kasper Bjorke', str(aiff), '2026-01-02', 2048))

    catalog = LibraryCatalog(str(db))

    hit = catalog.find_track('Heaven', 'Kasper Bjørke')
    assert hit.file_path == str(aiff)
    assert hit.spotify_id == 'sp9'
