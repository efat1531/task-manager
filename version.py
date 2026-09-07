"""Single source of truth for the application version.

``APP_VERSION`` is the version baked into a build. The auto-updater compares it
against the latest GitHub release to decide whether an update exists, and the
"what's new" popup uses it to detect that the app has just been updated. Bump it
in the same commit that updates ``RELEASE_NOTES.md`` for a release, and tag that
commit ``v<APP_VERSION>`` (the release workflow asserts the two match).
"""
from __future__ import annotations

APP_VERSION = "1.5.0"

#: Human-facing metadata surfaced in the Help → About box. Kept here so the UI
#: imports them from the same single source as the version.
APP_AUTHOR = "Efat Sikder"
APP_DESCRIPTION = "A personal task manager with Linear & Azure DevOps integration."
APP_COPYRIGHT = "© 2026 Efat Sikder"
APP_CONTACT_EMAIL = "efat1531@gmail.com"

#: ``owner/repo`` used to build the GitHub Releases API and download URLs.
GITHUB_REPO = "efat1531/task-manager"

#: Human-facing releases page, offered as a fallback when an in-app install
#: cannot run (e.g. a non-frozen dev run, or a failed download).
RELEASES_PAGE_URL = f"https://github.com/{GITHUB_REPO}/releases/latest"
