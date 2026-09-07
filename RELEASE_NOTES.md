# Task Manager v1.5.1

A reliability fix for **in-app updates**. Previous versions could download an
update, relaunch, and quietly come back up on the *old* version — this release
fixes that, and makes the download feel less like it's stuck.

## 🐛 Fixes

- **In-app updates now actually apply.** The updater used to overwrite the running
  program in place, which Windows blocks while the app's launcher is still shutting
  down — so the swap silently failed and the app reopened on the previous version.
  It now swaps the executable the reliable way (renaming the old one aside first)
  and only relaunches once the new version is in place.
- **Download no longer looks frozen at 0%.** While connecting to the download the
  dialog now shows a moving **"Connecting…"** bar, then switches to a real
  percentage as soon as data starts arriving, instead of sitting at 0%.

## ⚠️ One-time manual update

Because the broken updater is baked into builds up to and including **v1.5.0**,
updating *from* one of those builds may still land you back on the old version. To
get onto the fixed updater, install **v1.5.1 once by hand**:

- Download **`TaskManager-Setup.exe`** below and run it (or the portable
  **`TaskManager.exe`**), over your existing install.

From **v1.5.1 onward, Help → Check for updates… works normally.**

## 📦 Install

- **Recommended:** download **`TaskManager-Setup.exe`** below and run it. It
  installs to your user profile (no administrator rights needed), creates
  shortcuts, and can be removed later from **Settings → Apps**.
- **Portable:** the standalone **`TaskManager.exe`** is still available if you
  prefer to run it without installing.

> Note: the installer and app are not code-signed yet, so Windows SmartScreen may
> show a warning on first run — choose **More info → Run anyway**.

**Full changelog** is appended below.
