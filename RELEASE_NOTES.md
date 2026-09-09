# Task Manager v2.1.1

A small build maintenance release. No feature or data changes — every task,
schedule, and integration link carries straight over.

## 🔧 Changes

- **Portable `TaskManager.exe` is no longer UPX-packed.** Packed executables trip
  extra antivirus, SmartScreen, and Smart App Control heuristics, which was blocking
  v2.1.0 on some machines. The exe is a little larger now but trips fewer flags on
  first run.

## 📦 Install

- Download **`TaskManager.exe`** below and just run it — no install, no admin rights.
  Your data lives per-user at `%LOCALAPPDATA%\TaskManager\tasks.db`, and the app keeps
  itself up to date.

> Note: the app is not code-signed, so Windows SmartScreen (or Smart App Control) may
> still warn on first run — choose **More info → Run anyway**. Under Smart App Control
> a fresh unsigned build can be blocked outright until it earns cloud reputation.

**Full changelog** is appended below.
