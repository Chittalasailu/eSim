"""Look up the bundled eSim user manual for the AI Assistant.

The manual (library/browser/User-Manual/eSim.html) is split into sections,
each section is embedded once with the local embedding model, and the vectors
are cached in ~/.esim/ai_assistant/manual_index.json. A question is embedded
the same way and the closest sections are added to the model's prompt.

Everything runs through Ollama, like the rest of the assistant; no extra
Python packages are needed.
"""

import hashlib
import json
import math
import os
import re
import threading
from html.parser import HTMLParser

import ollama

from configuration import paths

EMBED_MODEL = "nomic-embed-text"

# Cosine similarity a section needs to count as relevant. eSim questions
# score 0.69-0.84 against their section with nomic-embed-text; unrelated
# questions ("capital of France", "sort a list in Python") stay below 0.61.
MIN_SCORE = 0.65
MAX_SECTIONS = 3
MAX_CHUNK_CHARS = 1200

# Sections that are lists of headings or citations, not instructions.
_SKIPPED_SECTIONS = {"Contents", "References"}

_INDEX_VERSION = 1
_lock = threading.Lock()
_index = None


def manual_path():
    return paths.library_path("browser", "User-Manual", "eSim.html")


def index_path():
    return paths.esim_config_path("ai_assistant", "manual_index.json")


class _ManualParser(HTMLParser):
    """Collect (heading, text) pairs from the tex4ht-generated manual."""

    _HEADING = re.compile(r"h[1-4]")
    _BLOCKS = {"p", "br", "li", "tr", "div", "pre"}

    def __init__(self):
        super().__init__()
        self.sections = []
        self._title = None
        self._text = []
        self._heading = None
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip_depth += 1
        elif self._HEADING.fullmatch(tag):
            self._finish_section()
            self._heading = []
        elif tag in self._BLOCKS and self._heading is None:
            self._text.append("\n\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip_depth = max(0, self._skip_depth - 1)
        elif self._HEADING.fullmatch(tag) and self._heading is not None:
            self._title = " ".join(" ".join(self._heading).split())
            self._heading = None

    def handle_data(self, data):
        if self._skip_depth:
            return
        (self._heading if self._heading is not None else self._text).append(data)

    def close(self):
        super().close()
        self._finish_section()

    def _finish_section(self):
        text = re.sub(r"[ \t]+", " ", "".join(self._text))
        text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
        if self._title and text and self._title not in _SKIPPED_SECTIONS:
            self.sections.append((self._title, text))
        self._text = []


def split_manual(html):
    """Return the manual as a list of {"title", "text"} chunks."""
    parser = _ManualParser()
    parser.feed(html)
    parser.close()

    chunks = []
    for title, text in parser.sections:
        current = ""
        for para in (p.strip() for p in text.split("\n\n")):
            if not para:
                continue
            if current and len(current) + len(para) > MAX_CHUNK_CHARS:
                chunks.append({"title": title, "text": current})
                current = ""
            current = f"{current}\n\n{para}".strip()
        if current:
            chunks.append({"title": title, "text": current})
    return chunks


def _embed(texts):
    return ollama.embed(model=EMBED_MODEL, input=texts)["embeddings"]


def _build_index(html, digest):
    chunks = split_manual(html)
    # nomic-embed-text expects these task prefixes on documents and queries.
    vectors = _embed([f"search_document: {c['title']}\n{c['text']}" for c in chunks])
    for chunk, vector in zip(chunks, vectors):
        chunk["embedding"] = vector
    return {"version": _INDEX_VERSION, "model": EMBED_MODEL,
            "manual_sha256": digest, "chunks": chunks}


def _load_index():
    """Return the cached index, (re)building it when the manual changed."""
    global _index
    with _lock:
        with open(manual_path(), "rb") as f:
            raw = f.read()
        digest = hashlib.sha256(raw).hexdigest()
        if _index is not None and _index["manual_sha256"] == digest:
            return _index

        cached = None
        try:
            with open(index_path(), encoding="utf-8") as f:
                cached = json.load(f)
        except (OSError, ValueError):
            pass
        if (cached and cached.get("version") == _INDEX_VERSION
                and cached.get("model") == EMBED_MODEL
                and cached.get("manual_sha256") == digest):
            _index = cached
            return _index

        _index = _build_index(raw.decode("utf-8", errors="replace"), digest)
        os.makedirs(os.path.dirname(index_path()), exist_ok=True)
        paths.write_json_atomic(index_path(), _index, indent=None)
        return _index


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))
    return dot / norm if norm else 0.0


def search(question, limit=MAX_SECTIONS, min_score=MIN_SCORE):
    """Return up to `limit` manual chunks relevant to `question`, best first."""
    index = _load_index()
    query = _embed([f"search_query: {question}"])[0]
    scored = sorted(
        ((_cosine(query, c["embedding"]), c) for c in index["chunks"]),
        key=lambda item: item[0], reverse=True,
    )
    return [dict(title=c["title"], text=c["text"], score=s)
            for s, c in scored[:limit] if s >= min_score]


def manual_context(question):
    """Prompt text with the manual sections relevant to `question`, or ""."""
    try:
        found = search(question)
    except Exception as e:  # Ollama down, model missing, manual not shipped
        print(f"[MANUAL SEARCH] skipped: {e}")
        return ""
    if not found:
        return ""
    sections = "\n\n".join(f"## {c['title']}\n{c['text']}" for c in found)
    return (
        "Relevant sections of the eSim user manual are below. Base your answer "
        "on them when they cover the question, and do not contradict them.\n\n"
        f"{sections}"
    )
