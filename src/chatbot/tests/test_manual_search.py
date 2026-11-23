import os
import sys

import pytest

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from chatbot import chatbot_thread, manual_search  # noqa: E402

MANUAL = """<html><body>
<h2>Contents</h2><p>1 Introduction 2 Netlist generation</p>
<h2>Chapter 5 Schematic Creation</h2>
<h4>5.2.5 Netlist generation</h4>
<p>Click on the Generate netlist tool from the top toolbar.</p>
<p>Click on spice and check Default Format.</p>
<h4>5.1.5 Hotkeys</h4><p>W - Place wire</p>
<h2>References</h2><p>[1] KiCad documentation</p>
</body></html>"""

# Fake embeddings: one axis per topic, so cosine similarity is 1 for a
# matching topic and 0 otherwise.
TOPICS = ["netlist", "wire", "schematic"]


def fake_embed(texts):
    vectors = []
    for text in texts:
        vec = [1.0 if topic in text.lower() else 0.0 for topic in TOPICS]
        vectors.append(vec if any(vec) else [0.0, 0.0, 0.0])
    return vectors


@pytest.fixture
def manual(tmp_path, monkeypatch):
    manual_file = tmp_path / "eSim.html"
    manual_file.write_text(MANUAL, encoding="utf-8")
    monkeypatch.setattr(manual_search, "manual_path", lambda: str(manual_file))
    monkeypatch.setattr(manual_search, "index_path",
                        lambda: str(tmp_path / "cache" / "manual_index.json"))
    monkeypatch.setattr(manual_search, "_index", None)
    calls = []

    def counting_embed(texts):
        calls.append(list(texts))
        return fake_embed(texts)

    monkeypatch.setattr(manual_search, "_embed", counting_embed)
    return manual_file, calls


def test_manual_is_split_by_heading_without_contents_or_references():
    chunks = manual_search.split_manual(MANUAL)

    # A heading with no text of its own (Chapter 5) gives no chunk.
    assert [c["title"] for c in chunks] == ["5.2.5 Netlist generation", "5.1.5 Hotkeys"]
    assert "Generate netlist tool" in chunks[0]["text"]
    assert "Default Format" in chunks[0]["text"]


def test_long_sections_are_split_at_paragraphs():
    para = "x" * 700
    html = f"<h3>Long</h3><p>{para}</p><p>{para}</p><p>{para}</p>"

    chunks = manual_search.split_manual(html)

    assert len(chunks) == 3
    assert all(len(c["text"]) <= manual_search.MAX_CHUNK_CHARS for c in chunks)


def test_bundled_manual_parses_into_sections():
    with open(manual_search.manual_path(), encoding="utf-8") as f:
        chunks = manual_search.split_manual(f.read())

    titles = [c["title"] for c in chunks]
    assert len(chunks) > 50
    assert "5.2.5 Netlist generation" in titles
    assert "Contents" not in titles


def test_search_returns_the_matching_section(manual):
    found = manual_search.search("how do I make a netlist")

    assert [c["title"] for c in found] == ["5.2.5 Netlist generation"]


def test_unrelated_question_finds_nothing(manual):
    assert manual_search.search("what is the capital of France") == []
    assert manual_search.manual_context("what is the capital of France") == ""


def test_index_is_cached_on_disk(manual, monkeypatch):
    _, calls = manual
    manual_search.search("netlist")
    monkeypatch.setattr(manual_search, "_index", None)

    manual_search.search("wire")

    documents_embedded = [c for c in calls if c[0].startswith("search_document")]
    assert len(documents_embedded) == 1


def test_index_is_rebuilt_when_the_manual_changes(manual):
    manual_file, calls = manual
    manual_search.search("netlist")

    manual_file.write_text(MANUAL.replace("W - Place wire", "W - Wire"),
                           encoding="utf-8")
    manual_search.search("wire")

    documents_embedded = [c for c in calls if c[0].startswith("search_document")]
    assert len(documents_embedded) == 2


