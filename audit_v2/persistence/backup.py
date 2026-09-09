"""Verified local backups and restores into new directories; never overwrite live data."""
import argparse
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify(backup: Path) -> dict:
    root = backup.resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != 1 or not manifest.get("files"):
        raise ValueError("Unsupported or empty backup manifest")
    for name, digest in manifest["files"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file() or _digest(path) != digest:
            raise ValueError(f"Backup integrity failed: {name}")
        if path.suffix in {".sqlite3", ".db"}:
            with sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True) as db:
                if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError(f"Database integrity failed: {name}")
    return manifest


def create(source: Path, destination: Path) -> dict:
    source, destination = source.resolve(), destination.resolve()
    if not source.is_dir() or destination.is_relative_to(source):
        raise ValueError("Backup destination must be outside the source directory")
    databases = sorted({*source.glob("*.sqlite3"), *source.glob("*.db")})
    if not databases:
        raise ValueError("No local audit databases found")
    destination.mkdir(parents=True, exist_ok=False)
    for path in databases:
        if path.is_symlink():
            raise ValueError("Database symlinks are not supported")
        with (
            sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True) as original,
            sqlite3.connect(destination / path.name) as target,
        ):
            original.backup(target)
    artifacts = source / "artifacts"
    if artifacts.exists():
        if any(p.is_symlink() for p in artifacts.rglob("*")) or artifacts.is_symlink():
            raise ValueError("Artifact symlinks are not supported")
        shutil.copytree(artifacts, destination / "artifacts")
    manifest = {"version": 1, "files": {
        str(path.relative_to(destination).as_posix()): _digest(path)
        for path in sorted(destination.rglob("*")) if path.is_file()
    }}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    verify(destination)
    return manifest


def restore(backup: Path, destination: Path) -> dict:
    manifest = verify(backup)
    backup, destination = backup.resolve(), destination.resolve()
    if destination.is_relative_to(backup):
        raise ValueError("Restore destination must be outside the backup")
    destination.mkdir(parents=True, exist_ok=False)
    for name in manifest["files"]:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup / name, target)
        if _digest(target) != manifest["files"][name]:
            raise ValueError(f"Restore integrity failed: {name}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create", "verify", "restore"])
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path, nargs="?")
    args = parser.parse_args()
    if args.action == "verify":
        result = verify(args.source)
    elif args.destination is None:
        parser.error("A new destination directory is required")
    elif args.action == "create":
        result = create(args.source, args.destination)
    else:
        result = restore(args.source, args.destination)
    print(f"Verified {len(result['files'])} backup files")


if __name__ == "__main__":
    main()
