"""Bounded Markdown chunks preserving headings and exact source text.

No domain-specific heading names or numbering are required. Plain text works too.
"""
from __future__ import annotations
import re
from dataclasses import dataclass

CHUNKER_VERSION = 'markdown-v2'
_HEADING = re.compile(r'^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$')


@dataclass
class Chunk:
    id: str
    section: str
    text: str


def chunk_policy(markdown: str, max_chars: int = 3000, overlap: int = 300) -> list[Chunk]:
    if max_chars <= 0 or not 0 <= overlap < max_chars:
        raise ValueError('Expected 0 <= overlap < max_chars')
    sections, body, headings = [], [], []
    in_fence = False
    def flush():
        text = '\n'.join(body).strip()
        if text:
            sections.append((' / '.join(title for _, title in headings) or 'Document', text))
        body.clear()
    for line in markdown.splitlines():
        if line.lstrip().startswith(('```', '~~~')):
            in_fence = not in_fence
        heading = _HEADING.match(line) if not in_fence else None
        if heading:
            flush()
            level, title = len(heading[1]), heading[2]
            headings[:] = [(n,t) for n,t in headings if n < level]
            headings.append((level, title))
        else:
            body.append(line)
    flush()
    chunks = []
    for number, (title, text) in enumerate(sections, 1):
        start, part = 0, 1
        while start < len(text):
            end = min(start + max_chars, len(text))
            if end < len(text):
                boundary = text.rfind('\n', start + max_chars // 2, end)
                if boundary > start:
                    end = boundary
            chunks.append(Chunk(id=f'sec{number}' + (f'-part{part}' if len(text) > max_chars else ''),
                                section=title, text=text[start:end]))
            if end == len(text):
                break
            start = max(start + 1, end - overlap)
            part += 1
    return chunks


def load_and_chunk(policy_file) -> list[Chunk]:
    return chunk_policy(policy_file.read_text(encoding='utf-8'))
