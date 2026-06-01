from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path

KB_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = KB_DIR.parent
SOURCE_MANIFEST_PATH = KB_DIR / "source-snapshots" / "manifest.json"
PACKAGE_ARCHIVE_PATH = KB_DIR / "source-snapshots" / "raw-snapshots.tar.gz"
PACKAGE_MANIFEST_PATH = KB_DIR / "source-snapshots" / "raw-snapshots-package.json"
PACKAGE_SHA256_PATH = KB_DIR / "source-snapshots" / "raw-snapshots.tar.gz.sha256"
RAW_PATH_PREFIX = "knowledge-base/source-snapshots/raw/"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", "utf-8")


def source_manifest_records(source_manifest_path: Path) -> list[dict]:
    manifest = load_json(source_manifest_path)
    records_by_path: dict[str, dict] = {}
    for snapshot in manifest.get("snapshots", []):
        raw_path = snapshot["raw_path"]
        if not raw_path.startswith(RAW_PATH_PREFIX):
            raise ValueError(f"Unexpected raw_path outside package prefix: {raw_path}")
        records_by_path[raw_path] = snapshot
    return [records_by_path[path] for path in sorted(records_by_path)]


def repo_path(raw_path: str) -> Path:
    path = PROJECT_ROOT / raw_path
    if not path.resolve().is_relative_to(PROJECT_ROOT.resolve()):
        raise ValueError(f"Refusing path outside repository: {raw_path}")
    return path


def build_package_manifest(
    *,
    source_manifest_path: Path,
    archive_path: Path,
    records: list[dict],
    files: list[dict],
) -> dict:
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "archive_path": str(archive_path.relative_to(PROJECT_ROOT)),
        "archive_sha256": sha256_file(archive_path),
        "archive_bytes": archive_path.stat().st_size,
        "source_manifest_path": str(source_manifest_path.relative_to(PROJECT_ROOT)),
        "source_manifest_sha256": sha256_file(source_manifest_path),
        "raw_file_count": len(files),
        "raw_total_bytes": sum(file["raw_bytes"] for file in files),
        "snapshot_count": len(records),
        "files": files,
    }


