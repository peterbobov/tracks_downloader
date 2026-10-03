"""Tests for FLAC → AIFF conversion"""

import subprocess
from pathlib import Path

import pytest
from mutagen.aiff import AIFF
from mutagen.flac import FLAC, Picture

from src.catalog import LibraryCatalog
from src.converter import ConversionError, convert_to_aiff

COVER_BYTES = b'\xff\xd8\xff\xe0' + b'fake-jpeg-data' * 10


def make_flac(path: Path, bits: int = 16, seconds: float = 2.0) -> Path:
    """Generate a short tagged FLAC with cover art"""
    sample_fmt = 's16' if bits == 16 else 's32'
    subprocess.run(
        ['ffmpeg', '-nostdin', '-v', 'error', '-y',
         '-f', 'lavfi', '-i', f'sine=frequency=440:duration={seconds}',
         '-ar', '44100', '-sample_fmt', sample_fmt,
         *(['-bits_per_raw_sample', '24'] if bits == 24 else []),
         str(path)],
        check=True,
    )
    flac = FLAC(path)
    flac['TITLE'] = 'Sunglasses at Night'
    flac['ARTIST'] = 'Tiga'
    flac['ALBUM'] = 'Sexor'
    flac['GENRE'] = 'Electro'
    flac['DATE'] = '2001'
    flac['BPM'] = '128'
    flac['INITIALKEY'] = '8A'
    pic = Picture()
    pic.type = 3
    pic.mime = 'image/jpeg'
    pic.data = COVER_BYTES
    flac.add_picture(pic)
    flac.save()
    return path


def test_converts_flac_to_aiff_and_removes_flac(tmp_path):
    flac_path = make_flac(tmp_path / 'Tiga - Sunglasses at Night.flac')
    flac_length = FLAC(flac_path).info.length

    aiff_path = convert_to_aiff(flac_path)

    assert aiff_path == tmp_path / 'Tiga - Sunglasses at Night.aiff'
    assert aiff_path.exists()
    assert not flac_path.exists()
    assert list(tmp_path.iterdir()) == [aiff_path]  # no leftover temp files

    aiff = AIFF(aiff_path)
    assert abs(aiff.info.length - flac_length) < 0.05
    assert aiff.info.bits_per_sample == 16
    assert aiff.info.sample_rate == 44100

    tags = aiff.tags
    assert str(tags['TIT2']) == 'Sunglasses at Night'
    assert str(tags['TPE1']) == 'Tiga'
    assert str(tags['TALB']) == 'Sexor'
    assert str(tags['TCON']) == 'Electro'
    assert str(tags['TDRC']) == '2001'
    assert str(tags['TBPM']) == '128'
    assert str(tags['TKEY']) == '8A'
    apic = tags.getall('APIC')
    assert len(apic) == 1
    assert apic[0].data == COVER_BYTES
    assert apic[0].mime == 'image/jpeg'


def test_preserves_24_bit_depth(tmp_path):
    flac_path = make_flac(tmp_path / 'hi-res.flac', bits=24)
    assert FLAC(flac_path).info.bits_per_sample == 24

    aiff_path = convert_to_aiff(flac_path)

    assert AIFF(aiff_path).info.bits_per_sample == 24


def test_failure_keeps_flac_and_cleans_up(tmp_path):
    bad = tmp_path / 'broken.flac'
    bad.write_bytes(b'not really a flac' * 100)

    with pytest.raises(ConversionError):
        convert_to_aiff(bad)

    assert bad.exists()
    assert list(tmp_path.iterdir()) == [bad]


def test_does_not_overwrite_existing_aiff(tmp_path):
    existing = tmp_path / 'track.aiff'
    existing.write_bytes(b'existing')
    flac_path = make_flac(tmp_path / 'track.flac')

    aiff_path = convert_to_aiff(flac_path)

    assert aiff_path == tmp_path / 'track (1).aiff'
    assert existing.read_bytes() == b'existing'


def test_catalog_reads_aiff_tags(tmp_path):
    aiff_path = convert_to_aiff(make_flac(tmp_path / 'some_bot_name_ABC123.flac'))

    metadata = LibraryCatalog(str(tmp_path / 'catalog.db')).extract_metadata(aiff_path)

    assert metadata['title'] == 'Sunglasses at Night'
    assert metadata['artist'] == 'Tiga'
    assert metadata['album'] == 'Sexor'