def test_context_names_the_manual_and_its_sections(manual):
    context = manual_search.manual_context("which hotkey places a wire")

    assert "eSim user manual" in context
    assert "## 5.1.5 Hotkeys" in context
    assert "W - Place wire" in context


def test_section_titles_are_listed_once_best_first():
    found = [{"title": "B"}, {"title": "A"}, {"title": "B"}]

    assert manual_search.section_titles(found) == ["B", "A"]


def test_context_is_empty_when_ollama_fails(manual, monkeypatch):
    def broken(texts):
        raise ConnectionError("Ollama is not running")

    monkeypatch.setattr(manual_search, "_embed", broken)

    assert manual_search.manual_context("netlist") == ""
    assert manual_search.relevant_sections("netlist") == []


class _Chat:
    def __init__(self):
        self.kwargs = None

    def __call__(self, **kwargs):
        self.kwargs = kwargs
        return iter([{"message": {"content": "answer"}}])


FOUND = [
    {"title": "5.2.5 Netlist generation", "text": "Click Generate netlist.", "score": 0.8},
    {"title": "5.2.5 Netlist generation", "text": "Check Default Format.", "score": 0.7},
    {"title": "5.1.5 Hotkeys", "text": "W - Place wire", "score": 0.66},
]


@pytest.fixture
def worker_env(monkeypatch):
    chat = _Chat()
    monkeypatch.setattr(chatbot_thread.ollama, "chat", chat)
    monkeypatch.setattr(chatbot_thread, "_ensure_ollama_running", lambda w: True)
    questions = []

    def sections(question):
        questions.append(question)
        return FOUND

    monkeypatch.setattr(chatbot_thread.manual_search, "relevant_sections", sections)
    return chat, questions


def test_worker_adds_manual_sections_before_the_rules(worker_env):
    chat, questions = worker_env
    worker = chatbot_thread.OllamaWorker(
        ["User: hi", "Bot: hello", "User: how do I make a netlist?"])

    worker.run()

    system = chat.kwargs["messages"][0]["content"]
    assert questions == ["how do I make a netlist?"]
    assert system.startswith("Relevant sections of the eSim user manual")
    assert "## 5.1.5 Hotkeys\nW - Place wire" in system
    assert system.endswith(chatbot_thread._SYSTEM_PROMPT)
    assert chat.kwargs["options"]["num_ctx"] >= chatbot_thread._MANUAL_NUM_CTX


def test_worker_does_not_search_for_pasted_netlists(worker_env):
    chat, questions = worker_env
    netlist = "Analyse this NgSpice netlist for me.\n" + "R1 1 0 1k\n" * 200
    worker = chatbot_thread.OllamaWorker([f"User: {netlist}"])

    worker.run()

    assert questions == []
    assert chat.kwargs["messages"][0]["content"] == chatbot_thread._SYSTEM_PROMPT


def test_worker_keeps_the_normal_window_without_manual_sections(worker_env, monkeypatch):
    chat, _ = worker_env
    monkeypatch.setattr(chatbot_thread.manual_search, "relevant_sections", lambda q: [])
    worker = chatbot_thread.OllamaWorker(["User: what is the capital of France?"])

    worker.run()

    assert chat.kwargs["messages"][0]["content"] == chatbot_thread._SYSTEM_PROMPT
    assert chat.kwargs["options"]["num_ctx"] == int(
        chatbot_thread.CONFIG["context_window"]["text_num_ctx"])


def test_worker_reports_the_sections_it_used(worker_env):
    worker = chatbot_thread.OllamaWorker(["User: how do I make a netlist?"])
    sent = []
    worker.sources_signal.connect(sent.append)

    worker.run()

    assert sent == [["5.2.5 Netlist generation", "5.1.5 Hotkeys"]]


def test_worker_reports_no_sections_without_a_match(worker_env, monkeypatch):
    monkeypatch.setattr(chatbot_thread.manual_search, "relevant_sections", lambda q: [])
    worker = chatbot_thread.OllamaWorker(["User: what is the capital of France?"])
    sent = []
    worker.sources_signal.connect(sent.append)

    worker.run()

    assert sent == []
