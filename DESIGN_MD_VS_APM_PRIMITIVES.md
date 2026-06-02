# Analysis: DESIGN.md vs APM Primitives

## Purpose of DESIGN.md

The [DESIGN.md specification](https://github.com/google-labs-code/design.md) serves a dual purpose:
1. **Machine-Readable Design Tokens:** It uses YAML frontmatter to provide coding agents with structured, exact values for a design system (e.g., colors, typography, spacing).
2. **Human-Readable Rationale:** It uses Markdown prose to explain *why* these values exist and *how* they should be applied (e.g., "Deep ink for headlines", "Boston Clay for call-to-action buttons").

The primary goal of `DESIGN.md` is to give AI coding agents a persistent, structured understanding of a project's visual identity so they can generate UI code that adheres to that identity.

## Purpose of APM Primitives

APM (Agent Package Manager) manages AI agent context through specific primitives, primarily:
1. **Instructions (`.instructions.md`):** Provide explicit, project-specific or package-specific directives to the agent (e.g., coding standards, architecture rules).
2. **Context (`.context.md` / `.memory.md`):** Provide background information or reference material needed for tasks.
3. **Chatmodes/Agents (`.agent.md`):** Define persona or role-based configurations for the agent.
4. **Skills (`SKILL.md`):** Act as package meta-guides describing how to use a specific APM package or tool. For example, a skill might describe how to run a test suite or deploy to a specific environment.

## Comparison: DESIGN.md vs. SKILL.md

| Feature | `DESIGN.md` | `SKILL.md` / APM Primitives |
| :--- | :--- | :--- |
| **Domain** | Visual Identity, UI/UX Design Systems | Workflows, Tool Usage, Coding Conventions |
| **Structure** | Strict YAML Frontmatter (Tokens) + Markdown | Basic Frontmatter (Name, Desc) + Markdown |
| **Agent Action** | Passive Context (Agent *reads* to generate UI) | Active/Procedural (Agent *executes* workflows or follows rules) |
| **Target Audience** | UI/UX Agents, Frontend Developers | General Coding Agents, Orchestrators |

*   `SKILL.md` tells an agent *how to do something* (e.g., "How to deploy to Vercel").
*   `DESIGN.md` tells an agent *what things look like* (e.g., "Buttons are Boston Clay with 4px rounding").

## Appropriateness for APM Management

**Conclusion: `DESIGN.md` is highly appropriate to be managed by APM.**

**Reasoning:**
1.  **Context is Dependency:** APM's core philosophy is that "AI coding agents need context to be useful... APM treats it that way" (from the APM README). A design system is a critical piece of context for any frontend or full-stack project.
2.  **Transitive Nature of Design:** Design systems are often distributed as packages (e.g., Material Design, Tailwind configurations). APM's ability to resolve transitive dependencies means a project could `apm install my-company/design-system`, and the agent would automatically inherit the `DESIGN.md` tokens and prose.
3.  **Governance and Consistency:** APM provides governance and drift detection. Managing `DESIGN.md` through APM ensures that all developers (and their agents) in an organization are using the identical, approved, and locked version of the design system.

In essence, `DESIGN.md` perfectly fits the definition of "agentic dependency" that APM is designed to manage. While its internal structure (tokens) is specific to UI design, its role as a context provider aligns identically with APM's goals.

## References
*   [DESIGN.md Specification (Google Labs)](https://github.com/google-labs-code/design.md)
*   APM Repository README and Architecture Documentation.
