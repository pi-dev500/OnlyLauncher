#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Searchable dropdown widget.

`CustomDropDown` is a small replacement for `ttk.Combobox` that lets the user type
to filter a potentially very long list (hundreds of Minecraft versions, for
instance) instead of scrolling through it.

The widget exposes a `ttk.Combobox`-like interface:

    dd = CustomDropDown(parent, values=["1.20.1", "1.21", ...], command=callback)
    dd.pack(fill="x")
    dd.get()             # currently selected value ("" when nothing is selected)
    dd.set("1.21")       # programmatic selection
    dd["values"] = [...] # replace the list
    dd.configure(command=...)

`command` is called with the selected string every time an item is picked.

The list is shown in a `Toplevel`, so it can overflow the parent window, and it is
filtered on `<KeyRelease>`. `Escape` cancels, `Return` validates, the arrow keys
move the highlight.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Iterable, Optional


class CustomDropDown(ttk.Frame):
    """An editable combobox with incremental search over `values`."""

    def __init__(self, parent, values: Optional[Iterable[str]] = None,
                 command: Optional[Callable[[str], None]] = None,
                 width: int = 20, max_visible: int = 12, **kwargs):
        super().__init__(parent, **kwargs)
        self._values = [str(v) for v in (values or [])]
        self._command = command
        self._max_visible = max_visible
        self._popup: Optional[tk.Toplevel] = None
        self._listbox: Optional[tk.Listbox] = None
        self._filtered: list = []
        self._readonly = False

        self.var = tk.StringVar(value="")
        self.entry = ttk.Entry(self, textvariable=self.var, width=width)
        self.entry.pack(side="left", fill="both", expand=True)
        self.entry.bind("<KeyRelease>", self._on_key_release)
        self.entry.bind("<Down>", self._on_down)
        self.entry.bind("<Up>", self._on_up)
        self.entry.bind("<Return>", self._on_return)
        self.entry.bind("<Escape>", lambda e: self._close_popup())
        self.entry.bind("<FocusOut>", lambda e: self.after(150, self._maybe_close))

        self.button = ttk.Button(self, text="\u25bc", width=3, command=self.drop)
        self.button.pack(side="left")

    # ------------------------------------------------------------------ values
    def get(self) -> str:
        return self.var.get()

    def set(self, value: str) -> None:
        self.var.set("" if value is None else str(value))

    def __getitem__(self, key):
        if key == "values":
            return list(self._values)
        raise KeyError(key)

    def __setitem__(self, key, value):
        if key in ("values", "value"):
            self.configure(values=value)
        else:
            raise KeyError(key)

    def configure(self, **kwargs):  # noqa: D102 - mirrors tkinter's API
        if "values" in kwargs:
            self._values = [str(v) for v in (kwargs.pop("values") or [])]
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        if "state" in kwargs:
            state = kwargs.pop("state")
            self._readonly = state == "readonly"
            self.entry.configure(state="readonly" if self._readonly else "normal")
            self.button.configure(state="disabled" if state == "disabled" else "normal")
        if kwargs:
            super().configure(**kwargs)

    config = configure

    # ------------------------------------------------------------------ popup
    def drop(self):
        """Toggle the list of suggestions."""
        if self._popup is not None:
            self._close_popup()
            return
        self._filter(self.var.get() if not self._readonly else "")
        self._open_popup()

    def _open_popup(self):
        self._popup = tk.Toplevel(self)
        self._popup.wm_overrideredirect(True)
        try:
            self._popup.wm_attributes("-topmost", True)
        except tk.TclError:
            pass

        height = max(1, min(self._max_visible, len(self._filtered) or 1))
        frame = tk.Frame(self._popup, borderwidth=1, relief="solid")
        frame.pack(fill="both", expand=True)
        self._listbox = tk.Listbox(frame, height=height, activestyle="dotbox",
                                   exportselection=False)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self._listbox.yview)
        self._listbox.configure(yscrollcommand=scroll.set)
        self._listbox.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self._listbox.bind("<ButtonRelease-1>", self._on_click)
        self._listbox.bind("<Return>", self._on_return)
        self._listbox.bind("<Escape>", lambda e: self._close_popup())

        self._fill_listbox()
        self._place_popup()
        self._listbox.focus_set()

    def _fill_listbox(self):
        if self._listbox is None:
            return
        self._listbox.delete(0, "end")
        for value in self._filtered:
            self._listbox.insert("end", value)
        if self._filtered:
            self._listbox.selection_set(0)
            self._listbox.activate(0)
            self._listbox.see(0)

    def _place_popup(self):
        if self._popup is None:
            return
        self.update_idletasks()
        x = self.entry.winfo_rootx()
        y = self.entry.winfo_rooty() + self.entry.winfo_height()
        width = self.winfo_width() or self.entry.winfo_width()
        rows = max(1, min(self._max_visible, len(self._filtered) or 1))
        height = rows * 18 + 4
        self._popup.wm_geometry(f"{max(width, 120)}x{height}+{x}+{y}")

    def _maybe_close(self):
        """Close the popup when the focus really left both the entry and the list."""
        if self._popup is None:
            return
        try:
            focused = self.focus_get()
        except (tk.TclError, KeyError):
            focused = None
        if focused is None:
            self._close_popup()
            return
        try:
            in_popup = focused.winfo_toplevel() is self._popup
        except tk.TclError:
            in_popup = False
        if not in_popup and focused is not self.entry:
            self._close_popup()

    def _close_popup(self):
        if self._popup is not None:
            self._popup.destroy()
        self._popup = None
        self._listbox = None

    # ------------------------------------------------------------------ events
    def _on_key_release(self, event):
        if event.keysym in ("Up", "Down", "Return", "Escape", "Tab"):
            return
        self._filter(self.var.get())
        if self._popup is None and not self._readonly:
            self._open_popup()
        else:
            self._fill_listbox()
            self._place_popup()

    def _filter(self, text: str):
        text = (text or "").lower()
        self._filtered = [v for v in self._values if text in v.lower()]

    def _on_down(self, event):
        return self._move(1)

    def _on_up(self, event):
        return self._move(-1)

    def _move(self, delta):
        if self._listbox is None or not self._filtered:
            return "break"
        current = self._listbox.curselection()
        index = (current[0] if current else -1) + delta
        index = max(0, min(len(self._filtered) - 1, index))
        self._listbox.selection_clear(0, "end")
        self._listbox.selection_set(index)
        self._listbox.activate(index)
        self._listbox.see(index)
        return "break"

    def _on_click(self, event):
        self._select_current()
        return "break"

    def _on_return(self, event=None):
        if self._listbox is not None and self._filtered:
            self._select_current()
        else:
            self._commit(self.var.get())
        return "break"

    def _select_current(self):
        if self._listbox is None:
            return
        current = self._listbox.curselection()
        if not current:
            return
        self._commit(self._filtered[current[0]])

    def _commit(self, value: str):
        self.var.set(value)
        self._close_popup()
        if self._command is not None:
            self._command(value)

    def destroy(self):  # noqa: D102
        self._close_popup()
        super().destroy()


# Backwards compatible alias: the module's own demo used to call
# `SearchableComboBox`, a name that was never defined.
SearchableComboBox = CustomDropDown


if __name__ == "__main__":
    root = tk.Tk()
    root.title("Searchable Dropdown")
    options = ["Apple", "Banana", "Cherry", "Date", "Grapes", "Kiwi", "Mango",
               "Orange", "Peach", "Pear"]

    chosen = tk.StringVar(value="(rien)")
    sc = CustomDropDown(root, values=options, command=chosen.set)
    sc.pack(expand=True, fill="x", padx=10, pady=10)
    tk.Label(root, textvariable=chosen).pack()
    root.geometry("220x120")
    root.mainloop()
