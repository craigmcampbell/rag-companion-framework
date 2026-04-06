---
name: changelog-updater
description: Append a changelog entry to docs/CHANGELOG.md using the current date or an explicit version
---

# Changelog Updater

When updating the changelog, follow these rules:

## File target
- Target file: `docs/CHANGELOG.md` (under the repo’s `docs/` folder, not the repository root)

## Placement
- By default, append under `## YYYY-MM-DD` using the current date
- Use today's date in `YYYY-MM-DD` format based on the local development environment
- If a version is explicitly requested, use `## <version> - <date>`
- If the heading does not exist, create it near the top of the file

## Categories
Use these when helpful:
- Added
- Changed
- Fixed
- Removed

### Classification rules (required)
- Classify each change before writing bullets:
  - Added: introduces a new capability, endpoint, task, or workflow
  - Changed: modifies runtime behavior, output, prompts, logging semantics, or defaults
  - Fixed: resolves incorrect behavior, crash, or type/lint/schema/runtime error
  - Removed: removes capability or behavior
- If any runtime behavior changed, include at least one `Added` or `Changed` bullet.
- Do not log only tooling/type/schema fixes when behavior changes are present.

## Writing style
- One bullet per meaningful change
- Focus on impact, not internal implementation
- Keep bullets under 120 characters when possible
- Avoid duplicates
- Preserve markdown formatting

## Workflow
1. Inspect changed files and diffs (not filenames only)
2. For each change, write a one-line impact note ("what changed for users/operators")
3. Read existing `docs/CHANGELOG.md`
4. Choose the target heading based on date or version
5. Create the heading if needed
6. Add concise entries under the appropriate section
7. Preserve existing house style
8. Final checks:
   - no duplicate date/version headings
   - no duplicate bullets
   - behavior changes represented in `Added`/`Changed` (not only `Fixed`)
