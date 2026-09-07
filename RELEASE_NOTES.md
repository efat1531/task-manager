# Task Manager v1.5.0

This release sharpens both integrations. Linear tasks now follow their tickets far
more faithfully, the Azure tab is clearer, and the app tells you at a glance when
it's talking to a service and when the next auto-sync will run.

## ✨ New features

- **Clearer integration tabs.** The former "Integrations" tab is now simply
  **Azure**, so it reads as a sibling to the **Linear** tab instead of a catch-all.
- **Live sync feedback.** A busy indicator in the status bar appears whenever an
  integration is contacting Azure or Linear (testing, syncing, or loading), so a
  background sync is no longer invisible.
- **Linear next-sync countdown.** The footer countdown now shows **both** the next
  Azure *and* the next Linear auto-sync when each integration is active.
- **Ticket-driven Linear priority.** A synced Linear task now takes its priority
  straight from the Linear ticket, so re-prioritising a ticket re-prioritises its
  task on the next sync.
- **Azure "waiting for author".** A PR that's waiting on its author is parked at
  low priority and unpinned, then restored once it's active again.
- **Richer About box** with version, author, contact, and project links.

## 🐛 Fixes

- **Linear tasks reopen correctly.** A task auto-completed because its ticket left
  the synced statuses **or** picked up an excluded label now **reopens** on the
  next sync once the ticket returns to a synced status or the label is removed —
  instead of staying stuck complete.

## 📦 Install

- **Recommended:** download **`TaskManager-Setup.exe`** below and run it. It
  installs to your user profile (no administrator rights needed), creates
  shortcuts, and can be removed later from **Settings → Apps**.
- **Portable:** the standalone **`TaskManager.exe`** is still available if you
  prefer to run it without installing.

If you're already on v1.4.0 or later, this update can also be installed from
within the app (**Help → Check for updates…**).

> Note: the installer and app are not code-signed yet, so Windows SmartScreen may
> show a warning on first run — choose **More info → Run anyway**.

**Full changelog** is appended below.
