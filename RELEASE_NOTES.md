# Task Manager v1.3.0

In-app updates arrive: Task Manager can now check GitHub for a newer version and
update itself. Plus a fix for overlapping titles in the task list.

## ✨ New features

- **Built-in updater.** Task Manager now checks GitHub for a newer release in the
  background on startup and offers to install it, showing the new version's
  release notes first. You can also check any time from **Help → Check for
  updates…**, and an **About** entry shows the current version. On the packaged
  Windows app the update downloads and installs itself, then relaunches; elsewhere
  it opens the releases page. After an update, a one-time "What's new" popup
  summarises the changes.

## 🐛 Bug fixes

- **Task titles no longer overlap in the list.** When a row switched to a linked
  title (e.g. a PR or Linear task whose text contains a URL), the new title could
  be painted on top of a stale one, so two titles appeared jumbled together — most
  visible after enabling the Linear integration next to Azure PR tasks. Each task
  now renders cleanly on its own row.

## 📦 Install

Download `TaskManager.exe` below (Windows). The build is produced and tested in
CI for this tag. Once you're on v1.3.0, future updates can be installed from
within the app.

**Full changelog** is appended below.
