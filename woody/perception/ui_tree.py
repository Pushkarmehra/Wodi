"""
UI Automation tree walker and differ.

Uses Windows UI Automation API (via comtypes) to:
  - Walk the element tree of the foreground window
  - Diff against the previous snapshot to detect meaningful changes
  - Return structured element lists for precise targeting by Desktop Agent

This is what allows Woody to click "the Login button" rather than
relying purely on pixel coordinates.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from woody.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class UIElement:
    name: str
    control_type: str
    automation_id: str
    class_name: str
    rect: dict          # {"left": x, "top": y, "right": r, "bottom": b}
    is_enabled: bool
    is_keyboard_focusable: bool
    children: list["UIElement"] = field(default_factory=list)

    @property
    def center(self) -> tuple[int, int]:
        x = (self.rect["left"] + self.rect["right"]) // 2
        y = (self.rect["top"] + self.rect["bottom"]) // 2
        return x, y

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.control_type,
            "id": self.automation_id,
            "class": self.class_name,
            "rect": self.rect,
            "center": list(self.center),
            "enabled": self.is_enabled,
        }


class UITreeWatcher:
    """
    Walks the UI Automation tree of the foreground window and
    detects meaningful structural changes.

    Usage:
        watcher = UITreeWatcher()
        elements = watcher.get_elements()      # flat list of interactive elements
        changed = watcher.has_changed()        # True if UI changed since last call
    """

    def __init__(self, max_depth: int = 6, max_elements: int = 200) -> None:
        self._max_depth = max_depth
        self._max_elements = max_elements
        self._last_snapshot: list[dict] = []
        self._uia: Any = None

    def _get_uia(self) -> Any:
        """Lazy-load UI Automation COM interface."""
        if self._uia is None:
            try:
                import comtypes.client
                self._uia = comtypes.client.CreateObject(
                    "{ff48dba4-60ef-4201-aa87-54103eef594e}",  # CUIAutomation8
                    interface=comtypes.gen.UIAutomationClient.IUIAutomation,
                )
            except Exception:
                try:
                    # Fallback: use pywinauto's wrapper
                    from pywinauto import Desktop
                    self._uia = Desktop(backend="uia")
                except Exception as e:
                    log.warning("ui_tree.uia_unavailable", error=str(e))
        return self._uia

    def get_elements(self, hwnd: int | None = None) -> list[UIElement]:
        """Return a flat list of interactive UI elements in the foreground window."""
        try:
            return self._walk_pywinauto(hwnd)
        except Exception as e:
            log.debug("ui_tree.walk_error", error=str(e))
            return []

    def _walk_pywinauto(self, hwnd: int | None = None) -> list[UIElement]:
        """Walk UI tree using pywinauto (simpler cross-version compat)."""
        try:
            from pywinauto import Desktop
            from pywinauto.application import Application

            desktop = Desktop(backend="uia")

            if hwnd:
                try:
                    app = Application(backend="uia").connect(handle=hwnd)
                    window = app.top_window()
                except Exception:
                    window = desktop.get_active()
            else:
                window = desktop.get_active()

            elements: list[UIElement] = []
            self._recurse_pywinauto(window.wrapper_object(), elements, depth=0)
            return elements[: self._max_elements]

        except Exception as e:
            log.debug("ui_tree.pywinauto_error", error=str(e))
            return []

    def _recurse_pywinauto(self, elem: Any, out: list[UIElement], depth: int) -> None:
        if depth > self._max_depth or len(out) >= self._max_elements:
            return
        try:
            rect = elem.rectangle()
            out.append(
                UIElement(
                    name=elem.window_text() or "",
                    control_type=str(elem.element_info.control_type),
                    automation_id=elem.element_info.automation_id or "",
                    class_name=elem.element_info.class_name or "",
                    rect={
                        "left": rect.left,
                        "top": rect.top,
                        "right": rect.right,
                        "bottom": rect.bottom,
                    },
                    is_enabled=elem.is_enabled(),
                    is_keyboard_focusable=elem.element_info.enabled,
                )
            )
            for child in elem.children():
                self._recurse_pywinauto(child, out, depth + 1)
        except Exception:
            pass

    def snapshot(self) -> list[dict]:
        """Take a snapshot of current UI elements as serializable dicts."""
        elements = self.get_elements()
        return [e.to_dict() for e in elements]

    def has_changed(self) -> bool:
        """Return True if the UI tree has meaningfully changed since last call."""
        current = self.snapshot()
        changed = current != self._last_snapshot
        self._last_snapshot = current
        return changed

    def find_element(
        self,
        name: str | None = None,
        control_type: str | None = None,
        automation_id: str | None = None,
    ) -> UIElement | None:
        """Find a UI element matching the given criteria."""
        elements = self.get_elements()
        for elem in elements:
            if name and name.lower() not in elem.name.lower():
                continue
            if control_type and control_type.lower() != elem.control_type.lower():
                continue
            if automation_id and automation_id != elem.automation_id:
                continue
            return elem
        return None
