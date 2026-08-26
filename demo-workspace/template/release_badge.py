"""Formatting for the fictional Northstar release desk."""


def release_badge(version: str, checks_passed: bool) -> str:
    """Return a compact version and release-state label."""
    state = "ready" if checks_passed else "blocked"
    return f"{version} {state}"
