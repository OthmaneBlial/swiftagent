"""Reference acceptance implementation for the Northstar demo verifier."""


def release_badge(version: str, checks_passed: bool) -> str:
    """Return a normalized version and an explicit release state."""
    normalized = version.strip()
    if not normalized:
        normalized = "unversioned"
    elif not normalized.startswith("v"):
        normalized = f"v{normalized}"
    state = "READY" if checks_passed else "BLOCKED"
    return f"{normalized} · {state}"
