# Task Manager v2.2.0

Adds a **GitHub** integration alongside Azure DevOps and Linear, plus a new footer sync
indicator. No data changes — every task, schedule, and integration link carries
straight over.

## ✨ New

- **GitHub tab.** Turn your GitHub pull requests into tasks, just like the Azure tab:
  enable **PRs I'm asked to review** and/or **PRs I opened**, pick a priority for each,
  optionally restrict to one organization, and sync on demand or on a background
  auto-poll. The access token lives only in the OS keyring.
- **Same lifecycle as Azure.** Exactly one task per PR (never re-created if you delete
  it); a task auto-completes when its PR is merged, closed, or you're no longer asked to
  review it. It reopens if your review is re-requested, but never if you completed it
  yourself. Your own PRs are pinned to the top while review threads are unresolved and
  parked at Low while changes are requested.
- **GitHub notifications.** New toggles in the Notifications tab for review requests,
  changes requested, and new comments on your PRs.
- **Footer sync ring.** The "Next … sync in mm:ss" text is replaced by a small ring in
  the footer. It spins while any integration (Azure, GitHub, Linear) is syncing — at
  least two full turns, so even a quick sync is visible — and otherwise shows an arc for
  the time left until the next auto-sync. Hover it for a floating card listing each
  integration's time to its next sync (or "Syncing…"); the card fades away shortly after
  the mouse leaves.
- **Minimal-permission token guidance.** Each integration tab (and the README) now says
  exactly which token or key permissions to create and nothing more: a fine-grained
  GitHub token with **Pull requests: Read-only**, an Azure DevOps token with **Code →
  Read**, and a Linear API key with **Read** only.

## 🛡️ Safeguards

- If GitHub unexpectedly returns **no** pull requests while five or more tasks would be
  auto-completed (for example the token lost access to an organization), those tasks are
  left open and the tab tells you why, instead of completing them all.
- A sync that would exceed 500 pull requests fails with a clear message rather than
  silently completing the tasks beyond the cap.
- The GitHub client retries rate limits and transient server errors (5xx), and reports a
  rate limit as a rate limit rather than as an authentication failure. A token pasted
  with stray spaces or control characters is rejected up front.

## 🐞 Fixes

- Removing the **Azure** integration no longer forgets Linear's synced-issue links
  (it used to clear every integration's links). Each integration now clears only its
  own.

## 📦 Install

- Download **`TaskManager.exe`** below and just run it — no install, no admin rights.
  Your data lives per-user at `%LOCALAPPDATA%\TaskManager\tasks.db`, and the app keeps
  itself up to date.

> Note: the app is not code-signed, so Windows SmartScreen (or Smart App Control) may
> still warn on first run — choose **More info → Run anyway**. Under Smart App Control
> a fresh unsigned build can be blocked outright until it earns cloud reputation.

**Full changelog** is appended below.
