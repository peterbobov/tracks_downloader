#!/usr/bin/env python3
"""
Audio Converter Module

Converts downloaded FLAC files to AIFF for CDJ/Rekordbox compatibility:
- Lossless, bit-perfect conversion (source bit depth and sample rate preserved)
- Copies tags and cover art from Vorbis comments into ID3 frames
- Verifies the result before replacing the FLAC
"""

import subprocess
from pathlib import Path

from mutagen.aiff import AIFF
from mutagen.flac import FLAC
from mutagen.id3 import (
    APIC, COMM, TALB, TBPM, TCON, TDRC, TIT2, TKEY, TPE1, TPE2, TPOS, TPUB, TRCK, TSRC
)

from .constants import FileConstants

# Vorbis comment key → ID3 frame class
TAG_MAP = {
    'TITLE': TIT2,
    'ARTIST': TPE1,
    'ALBUM': TALB,
    'ALBUMARTIST': TPE2,
    'GENRE': TCON,
    'DATE': TDRC,
    'TRACKNUMBER': TRCK,
    'DISCNUMBER': TPOS,
    'BPM': TBPM,
    'INITIALKEY': TKEY,
    'KEY': TKEY,
    'ISRC': TSRC,
    'LABEL': TPUB,
    'ORGANIZATION': TPUB,
}

PCM_CODECS = {16: 'pcm_s16be', 24: 'pcm_s24be', 32: 'pcm_s32be'}

# Maximum allowed duration difference between source and output (seconds)
MAX_DURATION_DRIFT = 0.05


class ConversionError(Exception):
    """Raised when a file could not be converted; the source is left untouched"""


def _unique_path(path: Path) -> Path:
    """Return path, or 'name (N).ext' if it already exists"""
    if not path.exists():
        return path
    for i in range(1, FileConstants.MAX_COLLISION_ATTEMPTS):
        candidate = path.with_name(f"{path.stem} ({i}){path.suffix}")
        if not candidate.exists():
            return candidate
    raise ConversionError(f"Too many files named {path.name}")


def _copy_tags(flac: FLAC, aiff_path: Path) -> None:
    """Copy Vorbis comments and pictures from FLAC into the AIFF's ID3 chunk"""
    aiff = AIFF(aiff_path)
    if aiff.tags is None:
        aiff.add_tags()
    tags = aiff.tags

    for vorbis_key, frame_cls in TAG_MAP.items():
        values = flac.get(vorbis_key)
        if values and frame_cls.__name__ not in tags:
            tags.add(frame_cls(encoding=3, text=values))

    comment = flac.get('COMMENT') or flac.get('DESCRIPTION')
    if comment:
        tags.add(COMM(encoding=3, lang='eng', desc='', text=comment))

    for pic in flac.pictures:
        tags.add(APIC(encoding=3, mime=pic.mime, type=pic.type, desc=pic.desc, data=pic.data))

    aiff.save()


def convert_to_aiff(flac_path: Path) -> Path:
    """
    Convert a FLAC file to AIFF next to it, then delete the FLAC.

    Args:
        flac_path: Path to the source FLAC

    Returns:
        Path to the new AIFF file

    Raises:
        ConversionError: If conversion or verification fails (FLAC is kept)
    """
    flac_path = Path(flac_path)
    try:
        flac = FLAC(flac_path)
    except Exception as e:
        raise ConversionError(f"Cannot read FLAC {flac_path.name}: {e}") from e

    codec = PCM_CODECS.get(flac.info.bits_per_sample)
    if codec is None:
        raise ConversionError(f"Unsupported bit depth: {flac.info.bits_per_sample}")

    target = _unique_path(flac_path.with_suffix('.aiff'))
    temp = target.with_name(f".{target.name}.part")

    try:
        result = subprocess.run(
            ['ffmpeg', '-nostdin', '-v', 'error', '-y',
             '-i', str(flac_path),
             '-map', '0:a:0', '-map_metadata', '-1',
             '-c:a', codec, '-f', 'aiff', str(temp)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise ConversionError(f"ffmpeg failed: {result.stderr.strip()}")

        drift = abs(AIFF(temp).info.length - flac.info.length)
        if drift > MAX_DURATION_DRIFT:
            raise ConversionError(f"Duration mismatch after conversion ({drift:.2f}s)")

        _copy_tags(flac, temp)
        temp.rename(target)
    except FileNotFoundError as e:
        raise ConversionError("ffmpeg not found — install it with 'brew install ffmpeg'") from e
    except ConversionError:
        raise
    except Exception as e:
        raise ConversionError(f"Conversion failed for {flac_path.name}: {e}") from e
    finally:
        temp.unlink(missing_ok=True)

    flac_path.unlink()
    return target
