## 2024-06-09 - Avoid glob.glob for pattern matching

**Learning:** `glob.glob` is an expensive file-system operation. `ContextOptimizer` was using `glob.glob` to see if a file matched a recursive glob pattern (`**`). This requires reading the file system to match strings, which takes orders of magnitude longer than simply matching the string against the glob pattern in-memory. In tests, using `glob.glob` even with a cache took ~4 seconds vs ~0.2 seconds for using `_glob_match` on paths directly.

**Action:** For string pattern matching against known path strings, use `_glob_match` from `src/apm_cli/primitives/discovery.py` instead of `glob.glob` to avoid expensive filesystem scans.
