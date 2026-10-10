# Repository Guidelines

## Project Structure

This is a Python package using a `src` layout. Package code belongs in `src/toolsku/`; the current entry point is `main()` in `src/toolsku/__init__.py`. The planned web stack is FastAPI, Jinja templates, Bootstrap, and plain JavaScript. Keep Jinja HTML in `views/`, Bootstrap files in `assets/bootstrap/`, and browser scripts in `assets/js/`. Put new automated tests in `tests/` and name them `test_*.py`.

## Development Commands

- `uv sync` installs the project environment from the lockfile.
- `uv run python -c "from toolsku import main; main()"` runs the current entry point.
- `uv build` creates package distributions.
- `uv run pytest` runs the test suite once pytest and tests have been added. There are no test files in the current source tree.

## Style and Naming

Use four spaces for indentation, type hints for public functions, `snake_case` for functions and modules, and `CapWords` for classes. Keep modules focused on one task. No formatter or linter has been identified in the files reviewed; follow standard Python style and avoid introducing tooling without a project need.

## Testing

Add focused tests under `tests/` and use descriptive names such as `test_parses_input`. Cover normal behavior and relevant edge cases. No coverage threshold is established.

## Commits and Pull Requests

The repository has no commit history yet, so no commit convention is established. Use a short imperative subject (for example, `Add input validation`). Pull requests should explain the change and its reason, list checks run, and link a related issue when one exists. Include screenshots only when a change affects a visual interface.

## Contributor and Agent Practices

Do not read files matched by `.gitignore`. Avoid reading configuration files such as `.env`, YAML, TOML, or INI files; example configurations (for example, `.env.example`) may be read.

For backend work, focus first on correct business logic and use the `ponytail` skill to keep the solution small and complete. For FastAPI endpoints, follow the `fastapi` skill where relevant. Use reusable functions where useful, and watch for N+1 queries, mapping bottlenecks, race conditions, and performance issues.

For frontend work involving plain JavaScript, CSS, Bootstrap, or Tailwind, apply the `antislop` skill to guide visual and interaction decisions. Use plain JavaScript for browser behavior; do not add a JavaScript framework unless requested. In Vue or React, make each reusable component responsible for one task. In brainstorming, correct inaccurate assumptions with reasons and offer a practical recommendation.

<!-- antislop:start -->
## antislop

For UI, copy, accessibility, and responsive layout work, read the installed antislop core and the relevant skill files:

- Core: `/Users/madina/.codex/plugins/cache/anti-slop/antislop/3.2.20/antislop.md`
- UI: `/Users/madina/.codex/plugins/cache/anti-slop/antislop/3.2.20/skills/antislop-ui/SKILL.md`
- Copy: `/Users/madina/.codex/plugins/cache/anti-slop/antislop/3.2.20/skills/antislop-copywriting/SKILL.md`
- Accessibility: `/Users/madina/.codex/plugins/cache/anti-slop/antislop/3.2.20/skills/antislop-human/SKILL.md`
- Responsive layout: `/Users/madina/.codex/plugins/cache/anti-slop/antislop/3.2.20/skills/antislop-layoutmobile/SKILL.md`

Resolve antislop's usage mode and visual direction before UI work, then run its Delivery Gate before delivery.
<!-- antislop:end -->
