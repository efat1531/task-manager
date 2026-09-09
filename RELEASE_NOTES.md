# Task Manager v2.1.0

This release makes the app **actually notify you** — a real notification center with
desktop alerts, a working bell menu, and settings that persist — and simplifies
distribution to a single **portable `TaskManager.exe`**. Your data is untouched:
every task, schedule, and integration link carries straight over.

## ✨ New — Notification center

- **Desktop notifications, on an ongoing basis.** Reminders for **due-today** and
  **overdue** tasks now fire beyond startup (re-checked periodically, de-duplicated so
  the same task won't nag you twice a day). Syncs also alert you to **Azure PR events**
  (assigned for review, a new comment on your PR, changes requested) and **Linear
  issues** that become tasks.
- **The bell menu is real now.** The header bell shows an actual, persisted feed with
  an unread badge; **Mark all read** sticks across restarts.
- **A Notifications settings tab that works.** A master switch, per-source toggles,
  quiet hours, and a sound preference all **persist** and **gate** what gets delivered,
  and **Send a test notification** fires a real desktop toast.

## 🔧 Changes

- **Distribution is now the portable `TaskManager.exe` only** — the
  `TaskManager-Setup.exe` installer has been retired. Builds already installed via the
  old installer keep auto-updating automatically (they swap the exe in place).

## 📦 Install

- Download **`TaskManager.exe`** below and just run it — no install, no admin rights.
  Your data lives per-user at `%LOCALAPPDATA%\TaskManager\tasks.db`, and the app keeps
  itself up to date.

> Note: the app is not code-signed, so Windows SmartScreen (or Smart App Control) may
> warn on first run — choose **More info → Run anyway**.

**Full changelog** is appended below.
