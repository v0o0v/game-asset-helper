"""Tests for gah.tray — icon contents and activation handler.

Visual quality of the tray icon is a manual check; here we only verify
that the pixmap is no longer fully transparent (i.e. we actually drew
something) and that the activation handler routes a double-click to
``on_open_main`` while ignoring other reasons.
"""

from __future__ import annotations


def _make_qapplication():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_build_app_icon_is_non_empty() -> None:
    _make_qapplication()
    from PySide6.QtGui import QIcon

    from gah.tray import _build_app_icon

    icon = _build_app_icon()
    assert isinstance(icon, QIcon)

    # The icon must contain at least one opaque pixel — i.e. it isn't
    # the M0 empty placeholder anymore.
    pixmap = icon.pixmap(64, 64)
    image = pixmap.toImage()
    width, height = image.width(), image.height()
    assert width > 0 and height > 0

    found_opaque = False
    for y in range(0, height, 4):
        for x in range(0, width, 4):
            if image.pixelColor(x, y).alpha() > 0:
                found_opaque = True
                break
        if found_opaque:
            break
    assert found_opaque, "tray icon pixmap is fully transparent"


def test_double_click_invokes_on_open_main() -> None:
    _make_qapplication()
    from PySide6.QtWidgets import QSystemTrayIcon

    from gah.tray import _handle_tray_activation

    calls: list[None] = []
    _handle_tray_activation(QSystemTrayIcon.DoubleClick, lambda: calls.append(None))
    assert len(calls) == 1


def test_single_click_and_context_do_not_invoke_on_open_main() -> None:
    _make_qapplication()
    from PySide6.QtWidgets import QSystemTrayIcon

    from gah.tray import _handle_tray_activation

    calls: list[None] = []
    cb = lambda: calls.append(None)  # noqa: E731 — short test helper

    for reason in (
        QSystemTrayIcon.Trigger,
        QSystemTrayIcon.Context,
        QSystemTrayIcon.MiddleClick,
        QSystemTrayIcon.Unknown,
    ):
        _handle_tray_activation(reason, cb)

    assert calls == []


def test_handler_tolerates_none_callback() -> None:
    _make_qapplication()
    from PySide6.QtWidgets import QSystemTrayIcon

    from gah.tray import _handle_tray_activation

    # Should not raise when no callback is registered (tests / headless paths).
    _handle_tray_activation(QSystemTrayIcon.DoubleClick, None)
