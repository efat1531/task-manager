# Task Manager v2.1.2

A bug-fix release. No data changes — every task, schedule, and integration link
carries straight over.

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
