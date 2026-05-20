# Writing CLAUDE.md Files

## Principles
- CLAUDE.md is a **context injection file**, not documentation. Every line consumes context budget.
- Target under 100 lines. Ask: "If I remove this line, will Claude make mistakes?" — if no, cut it.
- Only document what Claude gets wrong. Don't write a comprehensive manual.
- Don't use CLAUDE.md as a linter — use actual linters, formatters, and hooks for that.

## Structure
1. **One-liner project context** — orient Claude ("This is a .NET model library for low-code app models")
2. **Build/test commands** — only the ones Claude needs to run
3. **Architecture** — major components and folder structure, briefly
4. **Gotchas** — project-specific pitfalls and non-obvious conventions
5. **Design rationale** — rejected alternatives and why, to prevent Claude from re-suggesting them

## Progressive Disclosure
- Keep the root CLAUDE.md lean. Use sub-directory CLAUDE.md files for component-specific context.
- Don't dump everything — tell Claude **where to find** detailed info so it loads only when needed.
- Use path-scoped rules (`.claude/rules/` with `paths` frontmatter) to point Claude to sub-directory CLAUDE.md files when working on specific areas.

## What NOT to Include
- Style guides (use linters and `.editorconfig`)
- Full API references (Claude can read the code)
- Obvious patterns Claude already knows (standard .NET, common frameworks)
- Anything that doesn't prevent a concrete mistake
