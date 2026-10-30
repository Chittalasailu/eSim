import os
import sys

import pytest

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from chatbot import manual_search  # noqa: E402


@pytest.fixture(autouse=True)
def no_real_manual_index(tmp_path, monkeypatch):
    """Keep tests off the local Ollama and the user's ~/.esim index."""
    def no_ollama(texts):
        raise ConnectionError("tests do not call Ollama")

    monkeypatch.setattr(manual_search, "_embed", no_ollama)
    monkeypatch.setattr(manual_search, "index_path",
                        lambda: str(tmp_path / "manual_index.json"))
    monkeypatch.setattr(manual_search, "_index", None)