def package_raw_snapshots(args: argparse.Namespace) -> None:
    source_manifest_path = Path(args.source_manifest).resolve()
    archive_path = Path(args.archive).resolve()
    package_manifest_path = Path(args.package_manifest).resolve()
    sha256_path = Path(args.sha256).resolve()

    records = source_manifest_records(source_manifest_path)
    missing_paths = [
        record["raw_path"]
        for record in records
        if not repo_path(record["raw_path"]).exists()
    ]
    if missing_paths:
        examples = "\n".join(f"- {path}" for path in missing_paths[:10])
        raise FileNotFoundError(
            "Cannot package raw snapshots because the local ignored raw cache "
            f"is incomplete. Missing {len(missing_paths)} of {len(records)} "
            f"manifest-referenced files. Re-run `make crawl-party-sources` "
            f"or unpack an existing package first.\n{examples}"
        )

    files: list[dict] = []
    for record in records:
        raw_path = record["raw_path"]
        path = repo_path(raw_path)

        actual_sha256 = sha256_file(path)
        actual_bytes = path.stat().st_size
        if actual_sha256 != record["raw_sha256"]:
            raise ValueError(f"Hash mismatch for {raw_path}")
        if actual_bytes != record["raw_bytes"]:
            raise ValueError(f"Byte-count mismatch for {raw_path}")

        files.append(
            {
                "raw_path": raw_path,
                "raw_sha256": record["raw_sha256"],
                "raw_bytes": record["raw_bytes"],
                "snapshot_id": record["snapshot_id"],
                "source_id": record["source_id"],
                "party_id": record["party_id"],
                "canonical_url": record["canonical_url"],
            }
        )

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=archive_path.parent, prefix=f".{archive_path.name}.", delete=False
    ) as temp_file:
        temp_path = Path(temp_file.name)

    try:
        with temp_path.open("wb") as raw_output:
            with gzip.GzipFile(fileobj=raw_output, mode="wb", mtime=0) as gzip_output:
                with tarfile.open(fileobj=gzip_output, mode="w") as tar:
                    for file in files:
                        raw_path = file["raw_path"]
                        path = repo_path(raw_path)
                        info = tar.gettarinfo(path, arcname=raw_path)
                        info.uid = 0
                        info.gid = 0
                        info.uname = ""
                        info.gname = ""
                        info.mtime = 0
                        info.mode = 0o644
                        with path.open("rb") as input_file:
                            tar.addfile(info, input_file)
        temp_path.replace(archive_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()

    package_manifest = build_package_manifest(
        source_manifest_path=source_manifest_path,
        archive_path=archive_path,
        records=records,
        files=files,
    )
    write_json(package_manifest_path, package_manifest)
    sha256_path.write_text(
        f"{package_manifest['archive_sha256']}  {archive_path.name}\n",
        encoding="utf-8",
    )
    print(
        "Packaged "
        f"{package_manifest['raw_file_count']} raw snapshots into "
        f"{archive_path.relative_to(PROJECT_ROOT)}"
    )


def load_package_manifest(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Missing package manifest: {path}")
    return load_json(path)


def verify_archive_hash(package_manifest: dict, archive_path: Path) -> None:
    actual = sha256_file(archive_path)
    expected = package_manifest["archive_sha256"]
    if actual != expected:
        raise ValueError(f"Archive hash mismatch: expected {expected}, got {actual}")


def assert_safe_member(member: tarfile.TarInfo) -> None:
    name = member.name
    if member.isdir():
        return
    if not member.isfile():
        raise ValueError(f"Refusing non-file archive member: {name}")
    if Path(name).is_absolute() or ".." in Path(name).parts:
        raise ValueError(f"Refusing unsafe archive path: {name}")
    if not name.startswith(RAW_PATH_PREFIX):
        raise ValueError(f"Unexpected archive member outside raw prefix: {name}")


def unpack_raw_snapshots(args: argparse.Namespace) -> None:
    archive_path = Path(args.archive).resolve()
    package_manifest_path = Path(args.package_manifest).resolve()
    package_manifest = load_package_manifest(package_manifest_path)
    verify_archive_hash(package_manifest, archive_path)

    if args.clean:
        shutil.rmtree(KB_DIR / "source-snapshots" / "raw", ignore_errors=True)

    with tarfile.open(archive_path, mode="r:gz") as tar:
        for member in tar.getmembers():
            assert_safe_member(member)
        tar.extractall(PROJECT_ROOT, filter="data")

    verify_raw_snapshots(args)
    print(f"Unpacked {archive_path.relative_to(PROJECT_ROOT)}")


def verify_raw_snapshots(args: argparse.Namespace) -> None:
    archive_path = Path(args.archive).resolve()
    package_manifest_path = Path(args.package_manifest).resolve()
    source_manifest_path = Path(args.source_manifest).resolve()
    package_manifest = load_package_manifest(package_manifest_path)

    if archive_path.exists():
        verify_archive_hash(package_manifest, archive_path)

    source_paths = {
        record["raw_path"] for record in source_manifest_records(source_manifest_path)
    }
    package_paths = {file["raw_path"] for file in package_manifest["files"]}
    if source_paths != package_paths:
        missing = sorted(source_paths - package_paths)
        extra = sorted(package_paths - source_paths)
        raise ValueError(
            "Package manifest does not match source manifest: "
            f"missing={missing[:5]} extra={extra[:5]}"
        )

    missing_files: list[str] = []
    bad_hashes: list[str] = []
    for file in package_manifest["files"]:
        path = repo_path(file["raw_path"])
        if not path.exists():
            missing_files.append(file["raw_path"])
            continue
        if sha256_file(path) != file["raw_sha256"]:
            bad_hashes.append(file["raw_path"])

    if missing_files or bad_hashes:
        raise ValueError(
            "Raw snapshot verification failed: "
            f"missing={missing_files[:5]} bad_hashes={bad_hashes[:5]}"
        )

    print(f"Verified {len(package_manifest['files'])} packaged raw snapshots")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Package raw source snapshots")
    parser.add_argument("--archive", default=str(PACKAGE_ARCHIVE_PATH))
    parser.add_argument("--package-manifest", default=str(PACKAGE_MANIFEST_PATH))
    parser.add_argument("--sha256", default=str(PACKAGE_SHA256_PATH))
    parser.add_argument("--source-manifest", default=str(SOURCE_MANIFEST_PATH))
    subparsers = parser.add_subparsers(dest="command", required=True)

    package_parser = subparsers.add_parser("package")
    package_parser.set_defaults(func=package_raw_snapshots)

    unpack_parser = subparsers.add_parser("unpack")
    unpack_parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove the existing raw snapshot directory before unpacking.",
    )
    unpack_parser.set_defaults(func=unpack_raw_snapshots)

    verify_parser = subparsers.add_parser("verify")
    verify_parser.set_defaults(func=verify_raw_snapshots)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
