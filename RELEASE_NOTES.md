# Task Manager v1.2.1

A patch release fixing a task-list rendering glitch introduced alongside the
v1.2.0 integrations.

## 🐛 Bug fixes

- **Task titles no longer overlap in the list.** When a row switched to a linked
  title (e.g. a PR or Linear task whose text contains a URL), the new title could
  be painted on top of a stale one, so two titles appeared jumbled together — most
  visible after enabling the Linear integration next to Azure PR tasks. Each task
  now renders cleanly on its own row. Linear and Azure PR items remain separate
  tasks in isolated namespaces; only their rendering was affected.

## 📦 Install

Download `TaskManager.exe` below (Windows). The build is produced and tested in
CI for this tag.

**Full changelog** is appended below.
