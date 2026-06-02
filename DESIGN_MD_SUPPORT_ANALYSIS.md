# Feasibility Analysis: Adding DESIGN.md Support to APM

## 1. Overview and Feasibility

Adding support for `DESIGN.md` to APM is highly feasible and aligns well with the existing architecture. APM already manages agent context through distinct primitives (`Chatmode`, `Instruction`, `Context`, `Skill`). Introducing `DESIGN.md` requires adding a new `Design` primitive.

The `DESIGN.md` specification dictates a file with YAML frontmatter (for machine-readable design tokens like colors and typography) and a Markdown body (for human-readable design rationale). This format is natively supported by APM's current parsing strategy, which utilizes the `frontmatter` library for all primitive parsing.

## 2. Implementation Changes

### A. Data Models (`src/apm_cli/primitives/models.py`)

1.  **New `Design` Dataclass**:
    *   Create a `@dataclass class Design` to represent the parsed `DESIGN.md`.
    *   Fields should include:
        *   `name`: `str` (from frontmatter or default)
        *   `file_path`: `Path`
        *   `description`: `str` (optional)
        *   `content`: `str` (the Markdown body)
        *   `tokens`: `Dict` (to store the parsed YAML frontmatter tokens like `colors`, `typography`, etc.)
        *   `source`: `Optional[str]`
    *   Add a `validate()` method to ensure required fields and basic structure (e.g., valid token schema, checking for required sections based on the spec, or even integrating the `@google/design.md` linter if desired).

2.  **Update `Primitive` Union Type**:
    *   Add `Design` to the `Primitive = Union[Chatmode, Instruction, Context, Skill, Design]` definition.

3.  **Update `PrimitiveCollection`**:
    *   Add a `designs: List[Design]` list to store discovered `DESIGN.md` files.
    *   Add a `_design_index: Dict[str, int]` for O(1) conflict lookups.
    *   Update `_index_for` to handle the `"design"` type.
    *   Update `add_primitive` to handle `isinstance(primitive, Design)`.
    *   Update `all_primitives()` and `count()` to include `designs`.

### B. Discovery (`src/apm_cli/primitives/discovery.py`)

1.  **Pattern Definitions**:
    *   Like `SKILL.md`, `DESIGN.md` is a well-known top-level file rather than a directory-based primitive like chatmodes or instructions.
    *   If `DESIGN.md` is expected to be at the project root, a specific function `_discover_local_design` (similar to `_discover_local_skill`) should be created to look for `Path(base_dir) / "DESIGN.md"`.
    *   Alternatively, if `DESIGN.md` files can exist in subdirectories, they should be added to `LOCAL_PRIMITIVE_PATTERNS` and `DEPENDENCY_PRIMITIVE_PATTERNS`.
    *   Update `PRIMITIVE_SUFFIXES` logic if necessary (though it skips files that are exact basenames like `SKILL.md` or `DESIGN.md`).

2.  **Discovery Logic**:
    *   Update `discover_primitives` to call the new discovery logic for `DESIGN.md` locally.
    *   Update `scan_dependency_primitives` (or create `_discover_design_in_directory`) to look for `DESIGN.md` in dependency roots alongside `SKILL.md`.

### C. Parsing (`src/apm_cli/primitives/parser.py`)

1.  **New Parser Function**:
    *   Implement `parse_design_file(file_path: Union[str, Path], source: str = None) -> Design`.
    *   This function will load the file using `frontmatter.load(f)`.
    *   It will extract the `metadata` (tokens) and `content` (prose) and instantiate the `Design` dataclass.

2.  **Update Routing in `parse_primitive_file`**:
    *   If `DESIGN.md` is discovered via patterns, update the routing logic to call `parse_design_file` when `file_path.name == "DESIGN.md"`. However, if handled like `SKILL.md`, it might bypass `parse_primitive_file` entirely and call `parse_design_file` directly during discovery.

### D. Compilation (`src/apm_cli/compilation/`)

This is the most critical part: how should `DESIGN.md` be injected into the final agent context?

1.  **Context Optimizer (`src/apm_cli/compilation/context_optimizer.py`)**:
    *   If `DESIGN.md` is treated as general context, the context optimizer needs to account for it when ranking and packing files.

2.  **Agents Compiler (`src/apm_cli/compilation/agents_compiler.py` & `template_builder.py`)**:
    *   Should `DESIGN.md` be rendered as a dedicated section in `AGENTS.md`? If so, `template_builder.py` needs a `render_design_block` function.
    *   It could be appended as a new section like `## Design System` containing the content and potentially a serialized version of the tokens.

3.  **Target-Specific Formatters (`claude_formatter.py`, `gemini_formatter.py`, etc.)**:
    *   Update formatters to handle the new `Design` primitive if they need to format the tokens or markdown prose in a specific way for different LLMs (e.g., Claude might prefer the raw markdown, while Copilot might need it injected into `.github/copilot-instructions.md`).

## 3. Potential Challenges & Considerations

*   **Linter Integration**: The `DESIGN.md` spec includes a CLI for linting (`@google/design.md`). APM could optionally integrate this linter as a validation step during `apm install` or `apm build`, emitting warnings if a `DESIGN.md` is malformed. This would require an optional dependency or invoking `npx`. For Python, it might be better to re-implement basic validation natively in the `Design.validate()` method.
*   **Token Merging**: If multiple dependencies provide a `DESIGN.md` file, how are conflicts resolved? Currently, APM handles conflicts at the file level (local wins, or first dependency wins). For `DESIGN.md`, it might make sense to *merge* tokens if they don't overlap, or strictly follow the file-level override strategy. The file-level override is simpler and consistent with APM's current `PrimitiveCollection` behavior.
*   **Prompt Weight**: Design systems can be large. Injecting the entire `DESIGN.md` into every prompt might consume significant token budget. It might be necessary to allow agents to selectively request the design system context, or compile a "minified" version of the tokens for the LLM.

## 4. Conclusion

Supporting `DESIGN.md` is a straightforward extension of APM's existing primitive-based architecture. The core tasks involve defining the new data model, setting up discovery and parsing for the `DESIGN.md` filename, and updating the compilation templates to inject the design context into the final agent instruction files.