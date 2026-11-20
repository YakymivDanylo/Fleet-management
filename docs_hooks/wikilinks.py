"""MkDocs hook: Obsidian ``[[wikilinks]]`` -> relative Markdown links (one source for both tools).

Supported forms (as Obsidian writes them): ``[[name]]``, ``[[name|alias]]``, ``[[name#heading]]``,
``[[name#heading|alias]]`` and the table-safe ``[[name\\|alias]]``. ``name`` is a file stem anywhere
under ``docs/``; stems must be unique, otherwise the link is ambiguous. Fenced code blocks and
inline code are left untouched, so shell ``[[ ... ]]`` in runbooks is not rewritten.

An unresolved or ambiguous wikilink is logged as a WARNING, so ``mkdocs build --strict`` fails on it
exactly like on a dead Markdown link.
"""

import logging
import posixpath
import re

from mkdocs.structure.files import Files
from mkdocs.structure.pages import Page

log = logging.getLogger("mkdocs.hooks.wikilinks")

WIKILINK_RE = re.compile(r"\[\[([^\]|#\\]+)(#[^\]|\\]+)?(?:\\?\|([^\]]+))?\]\]")
FENCE_RE = re.compile(r"^(\s*)(```|~~~)")
INLINE_CODE_RE = re.compile(r"(`+)(.+?)\1")

_index: dict[str, list[str]] = {}


def on_files(files: Files, config) -> Files:
    _index.clear()
    for f in files.documentation_pages():
        stem = posixpath.splitext(posixpath.basename(f.src_uri))[0].lower()
        _index.setdefault(stem, []).append(f.src_uri)
    return files


def _slug(heading: str) -> str:
    # Same rule as pymdownx.slugs.slugify(case=lower) for the headings used in this knowledge base.
    text = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return text.replace(" ", "-")


def _replace(match: re.Match, page: Page) -> str:
    name, anchor, alias = match.group(1).strip(), match.group(2), match.group(3)
    targets = _index.get(name.lower(), [])
    if len(targets) != 1:
        problem = "not found" if not targets else f"ambiguous ({', '.join(targets)})"
        log.warning("Wikilink [[%s]] in '%s': %s", name, page.file.src_uri, problem)
        return match.group(0)
    base = posixpath.dirname(page.file.src_uri)
    href = posixpath.relpath(targets[0], base or ".")
    if anchor:
        href += "#" + _slug(anchor[1:])
    text = (alias or name).strip()
    return f"[{text}]({href})"


def _convert_line(line: str, page: Page) -> str:
    parts, last = [], 0
    for code in INLINE_CODE_RE.finditer(line):
        parts.append(WIKILINK_RE.sub(lambda m: _replace(m, page), line[last : code.start()]))
        parts.append(code.group(0))
        last = code.end()
    parts.append(WIKILINK_RE.sub(lambda m: _replace(m, page), line[last:]))
    return "".join(parts)


def on_page_markdown(markdown: str, page: Page, config, files: Files) -> str:
    out, fence = [], None
    for line in markdown.split("\n"):
        m = FENCE_RE.match(line)
        if m:
            fence = None if fence == m.group(2) else (fence or m.group(2))
            out.append(line)
            continue
        out.append(line if fence else _convert_line(line, page))
    return "\n".join(out)
