# Task Manager v1.2.0

Linear issue syncing joins the Azure DevOps integration, a new footer countdown
shows when the next Azure sync will run, and two reordering/PR bugs are fixed.

## ✨ New features

- **Linear integration: turn your assigned issues into tasks.** Mirroring the
  Azure DevOps integration, Linear issues assigned to you now sync into tasks on
  their own "Linear" tab. Pick a team, map each workflow status to a task priority,
  and exclude issues by label. Tasks are de-duplicated, re-prioritised when an
  issue changes status, and auto-completed once an issue leaves the eligible set —
  all kept isolated from the Azure PR tasks. Add your Linear API key in the tab to
  get started.
- **See when the next Azure sync will run.** A footer status-bar label now counts
  down "Next Azure sync in mm:ss" and refreshes every second. It appears only
  while the Azure integration has active sources and the auto-poll is running, and
  hides itself when Azure is disabled — so you always know how long until tasks
  refresh, without guessing.
- **Copy-paste the source link straight from a task.** Synced Azure PR and Linear
  issue tasks now surface the full URL on its own labelled "Link:" line in the
  description.

## 🐛 Bug fixes

- **Drag a task from the bottom to the top in one motion.** Dropping a row above
  the first row was mis-read as "drop at the bottom" and silently did nothing,
  forcing you to move a task up one position at a time. Drops are now resolved by
  cursor position, so a bottom-to-top drag lands at the top in a single drag.
- **Voting on your own PR no longer creates a duplicate "Review PR" task.** When
  you cast a vote (e.g. "Wait for author") on a pull request you authored, Azure
  adds you to that PR's reviewer list, which previously spawned a spurious
  "Review PR" task alongside your existing "Your PR" task. Pull requests you
  authored are now excluded from the review list, so only the "Your PR" task
  remains.
- **Task titles no longer overlap in the list.** A row switching to a linked
  title (e.g. a PR or Linear task whose text contains a URL) could paint the new
  title on top of a stale one, so two titles appeared jumbled together. Each task
  now renders cleanly on its own row.

## 🛠 Reliability

- Credential storage now degrades gracefully if the OS keyring backend fails at a
  low level, instead of crashing on startup.

## 📦 Install

Download `TaskManager.exe` below (Windows). The build is produced and tested in
CI for this tag.

**Full changelog** is appended below.
