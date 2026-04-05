---
name: changelog-updater
description: Append a changelog entry to CHANGELOG.md using the current date or an explicit version
---

# Changelog Updater

When updating `CHANGELOG.md`, follow these rules:

## File target
- Target file: `CHANGELOG.md`

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

## Writing style
- One bullet per meaningful change
- Focus on impact, not internal implementation
- Keep bullets under 120 characters when possible
- Avoid duplicates
- Preserve markdown formatting

## Workflow
1. Inspect changed files
2. Read existing `CHANGELOG.md`
3. Choose the target heading based on date or version
4. Create the heading if needed
5. Add concise entries under the appropriate section
6. Preserve existing house style