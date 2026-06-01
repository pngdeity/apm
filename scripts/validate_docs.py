#!/usr/bin/env python3
"""Validate repository documentation quality in one command.

This script is the canonical docs-validation entrypoint for contributors
and CI. It validates:

1. Internal links across in-scope markdown/MDX files
2. Fragment anchors for markdown heading targets
3. Required frontmatter shape for docs site pages
4. Existing lockstep docs regression checks
5. The docs site build (which includes starlight-links-validator)
"""

from __future__ import annotations

import argparse
import posixpath
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote, urlsplit

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_CONTENT_ROOT = REPO_ROOT / "docs" / "src" / "content" / "docs"
DOCS_ASTRO_CONFIG = REPO_ROOT / "docs" / "astro.config.mjs"

DOCS_CONTENT_GLOBS = ("docs/src/content/docs/**/*.md", "docs/src/content/docs/**/*.mdx")

# Intentional markdown-like fixtures and generated prompt assets that are
# not end-user documentation and may contain synthetic or incomplete links.
LINK_CHECK_EXCLUDE_SUBSTRINGS = (
    "/evals/fixtures/",
    "/assets/",
)

EXTERNAL_SCHEMES = {"http", "https", "mailto", "tel", "data"}
HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$")
LINK_RE = re.compile(r"(?<!!)\[[^\]]*]\(([^)]+)\)")
REDIRECT_RE = re.compile(r"['\"](/[^'\"]+)['\"]\s*:\s*['\"](/[^'\"]+)['\"]")


def _slugify_heading(heading: str) -> str:
    text = heading.strip().lower()
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[^\w\- ]", "", text)
    text = text.replace(" ", "-").strip("-")
    return text


def _collect_anchors(text: str) -> set[str]:
    anchors: set[str] = set()
    seen: dict[str, int] = defaultdict(int)
    for line in text.splitlines():
        match = HEADING_RE.match(line)
        if not match:
            continue
        base = _slugify_heading(match.group(2))
        if not base:
            continue
        count = seen[base]
        seen[base] += 1
        anchor = base if count == 0 else f"{base}-{count}"
        anchors.add(anchor)
    return anchors


def _extract_redirect_paths() -> tuple[set[str], set[str]]:
    text = DOCS_ASTRO_CONFIG.read_text(encoding="utf-8")
    sources: set[str] = set()
    destinations: set[str] = set()
    for src, dst in REDIRECT_RE.findall(text):
        sources.add(src.rstrip("/"))
        destinations.add(dst.rstrip("/"))
    return sources, destinations


def _iter_scope_files() -> list[Path]:
    files: set[Path] = set()
    for pattern in DOCS_CONTENT_GLOBS:
        files.update(REPO_ROOT.glob(pattern))
    return sorted(files)


def _is_excluded_for_link_check(path: Path) -> bool:
    norm = f"/{path.relative_to(REPO_ROOT).as_posix()}"
    return any(token in norm for token in LINK_CHECK_EXCLUDE_SUBSTRINGS)


def _route_from_docs_content(path: Path) -> str:
    rel = path.relative_to(DOCS_CONTENT_ROOT).as_posix()
    stem = re.sub(r"\.(md|mdx)$", "", rel)
    if stem.endswith("/index"):
        stem = stem[: -len("/index")]
    return f"/{stem}".rstrip("/")


def _build_docs_route_sets(files: list[Path]) -> tuple[set[str], set[str]]:
    routes: set[str] = set()
    redirects_src, redirects_dst = _extract_redirect_paths()
    for p in files:
        if p.is_relative_to(DOCS_CONTENT_ROOT):
            route = _route_from_docs_content(p)
            for variant in _route_variants(route):
                routes.add(variant)
            if route == "":
                routes.add("/")
    return routes | redirects_src | redirects_dst, redirects_src


def _normalize_route(path: str) -> str:
    normalized = re.sub(r"^/apm(?=/|$)", "", path).rstrip("/")
    return normalized or "/"


def _build_route_to_file(files: list[Path]) -> dict[str, Path]:
    route_to_file: dict[str, Path] = {}
    for p in files:
        if p.is_relative_to(DOCS_CONTENT_ROOT):
            for variant in _route_variants(_route_from_docs_content(p)):
                route_to_file[_normalize_route(variant)] = p
    return route_to_file


def _route_variants(route: str) -> set[str]:
    normalized = _normalize_route(route)
    parts = normalized.split("/")
    dotted = "/".join(part.replace(".", "") for part in parts)
    return {normalized, _normalize_route(dotted)}


