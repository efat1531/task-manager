# Task Manager v2.0.0

A **complete visual redesign**. Task Manager moves to the flat, square
"blueprint" look — a slate-blue accent, hairline dividers, and the bundled
**Barlow** type family — and gains a notification center, in-window reminder
toasts, and a friendlier task list. Nothing about your data changes; every task,
schedule, and integration link carries straight over.

## ✨ What's new

- **Brand-new interface.** A cohesive light/dark theme built from a single set of
  design tokens: flat surfaces, crisp dividers, a slate-blue accent, and custom
  themed icons throughout. Dark mode was rebuilt to match.
- **Bundled Barlow font.** The app now ships and uses the Barlow / Barlow
  Condensed fonts, so it looks the same on every machine. If they can't load, it
  falls back cleanly to Segoe UI.
- **Notification center.** A bell in the header with an unread badge and a
  slide-in panel of recent alerts, plus a new **Notifications** tab for choosing
  which events notify you and how.
- **In-window reminder toasts.** Task reminders now also appear as a dismissible
  card in the corner of the window, mirroring the desktop notification.
- **Clearer task list.**
  - Priority now shows as a **coloured badge** (Urgent / High / Medium / Low).
  - Each row has a **checkbox** — tick it to complete or reopen a task in place.
  - A drag handle on every row makes manual reordering more discoverable.
- **Redesigned task editor.** Priority is now a **segmented control** instead of a
  dropdown, so all four levels are visible at a glance.
- **Refreshed integration tabs.** The Azure DevOps and Linear settings are laid
  out in "blueprint" panels, and Linear's exclude-labels now wrap as tidy chips.
- **Smoother busy indicator.** The footer's progress bar is replaced by a compact
  animated spinner that names the running sync.

## 🐛 Fixes

- **Manual reordering no longer makes a task briefly vanish.** Drag-to-reorder now
  runs its own drag so the table is never left with a missing row until the next
  refresh.
- **Linear remembers your team names.** Selected teams now display as
  "Engineering (ENG)" after a restart instead of a bare id.

## 📦 Install

- **Recommended:** download **`TaskManager-Setup.exe`** below and run it. It
  installs to your user profile (no administrator rights needed), creates
  shortcuts, and can be removed later from **Settings → Apps**.
- **Portable:** the standalone **`TaskManager.exe`** is still available if you
  prefer to run it without installing.

> Note: the installer and app are not code-signed yet, so Windows SmartScreen may
> show a warning on first run — choose **More info → Run anyway**.

**Full changelog** is appended below.
