#!/usr/bin/env python3
"""LeafOS README and version steward used by the root ``program`` shell."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[4]
MANIFEST = ROOT / "assets" / "brand" / "immutable" / "manifest.json"
START = "<!-- leafos-program:brand-asset:start -->"
END = "<!-- leafos-program:brand-asset:end -->"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
BADGE = re.compile(r"^\s*(?:!\[[^]]*]\([^)]*\)|<img\b[^>]*>)\s*$", re.I)
DIVIDER = re.compile(r"^\s*(?P<mark>[-_])(?:\s*(?P=mark)){11,}\s*$")
FENCE = re.compile(r"^\s*(?P<fence>`{3,}|~{3,})")
SKIP_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "vendor",
    "__pycache__",
    "archive",
    "imports",
    "imports2",
    "imports3",
    "runs",
    "reports",
    "fixtures",
    "training-template",
    "vsepr-day98-leafos-run1",
}


class ProgramError(RuntimeError):
    """A concise operator-facing failure."""


def _inside_root(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(ROOT)
    except ValueError as exc:
        raise ProgramError(f"Target must stay under the LeafOS root: {resolved}") from exc
    return resolved


def target_path(value: str | Path) -> Path:
    path = Path(value)
    return _inside_root(path if path.is_absolute() else ROOT / path)


def load_manifest() -> dict[str, object]:
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProgramError(f"Cannot read immutable asset manifest: {MANIFEST}") from exc
    required = {"path", "sha256", "bytes", "immutable"}
    if not required.issubset(data) or data.get("immutable") is not True:
        raise ProgramError("Immutable asset manifest is incomplete or mutable")
    return data


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_asset() -> tuple[Path, dict[str, object]]:
    manifest = load_manifest()
    asset = target_path(str(manifest["path"]))
    if not asset.is_file():
        raise ProgramError(f"Permanent asset is missing: {asset}")
    actual_hash = sha256(asset)
    actual_bytes = asset.stat().st_size
    if actual_hash.lower() != str(manifest["sha256"]).lower():
        raise ProgramError(f"Permanent asset hash mismatch: {asset}")
    if actual_bytes != int(manifest["bytes"]):
        raise ProgramError(f"Permanent asset size mismatch: {asset}")
    return asset, manifest


def _remove_managed_block(text: str) -> str:
    pattern = re.compile(
        rf"\n?[ \t]*{re.escape(START)}.*?{re.escape(END)}[ \t]*\n?",
        re.DOTALL,
    )
    return pattern.sub("\n", text)


def branded_readme(text: str, readme: Path, asset: Path) -> str:
    """Return README text with one managed asset block after its badge group."""
    text = _remove_managed_block(text).replace("\r\n", "\n")
    lines = text.splitlines()
    heading = next((i for i, line in enumerate(lines) if re.match(r"^#\s+\S", line)), None)
    if heading is None:
        raise ProgramError("README needs a level-one title before it can be managed")

    last_badge: int | None = None
    for index in range(heading + 1, min(len(lines), heading + 50)):
        stripped = lines[index].strip()
        if stripped in {"</div>", "---"} or stripped.startswith("**"):
            break
        if BADGE.match(lines[index]) and ("badge" in stripped.lower() or "shields.io" in stripped.lower()):
            last_badge = index

    insert_at = (last_badge + 1) if last_badge is not None else (heading + 1)
    relative = Path(os.path.relpath(asset, readme.parent)).as_posix()
    block = [
        "",
        START,
        f'<img src="{relative}" alt="LeafOS ASCII continual-growth mark" width="720">',
        END,
        "",
    ]
    lines[insert_at:insert_at] = block
    result = "\n".join(lines)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.rstrip() + "\n"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(temp_name, path)
    finally:
        try:
            Path(temp_name).unlink()
        except FileNotFoundError:
            pass


def split_sections(text: str) -> tuple[list[str], int]:
    """Split on long dash/underscore dividers outside fenced code blocks."""
    parts: list[str] = []
    current: list[str] = []
    separator_count = 0
    fence_mark: str | None = None

    for line in text.replace("\r\n", "\n").splitlines():
        fence = FENCE.match(line)
        if fence:
            mark = fence.group("fence")[0]
            if fence_mark is None:
                fence_mark = mark
            elif fence_mark == mark:
                fence_mark = None
            current.append(line)
            continue
        if fence_mark is None and DIVIDER.fullmatch(line):
            separator_count += 1
            section = "\n".join(current).strip()
            if section:
                parts.append(section + "\n")
            current = []
            continue
        current.append(line)

    section = "\n".join(current).strip()
    if section:
        parts.append(section + "\n")
    return parts, separator_count


def _section_filename(index: int, text: str) -> str:
    heading = next(
        (line.lstrip("#").strip() for line in text.splitlines() if re.match(r"^#{1,6}\s+\S", line)),
        "part",
    )
    slug = re.sub(r"[^a-z0-9]+", "-", heading.casefold()).strip("-")[:48] or "part"
    return f"{index:02d}-{slug}.md"


def split_markdown(markdown_value: str, output_value: str | None, check: bool) -> dict[str, object]:
    source = target_path(markdown_value)
    if not source.is_file():
        raise ProgramError(f"Markdown source does not exist: {source}")
    if source.suffix.lower() not in {".md", ".markdown"}:
        raise ProgramError("Split source must be a .md or .markdown file")

    output = target_path(output_value) if output_value else source.parent / f"{source.stem}.parts"
    output = _inside_root(output)
    if output.exists() and not output.is_dir():
        raise ProgramError(f"Split output must be a directory: {output}")
    parts, separator_count = split_sections(source.read_text(encoding="utf-8-sig"))
    filenames = [_section_filename(index, part) for index, part in enumerate(parts, 1)]
    result: dict[str, object] = {
        "action": "split-markdown",
        "source": str(source),
        "output": str(output),
        "separators": separator_count,
        "parts": len(parts),
        "files": filenames,
        "written": False,
    }
    if separator_count == 0 or check:
        return result

    split_manifest = output / ".leafos-program-split.json"
    old_files: list[str] = []
    if output.exists() and any(output.iterdir()):
        if not split_manifest.is_file():
            raise ProgramError(f"Output directory is not managed by program: {output}")
        old_manifest = json.loads(split_manifest.read_text(encoding="utf-8"))
        expected_source = source.relative_to(ROOT).as_posix()
        if old_manifest.get("source") != expected_source:
            raise ProgramError(f"Managed output belongs to another source: {output}")
        old_files = [str(name) for name in old_manifest.get("files", [])]

    output.mkdir(parents=True, exist_ok=True)
    for name, part in zip(filenames, parts):
        _atomic_write(output / name, part)
    manifest = {
        "schema": "leafos.markdown-split/v1",
        "source": source.relative_to(ROOT).as_posix(),
        "source_sha256": sha256(source),
        "separators": separator_count,
        "files": filenames,
    }
    _atomic_write(split_manifest, json.dumps(manifest, indent=2) + "\n")
    for stale in sorted(set(old_files) - set(filenames)):
        stale_path = output / Path(stale).name
        if stale_path.parent == output and stale_path.is_file():
            stale_path.unlink()
    result["written"] = True
    return result


def update_readme(readme_value: str, source_value: str | None, check: bool) -> dict[str, object]:
    asset, _ = verify_asset()
    readme = target_path(readme_value)
    source = Path(source_value).expanduser().resolve() if source_value else readme
    if not source.is_file():
        raise ProgramError(f"README source does not exist: {source}")
    before = readme.read_text(encoding="utf-8") if readme.exists() else ""
    proposed = branded_readme(source.read_text(encoding="utf-8-sig"), readme, asset)
    changed = proposed != before.replace("\r\n", "\n")
    if changed and not check:
        _atomic_write(readme, proposed)
    return {
        "action": "update-readme",
        "readme": str(readme),
        "source": str(source),
        "changed": changed,
        "written": bool(changed and not check),
        "asset": str(asset),
    }


def _current_version() -> str:
    return (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def _versioned_readme(text: str, old: str, new: str) -> str:
    text = text.replace(f"snapshot-{old}-", f"snapshot-{new}-")
    visible_version = re.compile(
        rf"(?P<prefix>\b(?:partially\s+)?working\s+\*{{0,2}}){re.escape(old)}(?P<suffix>\s+snapshot\b)",
        re.I,
    )
    return visible_version.sub(rf"\g<prefix>{new}\g<suffix>", text)


def change_version(new: str, readmes: Iterable[str], check: bool) -> dict[str, object]:
    if not SEMVER.fullmatch(new):
        raise ProgramError("Version must use numeric semantic form, for example 0.9.5")
    old = _current_version()
    root_metadata = ROOT / "leafos.root.json"
    taskpack_version = ROOT / "ProjectLeaf" / "leafos_taskpack" / "VERSION"
    metadata = json.loads(root_metadata.read_text(encoding="utf-8"))
    metadata["version"] = new
    updates: dict[Path, str] = {
        ROOT / "VERSION": new + "\n",
        taskpack_version: new + "\n",
        root_metadata: json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
    }
    for value in readmes:
        readme = target_path(value)
        if readme.exists():
            updates[readme] = _versioned_readme(readme.read_text(encoding="utf-8"), old, new)

    changed = [path for path, text in updates.items() if not path.exists() or path.read_text(encoding="utf-8").replace("\r\n", "\n") != text]
    if not check:
        originals = {path: path.read_bytes() if path.exists() else None for path in changed}
        try:
            for path in changed:
                _atomic_write(path, updates[path])
        except Exception:
            for path, original in originals.items():
                if original is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(original)
            raise
    return {
        "action": "change-version",
        "from": old,
        "to": new,
        "changed": [str(path.relative_to(ROOT)) for path in changed],
        "written": bool(changed and not check),
    }


def list_readmes(include_archived: bool = False) -> list[str]:
    found: list[str] = []
    for directory, child_dirs, filenames in os.walk(ROOT):
        if not include_archived:
            child_dirs[:] = [name for name in child_dirs if name.casefold() not in SKIP_DIRS]
        base = Path(directory)
        for name in filenames:
            path = base / name
            if name.lower().startswith("readme") and path.suffix.lower() in {"", ".md", ".markdown"}:
                found.append(path.relative_to(ROOT).as_posix())
    return sorted(found, key=str.lower)


def readme_has_asset(readme: Path, asset: Path) -> bool:
    if not readme.is_file():
        return False
    relative = Path(os.path.relpath(asset, readme.parent)).as_posix()
    text = readme.read_text(encoding="utf-8")
    return START in text and END in text and f'src="{relative}"' in text


def status(readme_value: str) -> dict[str, object]:
    asset, manifest = verify_asset()
    readme = target_path(readme_value)
    taskpack = ROOT / "ProjectLeaf" / "leafos_taskpack" / "VERSION"
    versions_match = _current_version() == taskpack.read_text(encoding="utf-8").strip()
    readme_linked = readme_has_asset(readme, asset)
    return {
        "status": "ok" if versions_match and readme_linked else "attention",
        "root": str(ROOT),
        "version": _current_version(),
        "taskpack_version": taskpack.read_text(encoding="utf-8").strip(),
        "versions_match": versions_match,
        "asset": str(asset.relative_to(ROOT).as_posix()),
        "asset_sha256": manifest["sha256"],
        "asset_verified": True,
        "readme": str(readme.relative_to(ROOT).as_posix()),
        "readme_linked": readme_linked,
    }


def print_result(result: object, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    if isinstance(result, dict):
        for key, value in result.items():
            print(f"{key.replace('_', ' ')}: {value}")
    elif isinstance(result, list):
        print("\n".join(str(item) for item in result))
    else:
        print(result)


def confirm(prompt: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        raise ProgramError("This write needs --yes when input is non-interactive")
    return input(f"{prompt} [y/N] ").strip().lower() in {"y", "yes"}


def interactive() -> int:
    while True:
        print("\nLeafOS program — README and release steward")
        print("  1  Update README")
        print("  2  Change version")
        print("  3  Verify asset and README")
        print("  4  Preview README update")
        print("  5  List README files")
        print("  6  Split Markdown [developer]")
        print("  7  Exit")
        try:
            choice = input("program> ").strip().lower()
            if choice in {"1", "update", "readme"}:
                value = input("README path [README.md]: ").strip() or "README.md"
                if confirm(f"Update {value}?", False):
                    print_result(update_readme(value, None, False))
            elif choice in {"2", "version"}:
                value = input(f"New version (current {_current_version()}): ").strip()
                preview = change_version(value, ["README.md"], True)
                print_result(preview)
                if confirm("Apply this version change?", False):
                    print_result(change_version(value, ["README.md"], False))
            elif choice in {"3", "verify", "status"}:
                value = input("README path [README.md]: ").strip() or "README.md"
                print_result(status(value))
            elif choice in {"4", "preview", "check"}:
                value = input("README path [README.md]: ").strip() or "README.md"
                print_result(update_readme(value, None, True))
            elif choice in {"5", "list", "readmes"}:
                print_result(list_readmes())
            elif choice in {"6", "split", "split-markdown"}:
                value = input("Markdown path: ").strip()
                preview = split_markdown(value, None, True)
                print_result(preview)
                if preview["separators"] and confirm("Write these split files?", False):
                    print_result(split_markdown(value, None, False))
            elif choice in {"7", "q", "quit", "exit"}:
                return 0
            else:
                print("Choose 1–7, or type the action name.")
        except (EOFError, KeyboardInterrupt):
            print("\nLeaving program.")
            return 0
        except ProgramError as exc:
            print(f"program: {exc}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="program", description=__doc__)
    sub = parser.add_subparsers(dest="command")

    status_parser = sub.add_parser("status", aliases=["verify"], help="verify the permanent asset and README link")
    status_parser.add_argument("readme", nargs="?", default="README.md")
    status_parser.add_argument("--json", action="store_true")

    update = sub.add_parser("update-readme", aliases=["readme"], help="insert or refresh the managed local image reference")
    update.add_argument("readme", nargs="?", default="README.md")
    update.add_argument("--source", help="replace content from this Markdown source before branding")
    update.add_argument("--check", action="store_true", help="preview without writing")
    update.add_argument("--yes", action="store_true", help="confirm a non-interactive write")
    update.add_argument("--json", action="store_true")

    version = sub.add_parser("change-version", aliases=["version"], help="synchronize LeafOS version authorities")
    version.add_argument("new_version", nargs="?")
    version.add_argument("--readme", action="append", default=[])
    version.add_argument("--check", action="store_true", help="preview without writing")
    version.add_argument("--yes", action="store_true", help="confirm a non-interactive write")
    version.add_argument("--json", action="store_true")

    listing = sub.add_parser("list-readmes", aliases=["list"], help="find README targets beneath the LeafOS root")
    listing.add_argument("--all", action="store_true", help="include archived and imported trees")
    listing.add_argument("--json", action="store_true")

    split = sub.add_parser("split-markdown", aliases=["split"], help="split developer Markdown on divider chains of 12 or more")
    split.add_argument("markdown")
    split.add_argument("--output", help="managed output directory; defaults to NAME.parts")
    split.add_argument("--check", action="store_true", help="preview without writing")
    split.add_argument("--yes", action="store_true", help="confirm a non-interactive write")
    split.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        if not sys.stdin.isatty():
            parser.print_help()
            return 0
        return interactive()
    try:
        if args.command in {"status", "verify"}:
            print_result(status(args.readme), args.json)
        elif args.command in {"update-readme", "readme"}:
            if not args.check and not confirm(f"Update {args.readme}?", args.yes):
                return 1
            print_result(update_readme(args.readme, args.source, args.check), args.json)
        elif args.command in {"change-version", "version"}:
            new = args.new_version
            if not new:
                if not sys.stdin.isatty():
                    raise ProgramError("Supply a version, for example: program version 0.9.5 --yes")
                new = input(f"New version (current {_current_version()}): ").strip()
            readmes = args.readme or ["README.md"]
            preview = change_version(new, readmes, True)
            if not args.check and not confirm(f"Change version {_current_version()} -> {new}?", args.yes):
                return 1
            result = preview if args.check else change_version(new, readmes, False)
            print_result(result, args.json)
        elif args.command in {"list-readmes", "list"}:
            print_result(list_readmes(args.all), args.json)
        elif args.command in {"split-markdown", "split"}:
            preview = split_markdown(args.markdown, args.output, True)
            if not args.check and preview["separators"] and not confirm(
                f"Write {preview['parts']} Markdown parts?", args.yes
            ):
                return 1
            result = preview if args.check or not preview["separators"] else split_markdown(args.markdown, args.output, False)
            print_result(result, args.json)
        return 0
    except (ProgramError, OSError, json.JSONDecodeError) as exc:
        print(f"program: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
