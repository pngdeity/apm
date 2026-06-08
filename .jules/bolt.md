## YYYY-MM-DD - Initial Entry
**Learning:** Initial setup.
**Action:** None.

## 2024-05-18 - Replacing glob.glob with in-memory matching
**Learning:** `glob.glob` with `recursive=True` is an extremely expensive filesystem scan in this codebase, particularly inside hot loops like `ContextOptimizer._file_matches_pattern` which evaluates patterns across many files.
**Action:** Replace `glob.glob` scans with `_glob_match` (from `src/apm_cli/primitives/discovery.py`) which evaluates patterns completely in memory using pre-fetched path strings. Tests still expect a specific side effect (`_glob_set_cache` population) that must be preserved.

## 2024-05-18 - Optimizing fnmatch inside _glob_match_parts
**Learning:** `fnmatch.fnmatch` parsing overhead dominates tight path-matching loops when wildcards aren't actually present in the path segment.
**Action:** Check for common wildcards (`*`, `?`, `[`) and use direct string comparison `==` if absent. This shaves off significant overhead in `_glob_match_parts`.

## 2024-05-18 - Side effects in optimization
**Learning:** Even when replacing expensive logic with purely in-memory evaluation, existing tests may assert on very specific side effects (`self._glob_set_cache` entries, precise `ValueError` exception boundaries during `resolve().relative_to()`).
**Action:** When replacing a component, check how tests interact with it. Here, the test expected `file_path.resolve().relative_to(...)` to throw `ValueError` if the file was outside the base directory, and explicitly checked `_glob_set_cache` to hold paths. Emulating these precise side effects while avoiding full file system scans keeps tests green.
