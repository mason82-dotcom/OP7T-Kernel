"""Prevent broken local documentation links and repeated Markdown headings.

External URLs and generated anchors are intentionally not fetched by CI.
Fenced code blocks are excluded.
"""
import re
import unittest
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"\]\(([^)]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")


def markdown_files():
    return (
        [ROOT / "README.md"]
        + sorted((ROOT / "docs").glob("*.md"))
        + sorted((ROOT / "patches").glob("*.md"))
    )


def readable_lines(path):
    in_fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            yield line


class DocumentationIntegrityTest(unittest.TestCase):
    def test_all_local_links_resolve(self):
        for path in markdown_files():
            with self.subTest(document=path.relative_to(ROOT)):
                for line in readable_lines(path):
                    for match in LINK.finditer(line):
                        destination = match.group(1).split("#", 1)[0].strip()
                        if not destination or destination.startswith(
                            ("https://", "http://", "mailto:", "//")
                        ):
                            continue
                        destination = unquote(destination)
                        resolved = (path.parent / destination).resolve()
                        self.assertTrue(
                            resolved.is_relative_to(ROOT),
                            f"{path.relative_to(ROOT)}: link escapes repository: {destination}",
                        )
                        self.assertTrue(
                            resolved.exists(),
                            f"{path.relative_to(ROOT)}: broken link: {destination}",
                        )

    def test_headings_are_unique_per_document(self):
        for path in markdown_files():
            seen = set()
            for line in readable_lines(path):
                match = HEADING.match(line)
                if not match:
                    continue
                heading = match.group(1).strip().casefold()
                self.assertNotIn(
                    heading, seen,
                    f"{path.relative_to(ROOT)}: repeated heading: {heading}",
                )
                seen.add(heading)


if __name__ == "__main__":
    unittest.main()
