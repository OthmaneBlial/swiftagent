from __future__ import annotations

import unittest

from release_badge import release_badge


class ReleaseBadgeTests(unittest.TestCase):
    def test_normalizes_version_and_ready_state(self) -> None:
        self.assertEqual(release_badge(" 1.4.0 ", True), "v1.4.0 · READY")

    def test_does_not_duplicate_existing_version_prefix(self) -> None:
        self.assertEqual(release_badge("v2.0.0", True), "v2.0.0 · READY")

    def test_uses_an_honest_fallback_for_blank_version(self) -> None:
        self.assertEqual(release_badge("   ", False), "unversioned · BLOCKED")


if __name__ == "__main__":
    unittest.main()
