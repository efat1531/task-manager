# Task Manager v1.1.0

Sharper PR-review task handling, plus two reordering/sorting fixes for lists
that contain recurring tasks.

## ✨ New features

- **Review tasks auto-complete from your Azure DevOps vote.** Once you cast any
  review vote on a pull request — Approve, Approve with suggestions, Wait for
  author, or Reject — its "Review PR" task is marked complete automatically. If a
  new commit resets your vote (Azure's "reset votes on push" policy), the task
  reopens so the PR gets another look. Works for both required and optional
  reviews. The sync status line now reports how many tasks were completed and
  reopened.

## 🐛 Bug fixes

- **Drag-and-drop reordering works again when recurring tasks are shown.**
  Previously, having any recurring occurrence in the list (e.g. a daily meeting)
  silently disabled row reordering for every task. Occurrence rows are now
  skipped during a drop instead of aborting the whole reorder.
- **"Sort by Priority" no longer strands recurring occurrences at the bottom.**
  Tasks and recurring occurrences are now merged and sorted together by the
  chosen key, so a Medium meeting sorts among the Medium tasks instead of
  producing an out-of-order Medium → Low → Medium list. Tasks with unresolved PR
  comments stay pinned to the top.

## 📦 Install

Download `TaskManager.exe` below (Windows). The build is produced and tested in
CI for this tag.

**Full changelog** is appended below.
