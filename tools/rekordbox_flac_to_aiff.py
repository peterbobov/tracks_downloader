# /// script
# requires-python = ">=3.12"
# dependencies = ["pyrekordbox==0.4.4"]
# ///
"""
Convert FLAC tracks in the Rekordbox library to AIFF, keeping everything attached to them.

Rekordbox's own Relocate refuses to switch file types, so this script does what a
relocate does, plus the format change:
  - converts each FLAC to an AIFF next to it and verifies the audio (bit-identical,
    or same sample count when reducing bit depth with --max-bits)
  - rewrites the filename stored in the track's ANLZ analysis files (DAT/EXT/2EX)
  - updates the track's djmdContent row (path, file name, type, bit depth, bitrate,
    size) and bumps Rekordbox's USN counters, exactly like a relocate

The track keeps its ID, so cues, grids, My Tags, ratings, history and playlist
membership are untouched. Work is committed folder by folder, so an interrupted run
keeps every finished folder. FLACs are only ever moved to the macOS Trash (--trash-flac).

Usage (Rekordbox must be closed for --apply):
    uv run tools/rekordbox_flac_to_aiff.py --ids 114074366            # dry run
    uv run tools/rekordbox_flac_to_aiff.py --ids 114074366 --apply
    uv run tools/rekordbox_flac_to_aiff.py --folder "Vol September" --apply
    uv run tools/rekordbox_flac_to_aiff.py --all --max-bits 16 --max-rate 48000 \
        --reconvert --trash-flac --apply
    uv run tools/rekordbox_flac_to_aiff.py --trash-converted          # trash leftover FLACs
    uv run tools/rekordbox_flac_to_aiff.py --rollback <backup dir>
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from pyrekordbox import Rekordbox6Database
from pyrekordbox.utils import get_rekordbox_pid

FILE_TYPE_FLAC = 5
FILE_TYPE_AIFF = 12
ANLZ_EXTS_WITH_PATH = ("DAT", "EXT", "2EX")
PCM_CODECS = {16: "pcm_s16be", 24: "pcm_s24be", 32: "pcm_s32be"}
BACKUP_ROOT = Path.home() / "Library/Pioneer/rekordbox/flac2aiff_backups"


@dataclass
class Job:
    content_id: str
    title: str
    flac: str
    aiff: str
    anlz_dir: str
    est_bytes: int
    redo: bool = False  # rebuild an AIFF this tool made earlier, keeping its file name
    status: str = "pending"
    error: str = ""
    src_bits: int = 0
    out_bits: int = 0
    src_rate: int = 0
    out_rate: int = 0
    channels: int = 0
    staged: str = ""
    anlz_files: list = field(default_factory=list)
    flac_trashed: bool = False


# MARK: - Audio

def probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
         "stream=sample_rate,channels,bits_per_raw_sample,bits_per_sample,duration_ts",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    s = json.loads(out.stdout)["streams"][0]
    bits = int(s.get("bits_per_raw_sample") or 0) or int(s.get("bits_per_sample") or 0)
    return {"sample_rate": int(s["sample_rate"]), "channels": int(s["channels"]),
            "bits": bits, "samples": int(s.get("duration_ts") or 0)}


def audio_md5(path: Path) -> str:
    """MD5 of the decoded audio as 32-bit PCM (lossless for 16/24/32-bit sources)."""
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a", "-c:a", "pcm_s32le",
         "-f", "md5", "-"],
        capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


def target_rate(src_rate: int, max_rate: int) -> int:
    """Highest rate <= max_rate in the source's family (44.1k or 48k), e.g. 88.2k -> 44.1k."""
    if src_rate <= max_rate:
        return src_rate
    base = 44100 if src_rate % 44100 == 0 else 48000
    return base * max(1, max_rate // base) if base <= max_rate else max_rate


def verify(src: Path, dst: Path, out_bits: int, out_rate: int) -> None:
    a, b = probe(src), probe(dst)
    if a["channels"] != b["channels"] or b["sample_rate"] != out_rate:
        raise RuntimeError("sample rate / channels wrong after conversion")
    if b["bits"] != out_bits:
        raise RuntimeError(f"expected {out_bits}-bit output, got {b['bits']}-bit")
    if not a["samples"]:
        raise RuntimeError("could not read source sample count")
    if a["sample_rate"] != out_rate:
        # Resampled: same duration, to within a sample (cues/grids are stored in ms)
        expected = a["samples"] * out_rate / a["sample_rate"]
        if abs(b["samples"] - expected) > 1:
            raise RuntimeError(f"duration differs ({b['samples']} vs ~{expected:.0f} samples)")
    elif a["bits"] != out_bits:
        # Bit depth reduced: audio can't be identical, but the sample count must be
        if a["samples"] != b["samples"]:
            raise RuntimeError(f"sample count differs ({a['samples']} vs {b['samples']})")
    elif audio_md5(src) != audio_md5(dst):
        raise RuntimeError("decoded audio differs after conversion")


def convert(job: Job, max_bits: int, max_rate: int) -> None:
    flac, aiff = Path(job.flac), Path(job.aiff)
    info = probe(flac)
    job.src_bits, job.src_rate, job.channels = info["bits"], info["sample_rate"], info["channels"]
    job.out_bits = min(job.src_bits, max_bits)
    job.out_rate = target_rate(job.src_rate, max_rate)
    codec = PCM_CODECS.get(job.out_bits)
    if codec is None:
        raise RuntimeError(f"unsupported bit depth {job.src_bits}")

    if aiff.exists() and not job.redo:
        # Left over from an earlier run and not in Rekordbox: reuse it if it checks out
        try:
            verify(flac, aiff, job.out_bits, job.out_rate)
            return
        except RuntimeError:
            pass

    resample = []
    if job.out_rate != job.src_rate:
        resample.append(f"osr={job.out_rate}:filter_size=256:phase_shift=10:cutoff=0.97")
    if job.out_bits < job.src_bits:
        resample.append(f"osf=s{job.out_bits}:dither_method=triangular")
    af = ["-af", "aresample=" + ":".join(resample)] if resample else []
    tmp = aiff.with_name(f".{aiff.name}.part")
    tmp.unlink(missing_ok=True)
    try:
        subprocess.run(
            ["ffmpeg", "-v", "error", "-n", "-i", str(flac), "-map", "0:a", "-map", "0:v?",
             *af, "-c:a", codec, "-c:v", "copy", "-map_metadata", "0",
             "-write_id3v2", "1", "-id3v2_version", "3", "-f", "aiff", str(tmp)],
            capture_output=True, text=True, check=True,
        )
        verify(flac, tmp, job.out_bits, job.out_rate)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    if job.redo:
        # The current AIFF is live in Rekordbox: swap it in at commit time
        job.staged = str(tmp)
    else:
        os.replace(tmp, aiff)


def trash(paths: list[str]) -> list[str]:
    """Move files to the macOS Trash (Put Back works). Returns the ones that failed."""
    failed = []
    for p in paths:
        r = subprocess.run(["/usr/bin/trash", p], capture_output=True, text=True)
        if r.returncode != 0:
            failed.append(p)
    return failed


# MARK: - ANLZ path patching

def patch_ppth(data: bytes, new_name: str) -> bytes:
    """Replace the file name in the PPTH tag of an ANLZ file, keeping its directory prefix.

    Layout: PMAI header (fourcc, header_len, file_len), then tags of
    (fourcc, header_len, tag_len, ...). PPTH adds path_len + UTF-16BE NUL-terminated path.
    """
    if data[:4] != b"PMAI":
        raise ValueError("not an ANLZ file")
    pos = int.from_bytes(data[4:8], "big")
    while pos < len(data):
        fourcc = data[pos:pos + 4]
        tag_len = int.from_bytes(data[pos + 8:pos + 12], "big")
        if fourcc == b"PPTH":
            path_len = int.from_bytes(data[pos + 12:pos + 16], "big")
            old_path = data[pos + 16:pos + 16 + path_len].decode("utf-16-be").rstrip("\0")
            prefix = old_path.rsplit("/", 1)[0] + "/" if "/" in old_path else ""
            new_path = (prefix + new_name + "\0").encode("utf-16-be")
            new_tag = (
                b"PPTH" + data[pos + 4:pos + 8]
                + (16 + len(new_path)).to_bytes(4, "big")
                + len(new_path).to_bytes(4, "big") + new_path
            )
            out = data[:pos] + new_tag + data[pos + tag_len:]
            return out[:8] + len(out).to_bytes(4, "big") + out[12:]
        pos += tag_len
    raise ValueError("no PPTH tag")


# MARK: - Selection

def anlz_dir(db: Rekordbox6Database, t) -> str:
    """The track's ANLZ folder, or "" for tracks Rekordbox never analysed (no files to
    patch; pyrekordbox would otherwise return the whole share directory)."""
    return str(db.get_anlz_dir(t)) if (t.AnalysisDataPath or "").strip() else ""


def estimate_bytes(t, args) -> int:
    bits = min(t.BitDepth or 16, args.max_bits)
    rate = target_rate(t.SampleRate or 44100, args.max_rate)
    return (t.Length or 0) * rate * (bits // 8) * 2


def select_redo_jobs(db: Rekordbox6Database, args, in_scope: set[str]) -> list[Job]:
    """AIFFs made by earlier runs that exceed the current --max-bits/--max-rate and
    whose FLAC is still on disk (so they can be rebuilt from the original)."""
    jobs, seen = [], set()
    for manifest in sorted(BACKUP_ROOT.glob("*/manifest.json")):
        for m in json.loads(manifest.read_text())["tracks"]:
            cid = m.get("content_id") or m.get("id")  # early manifests used "id"
            if m["status"] != "done" or cid in seen or cid not in in_scope:
                continue
            t = db.get_content(ID=cid)
            if t is None or t.FileType != FILE_TYPE_AIFF or t.FolderPath != m["aiff"]:
                continue
            too_big = (t.BitDepth or 0) > args.max_bits or (t.SampleRate or 0) > args.max_rate
            if args.folder and args.folder not in t.FolderPath:
                continue
            if too_big and Path(m["flac"]).exists():
                seen.add(cid)
                jobs.append(Job(cid, t.Title or "", m["flac"], m["aiff"],
                                anlz_dir(db, t), estimate_bytes(t, args), redo=True))
    return jobs


def select_jobs(db: Rekordbox6Database, args) -> tuple[list[Job], list[str]]:
    jobs, skipped = [], []
    tracks = db.get_content().all()
    known_paths = {c.FolderPath for c in tracks}
    if args.ids:
        wanted = set(args.ids)
        tracks = [t for t in tracks if t.ID in wanted]
    for t in tracks:
        path = t.FolderPath or ""
        if t.FileType != FILE_TYPE_FLAC or not path.lower().endswith(".flac"):
            continue
        if args.folder and args.folder not in path:
            continue
        flac = Path(path)
        aiff = flac.with_suffix(".aiff")
        label = f"{t.ID} {t.Title}"
        if not flac.exists():
            skipped.append(f"{label}: FLAC missing on disk ({flac})")
            continue
        if str(aiff) in known_paths:
            skipped.append(f"{label}: {aiff.name} is already a separate track in Rekordbox")
            continue
        jobs.append(Job(t.ID, t.Title or "", str(flac), str(aiff), anlz_dir(db, t),
                        estimate_bytes(t, args)))
    if args.reconvert:
        jobs += select_redo_jobs(db, args, {t.ID for t in tracks})
    jobs.sort(key=lambda j: j.flac)
    if args.limit:
        jobs = jobs[:args.limit]
    return jobs, skipped


# MARK: - Apply

def backup_db(db_dir: Path, dest: Path) -> None:
    # pyrekordbox's commit also syncs timestamps into masterPlaylists6.xml
    for name in ("master.db", "master.db-wal", "master.db-shm", "masterPlaylists6.xml"):
        src = db_dir / name
        if src.exists():
            shutil.copy2(src, dest / name)


def write_manifest(backup_dir: Path, share_dir: Path, jobs: list[Job]) -> None:
    (backup_dir / "manifest.json").write_text(json.dumps(
        {"share_dir": str(share_dir), "tracks": [asdict(j) for j in jobs]},
        indent=2, ensure_ascii=False,
    ))


def commit_folder(db: Rekordbox6Database, ready: list[Job], backup_dir: Path,
                  share_dir: Path) -> None:
    """Patch ANLZ files and update DB rows for one folder; undo ANLZ if the commit fails."""
    analysed = [j for j in ready if j.anlz_dir]
    for job in analysed:
        rel = Path(job.anlz_dir).relative_to(share_dir)
        shutil.copytree(job.anlz_dir, backup_dir / "share" / rel, dirs_exist_ok=True)

    patched: list[tuple[Path, Path]] = []
    try:
        for job in analysed:
            if job.redo:
                continue  # same file name, ANLZ paths already right
            for ext in ANLZ_EXTS_WITH_PATH:
                f = Path(job.anlz_dir) / f"ANLZ0000.{ext}"
                if f.exists():
                    tmp = f.with_name(f.name + ".tmp")
                    tmp.write_bytes(patch_ppth(f.read_bytes(), Path(job.aiff).name))
                    patched.append((tmp, f))
                    job.anlz_files.append(str(f))
        for tmp, f in patched:
            os.replace(tmp, f)

        for job in ready:
            if job.staged:
                os.replace(job.staged, job.aiff)
                job.staged = ""
            c = db.get_content(ID=job.content_id)
            c.FolderPath = job.aiff
            c.FileNameL = Path(job.aiff).name
            c.FileType = FILE_TYPE_AIFF
            c.BitDepth = job.out_bits
            c.SampleRate = job.out_rate
            c.BitRate = job.out_rate * job.out_bits * job.channels // 1000
            c.FileSize = Path(job.aiff).stat().st_size
        db.commit()
    except Exception:
        db.rollback()
        for tmp, _ in patched:
            tmp.unlink(missing_ok=True)
        for job in analysed:
            rel = Path(job.anlz_dir).relative_to(share_dir)
            shutil.copytree(backup_dir / "share" / rel, job.anlz_dir, dirs_exist_ok=True)
            job.anlz_files = []
        raise
    for job in ready:
        job.status = "done"


def apply(db: Rekordbox6Database, jobs: list[Job], args) -> Path:
    db_dir = Path(db.db_directory)
    share_dir = Path(db.share_directory)
    backup_dir = BACKUP_ROOT / datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir.mkdir(parents=True)
    backup_db(db_dir, backup_dir)
    print(f"\nBackup: {backup_dir}")

    folders: dict[str, list[Job]] = defaultdict(list)
    for j in jobs:
        folders[str(Path(j.flac).parent)].append(j)

    for n, (folder, fjobs) in enumerate(folders.items(), 1):
        free = shutil.disk_usage(folder).free
        need = sum(j.est_bytes for j in fjobs)
        if free - need < args.min_free_gb * 1e9:
            print(f"\nStopping: {free / 1e9:.1f} GB free, '{Path(folder).name}' needs "
                  f"~{need / 1e9:.1f} GB and the floor is {args.min_free_gb} GB.")
            print("Empty the Trash (or free space), then re-run the same command to continue.")
            break
        if get_rekordbox_pid():
            print("\nStopping: Rekordbox was opened. Close it and re-run to continue.")
            break

        print(f"\n[{n}/{len(folders)}] {folder} — {len(fjobs)} track(s)")

        def run(job: Job) -> Job:
            try:
                convert(job, args.max_bits, args.max_rate)
                job.status = "converted"
            except Exception as e:
                job.status, job.error = "failed", str(e)
                if job.staged:
                    Path(job.staged).unlink(missing_ok=True)
                    job.staged = ""
                print(f"  FAILED {Path(job.flac).name} — {e}")
            return job

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            list(pool.map(run, fjobs))
        ready = [j for j in fjobs if j.status == "converted"]
        if ready:
            try:
                commit_folder(db, ready, backup_dir, share_dir)
            except Exception as e:
                for j in ready:
                    j.status, j.error = "failed", f"commit: {e}"
                print(f"  Commit failed, folder left unchanged: {e}")
            done = [j for j in ready if j.status == "done"]
            if args.trash_flac and done:
                failed = set(trash([j.flac for j in done]))
                for j in done:
                    j.flac_trashed = j.flac not in failed
                if failed:
                    print(f"  Could not trash {len(failed)} FLAC(s); they stay in place.")
            print(f"  {len(done)} done, {len(fjobs) - len(done)} failed"
                  + (", FLACs moved to Trash" if args.trash_flac and done else ""))
        write_manifest(backup_dir, share_dir, jobs)

    write_manifest(backup_dir, share_dir, jobs)
    return backup_dir


# MARK: - Cleanup & rollback

def trash_converted(db: Rekordbox6Database) -> None:
    """Trash FLACs from earlier runs whose track now points at the AIFF in Rekordbox."""
    current = {c.ID: c.FolderPath for c in db.get_content().all()}
    to_trash = []
    for manifest in sorted(BACKUP_ROOT.glob("*/manifest.json")):
        for t in json.loads(manifest.read_text())["tracks"]:
            cid = t.get("content_id") or t.get("id")  # early manifests used "id"
            if t["status"] == "done" and current.get(cid) == t["aiff"] \
                    and Path(t["flac"]).exists() and Path(t["aiff"]).exists():
                to_trash.append(t["flac"])
    # The relocate test left an orphan FLAC that no manifest knows about
    for p in Path.home().glob("Music/**/*-rl.flac"):
        if str(p.with_suffix(".aiff")) in current.values():
            to_trash.append(str(p))
    to_trash = sorted(set(to_trash))
    for p in to_trash:
        print(f"  {p}")
    failed = trash(to_trash)
    print(f"Moved {len(to_trash) - len(failed)} FLAC(s) to the Trash"
          + (f", {len(failed)} failed" if failed else "") + ".")


def resync_anlz_paths(tracks: list[dict]) -> None:
    """Make each track's ANLZ PPTH name match its (restored) DB file name, so a rollback
    is consistent even if an ANLZ backup was taken after the file had been patched."""
    db = Rekordbox6Database()
    fixed = 0
    for t in tracks:
        c = db.get_content(ID=t.get("content_id") or t.get("id"))
        if c is None or not (c.AnalysisDataPath or "").strip():
            continue
        name = Path(c.FolderPath).name
        for ext in ANLZ_EXTS_WITH_PATH:
            f = Path(db.get_anlz_dir(c)) / f"ANLZ0000.{ext}"
            if f.exists():
                data = f.read_bytes()
                new = patch_ppth(data, name)
                if new != data:
                    f.write_bytes(new)
                    fixed += 1
    db.close()
    if fixed:
        print(f"Re-synced the file name in {fixed} ANLZ file(s).")


def rollback(backup_dir: Path) -> None:
    if get_rekordbox_pid():
        sys.exit("Rekordbox is running. Close it first.")
    manifest = json.loads((backup_dir / "manifest.json").read_text())
    share_dir = Path(manifest["share_dir"])
    db_dir = share_dir.parent
    for suffix in ("-wal", "-shm"):
        (db_dir / f"master.db{suffix}").unlink(missing_ok=True)
    for f in [*backup_dir.glob("master.db*"), *backup_dir.glob("masterPlaylists6.xml")]:
        shutil.copy2(f, db_dir / f.name)
    if (backup_dir / "share").exists():
        shutil.copytree(backup_dir / "share", share_dir, dirs_exist_ok=True)
    resync_anlz_paths(manifest["tracks"])
    print(f"Restored master.db, masterPlaylists6.xml and ANLZ files from {backup_dir}.")
    trashed = [t["flac"] for t in manifest["tracks"] if t.get("flac_trashed")]
    if trashed:
        print(f"{len(trashed)} FLAC(s) were moved to the Trash — use Finder's 'Put Back' "
              "on them before opening Rekordbox.")
    print("AIFF files were left in place.")


# MARK: - CLI

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ids", nargs="+", help="Rekordbox content IDs to convert")
    p.add_argument("--folder", help="Only tracks whose path contains this text")
    p.add_argument("--limit", type=int, help="Convert at most N tracks")
    p.add_argument("--all", action="store_true", help="Convert every FLAC track")
    p.add_argument("--apply", action="store_true", help="Actually convert (default: dry run)")
    p.add_argument("--max-bits", type=int, default=24, choices=(16, 24),
                   help="Reduce higher bit depths to this, with dither (default: 24 = keep)")
    p.add_argument("--max-rate", type=int, default=192000,
                   help="Resample higher rates down within their family, e.g. 48000 turns "
                        "88.2k into 44.1k and 96k into 48k (default: keep)")
    p.add_argument("--reconvert", action="store_true",
                   help="Also rebuild AIFFs from earlier runs that exceed --max-bits/--max-rate "
                        "(needs their FLAC still on disk)")
    p.add_argument("--trash-flac", action="store_true",
                   help="Move each FLAC to the Trash once its folder is committed")
    p.add_argument("--min-free-gb", type=float, default=8,
                   help="Stop before a folder would leave less free space than this")
    p.add_argument("--workers", type=int, default=4, help="Parallel ffmpeg conversions")
    p.add_argument("--trash-converted", action="store_true",
                   help="Trash FLACs left over from earlier runs, then exit")
    p.add_argument("--rollback", type=Path, help="Restore DB + ANLZ from a backup dir")
    args = p.parse_args()

    if args.rollback:
        rollback(args.rollback)
        return
    if args.trash_converted:
        trash_converted(Rekordbox6Database())
        return
    if not (args.ids or args.folder or args.limit or args.all):
        p.error("choose tracks with --ids, --folder, --limit or --all")
    if args.apply and get_rekordbox_pid():
        sys.exit("Rekordbox is running. Close it before --apply.")

    db = Rekordbox6Database()
    jobs, skipped = select_jobs(db, args)
    folders = len({Path(j.flac).parent for j in jobs})
    est = sum(j.est_bytes for j in jobs)
    print(f"{len(jobs)} FLAC track(s) in {folders} folder(s) selected, {len(skipped)} skipped. "
          f"AIFF output ~{est / 1e9:.1f} GB.")
    if args.ids or len(jobs) <= 20:
        for j in jobs:
            print(f"  {j.content_id}  {j.flac}  ->  {Path(j.aiff).name}")
    if skipped:
        print(f"  ({len(skipped)} skipped, e.g. {skipped[0]})")

    if not args.apply:
        print("\nDry run — nothing changed. Add --apply to convert.")
        return

    backup_dir = apply(db, jobs, args)
    done = sum(j.status == "done" for j in jobs)
    failed = [j for j in jobs if j.status == "failed"]
    pending = sum(j.status == "pending" for j in jobs)
    print(f"\nFinished: {done} converted, {len(failed)} failed, {pending} not started.")
    for j in failed:
        print(f"  failed: {j.flac} — {j.error}")
    print(f"Undo with: uv run tools/rekordbox_flac_to_aiff.py --rollback '{backup_dir}'")


if __name__ == "__main__":
    main()