def _strip_link_title(link_target: str) -> str:
    target = link_target.strip().strip("<>").strip()
    if not target:
        return target
    if target[0] in {'"', "'"} and target[-1] == target[0]:
        target = target[1:-1]
    for sep in (' "', " '"):
        idx = target.find(sep)
        if idx > 0:
            return target[:idx]
    return target


def _candidate_paths_for_relative(base_file: Path, raw_path: str) -> list[Path]:
    resolved = (base_file.parent / unquote(raw_path)).resolve()
    candidates = [resolved]
    if resolved.suffix == "":
        candidates.extend(
            [
                resolved.with_suffix(".md"),
                resolved.with_suffix(".mdx"),
                resolved / "index.md",
                resolved / "index.mdx",
            ]
        )
    return candidates


def _validate_fragment(
    source: Path,
    target_file: Path,
    fragment: str,
    anchors_by_file: dict[Path, set[str]],
    findings: dict[Path, list[str]],
    line_no: int,
) -> None:
    normalized = _slugify_heading(unquote(fragment).lstrip("#"))
    if not normalized:
        return
    if normalized not in anchors_by_file.get(target_file, set()):
        findings[source].append(
            f"L{line_no}: fragment '#{fragment}' not found in "
            f"{target_file.relative_to(REPO_ROOT)}"
        )


