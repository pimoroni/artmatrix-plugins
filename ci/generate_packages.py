#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_NAME = "package.json"
INDEX_NAME = "index.json"
INITIAL_VERSION = "1.0.0"
TARGET_PREFIX = "plugins"
NOT_PLUGINS = {"ci", "docs"}
# the plugin's picture, shipped with it for the settings page
THUMBNAIL = "thumbnail.png"
# shown on the install page's cards, so every plugin needs both
DETAILS = ("description", "author")
# three lines on a phone-width card
DESCRIPTION_MAX = 60
EXCLUDE_NAMES = {MANIFEST_NAME, "config.json", ".DS_Store", "Thumbs.db"}
EXCLUDE_SUFFIXES = {".pyc", ".mpy", ".swp"}
EXCLUDE_TAILS = ("_tokens.json",)
EXCLUDE_DIRS = {"__pycache__", ".ruff_cache", ".git"}
SIZE_WARN_BYTES = 256 * 1024


def is_plugin(path):
    if not path.is_dir() or path.name.startswith("."):
        return False
    if path.name in NOT_PLUGINS:
        return False
    return (path / "__init__.py").is_file()


def find_plugins():
    return sorted((path for path in ROOT.iterdir() if is_plugin(path)), key=lambda p: p.name)


def is_shippable(path, plugin):
    if path.name in EXCLUDE_NAMES or path.suffix in EXCLUDE_SUFFIXES:
        return False
    if any(path.name.endswith(tail) for tail in EXCLUDE_TAILS):
        return False
    if path.name.startswith("."):
        return False
    return not any(part in EXCLUDE_DIRS for part in path.relative_to(plugin).parts[:-1])


def plugin_files(plugin):
    files = [path for path in plugin.rglob("*") if path.is_file() and is_shippable(path, plugin)]
    return sorted(path.relative_to(plugin).as_posix() for path in files)


def manifest_for(plugin):
    # The display name, version, description, author and requires_internet are the
    # plugin author's to set, so all are read back out of the manifest this overwrites.
    try:
        existing = json.loads((plugin / MANIFEST_NAME).read_text())
    except (OSError, ValueError):
        existing = {}

    name = existing.get("name")
    version = existing.get("version")

    manifest = {}
    if isinstance(name, str) and name.strip():
        manifest["name"] = name
    else:
        manifest["name"] = " ".join(word[:1].upper() + word[1:] for word in plugin.name.split("_"))

    manifest["version"] = version if isinstance(version, str) and version else INITIAL_VERSION

    # no fallback for these, validate_index() fails a plugin without them
    for field in DETAILS:
        value = existing.get(field)
        if isinstance(value, str) and value.strip():
            manifest[field] = value

    # no fallback, a wrong guess would mislead offline users, main() fails without it
    if isinstance(existing.get("requires_internet"), bool):
        manifest["requires_internet"] = existing["requires_internet"]

    manifest["urls"] = [[f"{TARGET_PREFIX}/{plugin.name}/{path}", path] for path in plugin_files(plugin)]

    return manifest


def serialise(manifest):
    return json.dumps(manifest, indent=2) + "\n"


def index_for(plugins):
    # details sits beside plugins rather than inside it: firmware already out there
    # reads each plugins value as the display name string
    manifests = {plugin.name: manifest_for(plugin) for plugin in plugins}
    return {"plugins": {name: manifest["name"] for name, manifest in manifests.items()},
            "details": {name: {field: manifest.get(field) for field in DETAILS}
                        for name, manifest in manifests.items()}}


