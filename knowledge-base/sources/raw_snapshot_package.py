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
PACKAGE_SOURCE_FIELDS = (
    "raw_sha256",
    "raw_bytes",
    "snapshot_id",
    "source_id",
    "party_id",
    "canonical_url",
)


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


def verify_sha256_sidecar(sha256_path: Path, archive_path: Path) -> None:
    if not sha256_path.exists():
        raise FileNotFoundError(f"Missing archive sha256 sidecar: {sha256_path}")

    content = sha256_path.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError(f"Archive sha256 sidecar is empty: {sha256_path}")

    expected_hash = sha256_file(archive_path)
    parts = content.split()
    actual_hash = parts[0]
    actual_filename = parts[1] if len(parts) > 1 else archive_path.name
    if actual_hash != expected_hash:
        raise ValueError(
            f"Archive sidecar hash mismatch: expected {expected_hash}, got {actual_hash}"
        )
    if actual_filename != archive_path.name:
        raise ValueError(
            "Archive sidecar filename mismatch: "
            f"expected {archive_path.name}, got {actual_filename}"
        )


def verify_package_matches_source_manifest(
    package_manifest: dict, source_manifest_path: Path
) -> None:
    actual_manifest_hash = sha256_file(source_manifest_path)
    expected_manifest_hash = package_manifest.get("source_manifest_sha256")
    if actual_manifest_hash != expected_manifest_hash:
        raise ValueError(
            "Package source manifest hash mismatch: "
            f"expected {expected_manifest_hash}, got {actual_manifest_hash}"
        )

    source_records = source_manifest_records(source_manifest_path)
    source_by_path = {record["raw_path"]: record for record in source_records}
    package_files = package_manifest.get("files", [])
    package_paths = [file["raw_path"] for file in package_files]
    duplicate_package_paths = sorted(
        {path for path in package_paths if package_paths.count(path) > 1}
    )
    if duplicate_package_paths:
        raise ValueError(
            "Package manifest contains duplicate raw paths: "
            f"{duplicate_package_paths[:5]}"
        )

    package_by_path = {file["raw_path"]: file for file in package_files}
    source_paths = set(source_by_path)
    package_paths_set = set(package_by_path)
    if source_paths != package_paths_set:
        missing = sorted(source_paths - package_paths_set)
        extra = sorted(package_paths_set - source_paths)
        raise ValueError(
            "Package manifest does not match source manifest: "
            f"missing={missing[:5]} extra={extra[:5]}"
        )

    mismatches: list[str] = []
    for raw_path in sorted(source_by_path):
        source_record = source_by_path[raw_path]
        package_file = package_by_path[raw_path]
        for field in PACKAGE_SOURCE_FIELDS:
            if package_file.get(field) != source_record.get(field):
                mismatches.append(f"{raw_path}:{field}")

    expected_raw_file_count = len(package_files)
    expected_raw_total_bytes = sum(file["raw_bytes"] for file in package_files)
    expected_snapshot_count = len(source_records)
    count_checks = {
        "raw_file_count": expected_raw_file_count,
        "raw_total_bytes": expected_raw_total_bytes,
        "snapshot_count": expected_snapshot_count,
    }
    for field, expected_value in count_checks.items():
        if package_manifest.get(field) != expected_value:
            mismatches.append(f"{field}")

    if mismatches:
        raise ValueError(
            "Package manifest metadata does not match source manifest: "
            f"{mismatches[:10]}"
        )


def verify_archive_members(package_manifest: dict, archive_path: Path) -> None:
    expected_files = {
        file["raw_path"]: (file["raw_sha256"], file["raw_bytes"])
        for file in package_manifest.get("files", [])
    }
    seen_files: dict[str, tuple[str, int]] = {}
    duplicate_members: list[str] = []

    with tarfile.open(archive_path, mode="r:gz") as tar:
        for member in tar.getmembers():
            assert_safe_member(member)
            if member.isdir():
                continue
            if member.name in seen_files:
                duplicate_members.append(member.name)
                continue

            member_file = tar.extractfile(member)
            if member_file is None:
                raise ValueError(f"Could not read archive member: {member.name}")

            digest = hashlib.sha256()
            byte_count = 0
            while chunk := member_file.read(1024 * 1024):
                digest.update(chunk)
                byte_count += len(chunk)
            seen_files[member.name] = (digest.hexdigest(), byte_count)

    expected_paths = set(expected_files)
    seen_paths = set(seen_files)
    mismatches: list[str] = []
    if duplicate_members:
        mismatches.append(f"duplicate_members={duplicate_members[:5]}")
    if expected_paths != seen_paths:
        missing = sorted(expected_paths - seen_paths)
        extra = sorted(seen_paths - expected_paths)
        mismatches.append(f"missing={missing[:5]} extra={extra[:5]}")

    bad_members = sorted(
        path
        for path in expected_paths & seen_paths
        if expected_files[path] != seen_files[path]
    )
    if bad_members:
        mismatches.append(f"bad_hash_or_size={bad_members[:5]}")

    if mismatches:
        raise ValueError(
            "Archive members do not match package manifest: "
            f"{'; '.join(mismatches)}"
        )


def assert_safe_member(member: tarfile.TarInfo) -> None:
    name = member.name
    if Path(name).is_absolute() or ".." in Path(name).parts:
        raise ValueError(f"Refusing unsafe archive path: {name}")
    if not name.startswith(RAW_PATH_PREFIX):
        raise ValueError(f"Unexpected archive member outside raw prefix: {name}")
    if member.isdir():
        return
    if not member.isfile():
        raise ValueError(f"Refusing non-file archive member: {name}")


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

    args.require_unpacked_raw = True
    verify_raw_snapshots(args)
    print(f"Unpacked {archive_path.relative_to(PROJECT_ROOT)}")


def verify_raw_snapshots(args: argparse.Namespace) -> None:
    archive_path = Path(args.archive).resolve()
    package_manifest_path = Path(args.package_manifest).resolve()
    source_manifest_path = Path(args.source_manifest).resolve()
    sha256_path = Path(args.sha256).resolve()
    package_manifest = load_package_manifest(package_manifest_path)

    verify_archive_hash(package_manifest, archive_path)
    verify_sha256_sidecar(sha256_path, archive_path)

    verify_package_matches_source_manifest(package_manifest, source_manifest_path)
    verify_archive_members(package_manifest, archive_path)

    require_unpacked_raw = getattr(args, "require_unpacked_raw", False)
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
        if missing_files and not bad_hashes and not require_unpacked_raw:
            print(
                "Verified package archive and manifest; "
                f"{len(missing_files)} raw snapshots are not unpacked locally."
            )
            return
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
    verify_parser.add_argument(
        "--require-unpacked-raw",
        action="store_true",
        help="Also require every packaged raw file to exist in source-snapshots/raw/.",
    )
    verify_parser.set_defaults(func=verify_raw_snapshots)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