def _validate_links_and_frontmatter(files: list[Path], enforce_fragments: bool) -> int:
    errors_by_rule: dict[str, dict[Path, list[str]]] = {
        "frontmatter": defaultdict(list),
        "internal-link": defaultdict(list),
        "fragment": defaultdict(list),
    }
    anchors_by_file: dict[Path, set[str]] = {}
    docs_routes, redirect_sources = _build_docs_route_sets(files)
    route_to_file = _build_route_to_file(files)

    for p in files:
        text = p.read_text(encoding="utf-8")
        anchors_by_file[p] = _collect_anchors(text)
        if p.is_relative_to(DOCS_CONTENT_ROOT):
            lines = text.splitlines()
            has_frontmatter = len(lines) >= 3 and lines[0].strip() == "---"
            if not has_frontmatter:
                errors_by_rule["frontmatter"][p].append("Missing required YAML frontmatter block")
                continue
            try:
                closing_idx = next(i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---")
            except StopIteration:
                errors_by_rule["frontmatter"][p].append("Frontmatter opening '---' has no closing delimiter")
                continue
            fm_blob = "\n".join(lines[1:closing_idx])
            if not re.search(r"^\s*title\s*:\s*.+$", fm_blob, flags=re.MULTILINE):
                errors_by_rule["frontmatter"][p].append("Frontmatter must include non-empty 'title'")

    for p in files:
        if _is_excluded_for_link_check(p):
            continue
        text = p.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            for raw in LINK_RE.findall(line):
                target = _strip_link_title(raw)
                if not target:
                    continue
                parsed = urlsplit(target)
                if parsed.scheme.lower() in EXTERNAL_SCHEMES:
                    continue
                if target.startswith("//"):
                    continue
                if parsed.scheme and parsed.scheme.lower() not in EXTERNAL_SCHEMES:
                    continue

                path_part = parsed.path
                frag = parsed.fragment

                if path_part == "" and frag:
                    _validate_fragment(
                        p, p, frag, anchors_by_file, errors_by_rule["fragment"], line_no
                    )
                    continue

                if path_part.startswith("/"):
                    normalized = _normalize_route(path_part)
                    if normalized in docs_routes:
                        target_file = route_to_file.get(normalized)
                        if frag and target_file:
                            if target_file not in anchors_by_file:
                                anchors_by_file[target_file] = _collect_anchors(
                                    target_file.read_text(encoding="utf-8")
                                )
                            _validate_fragment(
                                p,
                                target_file,
                                frag,
                                anchors_by_file,
                                errors_by_rule["fragment"],
                                line_no,
                            )
                        continue
                    if normalized in redirect_sources:
                        continue
                    candidate = (REPO_ROOT / normalized.lstrip("/")).resolve()
                    public_candidate = (REPO_ROOT / "docs" / "public" / normalized.lstrip("/")).resolve()
                    if public_candidate.is_file():
                        continue
                    if candidate.is_file() or candidate.is_dir():
                        if frag:
                            if candidate.is_dir():
                                continue
                            if candidate not in anchors_by_file:
                                anchors_by_file[candidate] = _collect_anchors(
                                    candidate.read_text(encoding="utf-8")
                                )
                            _validate_fragment(
                                p,
                                candidate,
                                frag,
                                anchors_by_file,
                                errors_by_rule["fragment"],
                                line_no,
                            )
                        continue
                    errors_by_rule["internal-link"][p].append(
                        f"L{line_no}: absolute internal link target not found: {target!r}"
                    )
                    continue

                if p.is_relative_to(DOCS_CONTENT_ROOT) and not path_part.endswith((".md", ".mdx")):
                    current_route = _normalize_route(_route_from_docs_content(p))
                    resolved_route = _normalize_route(
                        posixpath.normpath(posixpath.join(f"{current_route}/", unquote(path_part)))
                    )
                    if resolved_route in docs_routes:
                        target_file = route_to_file.get(resolved_route)
                        if frag and target_file:
                            if target_file not in anchors_by_file:
                                anchors_by_file[target_file] = _collect_anchors(
                                    target_file.read_text(encoding="utf-8")
                                )
                            _validate_fragment(
                                p,
                                target_file,
                                frag,
                                anchors_by_file,
                                errors_by_rule["fragment"],
                                line_no,
                            )
                        continue
                    if resolved_route in redirect_sources:
                        continue

                candidate_files = _candidate_paths_for_relative(p, path_part)
                existing_target = next((c for c in candidate_files if c.is_file()), None)
                if existing_target is None:
                    if "<" in path_part or ">" in path_part:
                        continue
                    if p.name == "package-relative-links.md" and path_part.startswith(
                        ("../../references/", "../../apm_modules/")
                    ):
                        continue
                    dir_target = (p.parent / unquote(path_part)).resolve()
                    if dir_target.is_dir():
                        continue
                    errors_by_rule["internal-link"][p].append(
                        f"L{line_no}: relative internal link target not found: {target!r}"
                    )
                    continue
                if frag:
                    if existing_target not in anchors_by_file:
                        anchors_by_file[existing_target] = _collect_anchors(
                            existing_target.read_text(encoding="utf-8")
                        )
                    _validate_fragment(
                        p,
                        existing_target,
                        frag,
                        anchors_by_file,
                        errors_by_rule["fragment"],
                        line_no,
                    )

    total_errors = 0
    for rule in ("frontmatter", "internal-link"):
        file_errors = errors_by_rule[rule]
        count = sum(len(v) for v in file_errors.values())
        if count == 0:
            print(f"[+] {rule}: no violations")
            continue
        total_errors += count
        print(f"[x] {rule}: {count} violation(s)")
        for path in sorted(file_errors):
            rel = path.relative_to(REPO_ROOT)
            print(f"    - {rel}:")
            for err in file_errors[path]:
                print(f"      * {err}")

    fragment_findings = errors_by_rule["fragment"]
    fragment_count = sum(len(v) for v in fragment_findings.values())
    if fragment_count == 0:
        print("[+] fragment: no violations")
    else:
        marker = "[x]" if enforce_fragments else "[!]"
        suffix = "violation(s)" if enforce_fragments else "warning(s)"
        print(f"{marker} fragment: {fragment_count} {suffix}")
        for path in sorted(fragment_findings):
            rel = path.relative_to(REPO_ROOT)
            print(f"    - {rel}:")
            for err in fragment_findings[path]:
                print(f"      * {err}")
        if enforce_fragments:
            total_errors += fragment_count
    return total_errors


def _run_command(title: str, command: list[str], cwd: Path | None = None) -> int:
    print(f"\n[>] {title}: {' '.join(command)}")
    completed = subprocess.run(command, cwd=cwd or REPO_ROOT, check=False)
    if completed.returncode == 0:
        print(f"[+] {title}: passed")
    else:
        print(f"[x] {title}: failed with exit code {completed.returncode}")
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip docs site build check (npm --prefix docs run build).",
    )
    parser.add_argument(
        "--skip-help-consistency",
        action="store_true",
        help="Skip tests/unit/policy/test_help_consistency.py.",
    )
    parser.add_argument(
        "--enforce-fragments",
        action="store_true",
        help="Fail the validation when fragment/anchor checks report findings.",
    )
    args = parser.parse_args()

    files = _iter_scope_files()
    if not files:
        print("[x] No in-scope docs files found")
        return 2
    print(f"[>] validating {len(files)} in-scope markdown/MDX files")

    failures = 0
    if _validate_links_and_frontmatter(files, enforce_fragments=args.enforce_fragments):
        failures += 1

    if not args.skip_help_consistency:
        failures += int(
            _run_command(
                "help consistency",
                ["uv", "run", "pytest", "tests/unit/policy/test_help_consistency.py", "-q"],
            )
            != 0
        )

    if not args.skip_build:
        failures += int(
            _run_command("docs build", ["npm", "--prefix", "docs", "run", "build"]) != 0
        )

    if failures:
        print(f"\n[x] docs validation failed ({failures} failing check group(s))")
        return 1
    print("\n[+] docs validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