def validate_index(index, plugins):
    if not isinstance(index, dict):
        return ["index is not a JSON object"]

    catalogue = index.get("plugins")
    if not isinstance(catalogue, dict):
        return ["'plugins' is missing or is not an object"]

    problems = []

    if not catalogue:
        problems.append("'plugins' is empty, which would empty every device's catalogue")

    names = list(catalogue)

    for name in names:
        if not isinstance(name, str) or not name:
            problems.append(f"plugin name {name!r} is not a non-empty string")
        elif name.strip() != name or "/" in name or name.startswith("."):
            problems.append(f"plugin name {name!r} is not a usable directory name")

        display = catalogue[name]
        if not isinstance(display, str) or not display.strip():
            problems.append(f"display name {display!r} for {name!r} is not a non-empty string")

    if names != sorted(names):
        problems.append("'plugins' is not sorted")

    details = index.get("details")
    if not isinstance(details, dict):
        problems.append("'details' is missing or is not an object")
        details = {}

    for name in names:
        entry = details.get(name)
        if not isinstance(entry, dict):
            problems.append(f"'{name}' has no entry in 'details'")
            continue

        for field in DETAILS:
            value = entry.get(field)
            if not isinstance(value, str) or not value.strip():
                problems.append(f"'{name}' has no {field}, set one in {name}/{MANIFEST_NAME}")

        description = entry.get("description")
        if isinstance(description, str) and len(description) > DESCRIPTION_MAX:
            problems.append(f"'{name}' description is {len(description)} characters, the limit is {DESCRIPTION_MAX}")

    installable = {plugin.name for plugin in plugins if (plugin / MANIFEST_NAME).is_file()}
    for name in names:
        if isinstance(name, str) and name not in installable:
            problems.append(f"'{name}' is in the index but has no {MANIFEST_NAME}")

    return problems


def untracked_plugins(plugins):
    try:
        listing = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT, capture_output=True, check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []

    tracked = {Path(path).parts[0] for path in listing.decode().split("\0") if path}
    return [plugin.name for plugin in plugins if plugin.name not in tracked]


def total_bytes(plugin):
    return sum((plugin / path).stat().st_size for path in plugin_files(plugin))


def main():
    parser = argparse.ArgumentParser(
        description="Generate each plugin's package.json and the index.json catalogue.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="report manifests that are missing or out of date, and exit non-zero",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="only report problems",
    )
    args = parser.parse_args()

    plugins = find_plugins()
    if not plugins:
        print(f"No plugins found in {ROOT}", file=sys.stderr)
        return 1

    stale = []
    written = []
    problems = []

    for plugin in plugins:
        manifest_path = plugin / MANIFEST_NAME
        manifest = manifest_for(plugin)
        wanted = serialise(manifest)

        # untracked plugins are left out of the index, so validate_index() never sees them
        if "requires_internet" not in manifest:
            problems.append(f"'{plugin.name}' has no requires_internet, set true or false in {plugin.name}/{MANIFEST_NAME}")

        try:
            current = manifest_path.read_text()
        except OSError:
            current = None

        if current != wanted:
            if args.check:
                stale.append(plugin.name)
            else:
                manifest_path.write_text(wanted)
                written.append(plugin.name)

        if not args.quiet:
            count = len(manifest["urls"])
            size = total_bytes(plugin)
            note = "  <-- large, slow to install" if size > SIZE_WARN_BYTES else ""
            print(f"{plugin.name:<24} {count:>3} files  {size / 1024:>7.1f} kB{note}")

    untracked = untracked_plugins(plugins)
    shippable = [plugin for plugin in plugins if plugin.name not in untracked]

    if untracked and not args.quiet:
        print("", file=sys.stderr)
        print(f"Left out of {INDEX_NAME}, not committed:", file=sys.stderr)
        for name in untracked:
            print(f"  {name}", file=sys.stderr)

    index_path = ROOT / INDEX_NAME
    wanted_index = serialise(index_for(shippable))

    try:
        current_index = index_path.read_text()
    except OSError:
        current_index = None

    index_stale = current_index != wanted_index

    if index_stale and not args.check:
        index_path.write_text(wanted_index)

    problems += validate_index(json.loads(wanted_index), shippable)
    if problems:
        print("", file=sys.stderr)
        print(f"{INDEX_NAME} would not be safe to publish:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    if args.check:
        if index_stale:
            stale.append(INDEX_NAME)

        if stale:
            print("", file=sys.stderr)
            print("These are missing or out of date:", file=sys.stderr)
            for name in stale:
                print(f"  {name if name == INDEX_NAME else f'{name}/{MANIFEST_NAME}'}", file=sys.stderr)
            print("", file=sys.stderr)
            print("Run `python ci/generate_packages.py` and commit the result.", file=sys.stderr)
            return 1
        print(f"\n{len(plugins)} manifests and {INDEX_NAME} up to date.")
        return 0

    if index_stale:
        written.append(INDEX_NAME)

    if written:
        print(f"\nWrote {len(written)} file(s): {', '.join(written)}")
    else:
        print(f"\n{len(plugins)} manifests and {INDEX_NAME} already up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
