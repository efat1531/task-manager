# Task Manager v1.4.0

A **Reset** option to wipe the database and a set of Azure PR improvements:
PR tasks now always get a clickable link, name their repository in the title,
and existing tasks are backfilled with their link on the next sync.

## ✨ New features

- **Reset all data.** A new **Data → Reset (clear all data)…** menu entry wipes
  every task, schedule, recurring override, and synced integration link, and
  resets id counters. It is guarded by a confirmation dialog and cannot be
  undone.
- **Repository name in PR titles.** Azure PR tasks now read
  *"Your DenticonCore PR #59854: …"* / *"Review DenticonCore PR #59854: …"* so
  PRs from different repositories are distinguishable at a glance.

## 🐛 Bug fixes

- **Azure PR tasks always get a clickable link.** Azure's pull-request list
  endpoint often omits the PR's web URL, so some PR tasks had no `↗` link in
  their row (unlike Linear tasks). The link is now reconstructed from the
  organization, project, repository, and PR id when the API leaves it out.
- **Existing PR tasks are backfilled.** Tasks created before the link fix gain
  their `↗` link automatically on the next sync — the link is only added when a
  task has none, so any description you have edited is left untouched.

## 📦 Install

Download `TaskManager.exe` below (Windows). The build is produced and tested in
CI for this tag. If you're already on v1.3.0 or later, this update can be
installed from within the app (**Help → Check for updates…**).

**Full changelog** is appended below.
