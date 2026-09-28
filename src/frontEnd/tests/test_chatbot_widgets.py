"""eSim Copilot chat widgets under eSim 2.6 (PyQt6 and the Aurora theme).

The chatbot was developed on a branch whose main window was still PyQt5,
so several of its code paths had never run under PyQt6 or eSim's theme.
"""
import os
import sys
from unittest.mock import MagicMock

import pytest

_FE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _FE not in sys.path:
    sys.path.insert(0, _FE)


def test_chatbot_thread_imports_without_chromadb(monkeypatch):
    # The chat window does not use documentation retrieval, so a missing
    # chromadb must not stop the chatbot (or eSim) from loading.
    monkeypatch.setitem(sys.modules, "chromadb", None)
    for name in [m for m in sys.modules if m == "chatbot" or m.startswith("chatbot.")]:
        monkeypatch.delitem(sys.modules, name)

    import chatbot.chatbot_thread  # noqa: F401


def test_session_click_reads_session_id_from_item(qapp):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QListWidgetItem
    from frontEnd.Chatbot import ChatbotGUI

    item = QListWidgetItem("past chat")
    item.setData(Qt.ItemDataRole.UserRole, "session-42")
    gui = MagicMock(_current_session_id="session-42", _viewing_past_session=False)

    # Clicking the session that is already shown is a no-op; reaching that
    # early return proves the session id was read from the item.
    ChatbotGUI._on_session_clicked(gui, item)

    gui._save_current_session.assert_not_called()


@pytest.fixture(params=["style_light.qss", "style_dark.qss"])
def esim_theme(qapp, request):
    """eSim's real theme, whose global QPushButton min-width/padding the
    chatbot's small fixed-size buttons were never designed for."""
    from frontEnd import theme_utils
    qapp.setStyleSheet(theme_utils.build_qss(
        request.param, "dark" in request.param, "default", "system", "system", 100))
    yield
    qapp.setStyleSheet("")


def _buttons_not_at_fixed_size(root):
    from PyQt6.QtWidgets import QPushButton, QWIDGETSIZE_MAX
    root.ensurePolished()  # stylesheets apply at polish, i.e. when shown
    return [(b.text(), b.minimumSize(), b.maximumSize())
            for b in root.findChildren(QPushButton)
            if b.maximumWidth() < QWIDGETSIZE_MAX
            and b.maximumHeight() < QWIDGETSIZE_MAX
            and b.minimumSize() != b.maximumSize()]


def test_chat_panel_stays_a_side_panel_under_esim_theme(esim_theme, monkeypatch):
    from PyQt6 import sip
    from frontEnd.Chatbot import ChatbotGUI

    # No Ollama probing or server start from a unit test.
    monkeypatch.setattr(ChatbotGUI, "_startup_check", lambda self: None)
    monkeypatch.setattr(ChatbotGUI, "_update_ollama_status", lambda self: None)
    gui = ChatbotGUI()
    try:
        assert _buttons_not_at_fixed_size(gui) == []
        assert gui.minimumSizeHint().width() <= 480
    finally:
        gui._status_poll_timer.stop()
        sip.delete(gui)


def test_dynamic_chat_widgets_keep_button_sizes_under_esim_theme(esim_theme, qapp, tmp_path):
    import time
    from PyQt6 import sip
    from PyQt6.QtGui import QColor, QPixmap
    from frontEnd.Chatbot import ChatbotGUI, ChatHistoryViewer, _SessionItemWidget

    image = tmp_path / "schematic.png"
    pix = QPixmap(64, 64)
    pix.fill(QColor("white"))
    pix.save(str(image))

    widgets = [
        _SessionItemWidget("s1", "RC filter", "2026-09-28", msg_count=2),
        ChatHistoryViewer({"title": "RC filter", "messages": []}),
        ChatbotGUI._make_thumbnail(MagicMock(), str(image)),
    ]
    try:
        for widget in widgets:
            assert _buttons_not_at_fixed_size(widget) == [], type(widget).__name__
    finally:
        # ChatHistoryViewer schedules a 120 ms scroll on its browser; let it
        # fire while the widgets are alive, or it lands in a later test.
        end = time.monotonic() + 0.3
        while time.monotonic() < end:
            qapp.processEvents()
        for widget in widgets:
            sip.delete(widget)


def test_image_thumbnail_scales_real_image(qapp, tmp_path):
    from PyQt6.QtGui import QColor, QPixmap
    from PyQt6.QtWidgets import QLabel
    from frontEnd.Chatbot import ChatbotGUI

    image = tmp_path / "schematic.png"
    pix = QPixmap(640, 480)
    pix.fill(QColor("white"))
    assert pix.save(str(image))

    card = ChatbotGUI._make_thumbnail(MagicMock(), str(image))

    thumbs = [lbl.pixmap() for lbl in card.findChildren(QLabel)
              if not lbl.pixmap().isNull()]
    assert thumbs and thumbs[0].width() <= 68 and thumbs[0].height() <= 36
