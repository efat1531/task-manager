# Task Manager v2.0.1

A maintenance release that fixes in-app auto-update for builds installed with
**`TaskManager-Setup.exe`**. Your data is untouched — every task, schedule, and
integration link carries straight over.

## 🐛 Fixes

- **Auto-update now works when the app was installed via the installer.** Installed
  builds now update by re-running the installer silently instead of trying to swap
  the exe in place. This keeps the Add/Remove Programs version and uninstaller in
  sync, and — for the first time — updates installs under **`C:\Program Files`**
  (with a single administrator prompt when needed). Per-user installs still update
  with no prompt, and the portable **`TaskManager.exe`** keeps its in-place update.
- **Declining the administrator prompt no longer loses your app.** If an elevated
  update is cancelled, Task Manager reports it and stays open on the current
  version instead of closing.

> **Upgrading from an older Program Files install:** because the fix ships *inside*
> this release, a build already installed under `C:\Program Files` needs to be
> updated **once manually** — download and run `TaskManager-Setup.exe` below. Every
> update after that installs automatically. Per-user installs upgrade to this
> version automatically.

## 📦 Install

- **Recommended:** download **`TaskManager-Setup.exe`** below and run it. It
  installs to your user profile (no administrator rights needed), creates
  shortcuts, and can be removed later from **Settings → Apps**.
- **Portable:** the standalone **`TaskManager.exe`** is still available if you
  prefer to run it without installing.

> Note: the installer and app are not code-signed yet, so Windows SmartScreen may
> show a warning on first run — choose **More info → Run anyway**.

**Full changelog** is appended below.
