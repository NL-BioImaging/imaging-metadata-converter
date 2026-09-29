---
name: coding-preferences
description: >
  General coding-style and workflow preferences learned from working with
  this user, applicable to any project - not specific to this repo.
---

# Coding preferences

Things learned working with this user, generically applicable beyond this
project.

## Code style

- **Avoid `continue` in loops.** Restructure the loop body so each branch's
  condition is fully self-contained (combine the guard into the `if` that
  does the work) and let the loop fall through naturally when nothing
  matches, instead of an early `continue` to skip to the next iteration.
- **No single-letter variable names**, comprehension variables included:
  `field for field in fields`, not `f for f in fields`.
- **No comments unless the WHY is genuinely non-obvious.** A hidden
  constraint, a workaround for a specific bug, something that would
  surprise a careful reader - yes. Restating what the code already says
  clearly through naming - no.
- **No premature abstraction.** Don't build for hypothetical future cases.
  Three similar lines beat an early helper function extracted for one
  current use.

## Testing

- **Prefer test classes (`unittest.TestCase`) over ad-hoc scripts** for
  anything meant to keep passing, not just a one-off check during
  development. Ad-hoc verification scripts (run once via the shell, not
  committed) are fine and expected *during* development - promote the
  useful ones into the real test suite once the behavior is settled.
- **Write a synthetic test before trusting a new capability on real data.**
  When adding a genuinely new code path (not just new data), construct a
  minimal example that exercises exactly that path, inspect the output by
  hand, and only then apply it to production data. This caught real bugs
  before they touched anything real, more than once.
- **When "no data should be lost" is a requirement, write an actual test
  for it** - don't just eyeball a sample of the output. A multiset
  comparison of every leaf value in the input against every leaf value in
  the output (regardless of where each value ended up) catches silent
  overwrites that spot-checking a few fields will miss.
- **Verify a fix by tracing the actual mechanism, not by re-guessing.**
  When output looks wrong, instrument the real code path (e.g. wrap the
  function that writes values and log every call) rather than guessing at
  which rule fired from the symptom alone.

## Working style

- **Don't guess at ambiguous scope - ask.** When a fix could reasonably go
  several different ways (revert everything vs. revert part vs. keep it),
  present the concrete tradeoff and ask, rather than picking one and
  presenting it as done. Silently re-guessing after a correction reads
  worse than asking would have.
- **When a general principle is stated, look for every existing place it
  already applies**, not just the one instance that prompted it - a
  pattern flagged once usually recurs.
- **State assumptions before implementing**, especially about what a
  vendor-specific field means or how a data shape should be represented -
  it's cheaper to correct a stated assumption than a finished
  implementation built on a wrong one.
- **Never silently drop data.** When consolidating or renaming fields into
  a schema, anything that doesn't have an established target should stay
  reachable at its original location, not disappear.

## Carrying work across sessions

- Record the current task, its plan and how far it got under "In progress"
  in `notes/todo_known_issues.md` before editing code, and keep it updated.
  Clear it once the task is done.
- On "continue" with no other context, read that section first and resume
  from it.
