# Task Manager v2.2.0

Adds a **GitHub** integration alongside Azure DevOps and Linear. No data changes —
every task, schedule, and integration link carries straight over.

## ✨ New

- **GitHub tab.** Turn your GitHub pull requests into tasks, just like the Azure tab:
  enable **PRs I'm asked to review** and/or **PRs I opened**, pick a priority for each,
  optionally restrict to one organization, and sync on demand or on a background
  auto-poll. The access token lives only in the OS keyring.
- **Same lifecycle as Azure.** Exactly one task per PR (never re-created if you delete
  it); a task auto-completes when its PR is merged, closed, or you're no longer asked to
  review it, and reopens if your review is re-requested. Your own PRs are pinned as
  Urgent while review threads are unresolved and parked at Low while changes are
  requested.
- **GitHub notifications.** New toggles in the Notifications tab for review requests,
  changes requested, and new comments on your PRs.

## 🐞 Fixes

- Removing the **Azure** integration no longer forgets Linear's synced-issue links
  (it used to clear every integration's links).

## 🐞 Fixes

- **Desktop notifications now actually appear on Windows.** They previously used the
  legacy tray "balloon tip", which Windows 10/11 routinely suppress. Notifications now
  use native Windows toasts that land reliably in the Action Center, and the
  Notifications tab's **Send a test notification** button now reports honest
  success/failure instead of always claiming it sent. (Other platforms keep the
  previous notifier.)
- **The "Completed" filter now shows only what you completed that day.** Selecting
  **Status → Completed** used to list every completed task ever, including deadline-less
  ones. It now shows only tasks marked complete on the selected day (defaults to today),
  and follows the day picker so you can look back at any date. Older tasks completed
  before this update have no recorded completion date and appear under **All**.

## 📦 Install

- Download **`TaskManager.exe`** below and just run it — no install, no admin rights.
  Your data lives per-user at `%LOCALAPPDATA%\TaskManager\tasks.db`, and the app keeps
  itself up to date.

> Note: the app is not code-signed, so Windows SmartScreen (or Smart App Control) may
> still warn on first run — choose **More info → Run anyway**. Under Smart App Control
> a fresh unsigned build can be blocked outright until it earns cloud reputation.

**Full changelog** is appended below.
