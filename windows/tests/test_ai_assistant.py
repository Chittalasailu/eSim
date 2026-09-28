"""The optional eSim AI Assistant on Windows.

The chat window's Python packages are bundled into the private interpreter
at build time; the Ollama runtime (1.5 GB) and the models are fetched at
install time by windows/install_ai_assistant.py when the user ticks the
installer task. Static checks read installer.iss / build-windows.ps1 /
deps-manifest.json as text; the helper runs with downloads and processes
replaced by fakes, so nothing here needs Windows.
"""

import hashlib
import json
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
WINDIR = os.path.dirname(HERE)
REPO = os.path.dirname(WINDIR)
sys.path.insert(0, WINDIR)
sys.path.insert(0, os.path.join(REPO, "src"))

import install_ai_assistant as helper  # noqa: E402
from chatbot.chatbot_thread import REQUIRED_MODELS  # noqa: E402


def _read(name):
    with open(os.path.join(WINDIR, name), encoding="utf-8") as fh:
        return fh.read()


def _iss_lines(section):
    out, inside = [], False
    for line in _read("installer.iss").splitlines():
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            inside = s.lower() == "[%s]" % section.lower()
        elif inside and s and not s.startswith(";"):
            out.append(s)
    # Join Inno's backslash line continuations into one entry per line.
    return re.sub(r"\\\s*\n\s*", " ", "\n".join(out)).splitlines()


# ── installer.iss ──────────────────────────────────────────────────────────

def test_assistant_is_an_opt_in_task():
    task = [l for l in _iss_lines("Tasks") if 'Name: "aiassistant"' in l]
    assert task, "installer.iss has no aiassistant task"
    assert "unchecked" in task[0], "a multi-GB download must be opt-in"


def test_task_runs_the_helper_with_bundled_python_as_the_user():
    run = [l for l in _iss_lines("Run") if "install_ai_assistant.py" in l]
    assert len(run) == 1
    entry = run[0]
    assert r'Filename: "{app}\python\python.exe"' in entry
    assert "Tasks: aiassistant" in entry
    # Ollama installs per user; an elevated run would put it in the admin's
    # profile, not the user's.
    assert "runasoriginaluser" in entry
    assert "waituntilterminated" in entry


def test_helper_runs_before_eSim_is_offered_for_launch():
    lines = _iss_lines("Run")
    helper_at = next(i for i, l in enumerate(lines) if "install_ai_assistant.py" in l)
    launch_at = next(i for i, l in enumerate(lines) if "postinstall" in l)
    assert helper_at < launch_at


# ── build + manifest ───────────────────────────────────────────────────────

def test_build_bundles_the_chat_windows_python_packages():
    stage_python = re.search(r"function Stage-Python \{.*?\n\}", _read("build-windows.ps1"), re.S)
    body = stage_python.group(0)
    assert "requirements-copilot.txt" in body
    assert re.search(r"import [^'\n]*\bollama\b", body), "import check must cover ollama"
    assert re.search(r"(?im)^pyaudio\b", _read("requirements-windows.txt"))


def test_ollama_download_is_pinned_to_a_release_not_latest():
    entry = json.loads(_read("deps-manifest.json"))["ollama_setup"]
    assert "/latest/" not in entry["url"]
    assert "/v%s/" % entry["version"] in entry["url"]
    assert entry["filename"] == "OllamaSetup.exe"


# ── install_ai_assistant.py ────────────────────────────────────────────────

class Machine:
    """Fake Windows machine: records downloads and commands."""

    def __init__(self, tmp_path, ollama_installed=True, server_up=True,
                 payload=b"ollama-setup", failing_pulls=()):
        self.tmp = tmp_path
        self.ollama = str(tmp_path / "Ollama" / "ollama.exe")
        self.installed = ollama_installed
        self.server_up = server_up
        self.payload = payload
        self.failing_pulls = set(failing_pulls)
        self.downloads, self.commands, self.started, self.stopped = [], [], [], []

    def find_ollama(self):
        return self.ollama if self.installed else None

    def download(self, url, dest):
        self.downloads.append(url)
        with open(dest, "wb") as fh:
            fh.write(self.payload)

    def run(self, cmd):
        self.commands.append([os.path.basename(cmd[0])] + list(cmd[1:]))
        if os.path.basename(cmd[0]) == "OllamaSetup.exe":
            self.installed = True
        if cmd[1:2] == ["pull"] and cmd[2] in self.failing_pulls:
            return 1
        return 0

    def is_running(self):
        return self.server_up

    def start_server(self, ollama):
        self.started.append(ollama)
        self.server_up = True
        return "server"

    def stop_server(self, server):
        self.stopped.append(server)


@pytest.fixture
def machine(tmp_path, monkeypatch):
    def make(**kw):
        m = Machine(tmp_path, **kw)
        for name in ("find_ollama", "download", "run", "is_running",
                     "start_server", "stop_server"):
            monkeypatch.setattr(helper, name, getattr(m, name))
        monkeypatch.setattr(helper, "TEMP_DIR", str(tmp_path))
        monkeypatch.setattr(helper, "OLLAMA_SETUP", {
            "url": "https://github.com/ollama/ollama/releases/download/v1/OllamaSetup.exe",
            "filename": "OllamaSetup.exe",
            "sha256": hashlib.sha256(b"ollama-setup").hexdigest(),
        })
        return m
    return make


def _pulled(m):
    return [c[2] for c in m.commands if c[1:2] == ["pull"]]


def test_existing_ollama_is_used_and_models_are_pulled(machine):
    m = machine()

    assert helper.main() == 0
    assert m.downloads == []
    assert _pulled(m) == list(REQUIRED_MODELS)


def test_missing_ollama_is_downloaded_verified_and_installed_silently(machine, tmp_path):
    m = machine(ollama_installed=False)

    assert helper.main() == 0
    assert m.downloads == [helper.OLLAMA_SETUP["url"]]
    setup = next(c for c in m.commands if c[0] == "OllamaSetup.exe")
    assert "/VERYSILENT" in setup and "/SUPPRESSMSGBOXES" in setup
    assert _pulled(m) == list(REQUIRED_MODELS)
    assert not (tmp_path / "OllamaSetup.exe").exists(), "installer left in TEMP"


def test_tampered_download_is_never_run(machine, tmp_path, capsys):
    m = machine(ollama_installed=False, payload=b"not the pinned installer")

    assert helper.main() == 0  # eSim's own install must still finish
    assert not any(c[0] == "OllamaSetup.exe" for c in m.commands)
    assert _pulled(m) == []
    assert "sha256" in capsys.readouterr().out.lower()
    assert not (tmp_path / "OllamaSetup.exe").exists()


def test_server_is_started_for_the_download_and_stopped_after(machine):
    m = machine(server_up=False)

    assert helper.main() == 0
    assert m.started == [m.ollama]
    assert m.stopped == ["server"]
    assert _pulled(m) == list(REQUIRED_MODELS)


def test_a_failed_model_download_does_not_stop_the_rest(machine, capsys):
    m = machine(failing_pulls={REQUIRED_MODELS[0]})

    assert helper.main() == 0
    assert _pulled(m) == list(REQUIRED_MODELS)
    assert REQUIRED_MODELS[0] in capsys.readouterr().out


def test_unexpected_error_still_lets_the_install_finish(machine, monkeypatch, capsys):
    machine()

    def boom():
        raise OSError("disk full")
    monkeypatch.setattr(helper, "find_ollama", boom)

    assert helper.main() == 0
    assert "disk full" in capsys.readouterr().out
