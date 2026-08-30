#!/usr/bin/env python3
"""
app.py - main GUI for Raid Assistant.

A "character" is a PokeMMO account (players have alts). Loading one "logs you
in" and scopes everything to saves/<character>/.

Main view is a coverage grid:
    rows    = the 6 raids (Heatran, Cresselia, Meloetta, Cobalion, Terrakion, Virizion)
    columns = team positions P1-P4
    cell    = a button; label = scan progress for that (raid, position):
              – nothing, ! partial, ✗ a scan fails its strat, ✓ all 6 valid.
              Click it to open the scan window (scan_window.py).

Gear button (top right) drops the whole menu:
    New / Change ▸ (list) / Delete Character
    New Team   (next iteration)
    Check for Updates   ("↑ Update available" when origin/main is ahead)

Startup: 0 characters -> "create one" screen; exactly 1 -> load it; more than
one -> pick from a dropdown on the start screen.

Run:  python app.py
"""

import os
import re
import shutil
import threading
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox

import theme
import updater
from prefs import Prefs
from scan_window import ScanWindow, evaluate_position
from moves_window import MovesWindow

HERE = os.path.dirname(os.path.abspath(__file__))
SAVES = os.path.join(HERE, "saves")

RAIDS = ["Heatran", "Cresselia", "Meloetta", "Cobalion", "Terrakion", "Virizion"]
POSITIONS = ["P1", "P2", "P3", "P4"]


def list_characters():
    os.makedirs(SAVES, exist_ok=True)
    return sorted(d for d in os.listdir(SAVES) if os.path.isdir(os.path.join(SAVES, d)))


class Tooltip:
    """Small hover label for a widget. `.set(text)` updates it later."""

    def __init__(self, widget, text, delay=450):
        self.widget, self.text, self.delay = widget, text, delay
        self.tip = self._job = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def set(self, text):
        self.text = text

    def _schedule(self, _=None):
        self._cancel()
        self._job = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self._job:
            self.widget.after_cancel(self._job)
            self._job = None

    def _show(self):
        if self.tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.text, background=theme.TOOLTIP_BG,
                 foreground=theme.FG, relief="solid", borderwidth=1,
                 padx=6, pady=2, font=("TkDefaultFont", 9)).pack()

    def _hide(self, _=None):
        self._cancel()
        if self.tip:
            self.tip.destroy()
            self.tip = None


class App:
    def __init__(self, root):
        self.root = root
        self.character = None
        self.prefs = Prefs()
        saved = self.prefs.get("scan_region")
        self.bbox = tuple(saved) if saved and len(saved) == 4 else None

        root.title("Raid Assistant")
        root.geometry("470x330")
        root.minsize(400, 280)

        self._build_topbar()
        self._build_start()
        self._build_grid()
        self._boot()
        self._start_update_check()

    # ---------------- gear menu ----------------
    def _build_topbar(self):
        """A thin strip with a gear button, top-right, that drops the whole
        menu. Replaces the OS menu bar (which can't be themed on Windows)."""
        self.topbar = ttk.Frame(self.root)
        self.topbar.pack(side="top", fill="x")

        self.gear = ttk.Menubutton(self.topbar, text="⚙", takefocus=False,
                                   style="Gear.TMenubutton")
        self.gear.pack(side="right", padx=6, pady=4)
        Tooltip(self.gear, "Menu")

        m = tk.Menu(self.gear, tearoff=0)
        m.add_command(label="New Character", command=self.character_new)
        self.change_menu = tk.Menu(m, tearoff=0)
        m.add_cascade(label="Change Character", menu=self.change_menu)
        m.add_command(label="Delete Character", command=self.character_delete)
        m.add_separator()
        m.add_command(label="New Team", command=self.team_new)
        m.add_separator()
        self._update_label = "Check for Updates"
        m.add_command(label=self._update_label, command=self.check_updates)
        self._update_idx = m.index("end")

        self.gear_menu = m
        self.gear["menu"] = m
        self._refresh_change_menu()

    # ---------------- self-update ----------------
    def _start_update_check(self):
        """Background: see if origin/main is ahead, and if so flag the gear."""
        if not updater.available():
            return

        def worker():
            info = updater.check()
            if info and info.get("behind"):
                self._pending_update = info
                self.root.after(0, self._flag_update)

        threading.Thread(target=worker, daemon=True).start()

    def _flag_update(self):
        info = getattr(self, "_pending_update", None)
        if info:
            self.gear_menu.entryconfigure(
                self._update_idx, label=f"↑ Update available ({info['behind']})")
            self.gear.configure(text="⚙ •")

    def check_updates(self):
        if not updater.available():
            messagebox.showinfo(
                "Updates", "This copy isn't a git checkout, so it can't update "
                "itself.\nRe-download it, or run 'git pull' in the folder.")
            return
        self.root.config(cursor="watch")
        self.root.update_idletasks()
        info = getattr(self, "_pending_update", None) or updater.check()
        self.root.config(cursor="")
        if info is None:
            messagebox.showwarning("Updates", "Couldn't reach GitHub — try again later.")
            return
        if not info["behind"]:
            messagebox.showinfo("Updates", "You're on the latest version.")
            return
        lines = "\n".join(f"  • {s}" for s in info["subjects"][:10])
        more = "\n  …" if len(info["subjects"]) > 10 else ""
        note = ("\n\nYou have local changes — the update will only go through if "
                "it can fast-forward cleanly." if info["dirty"] else "")
        if not messagebox.askyesno(
                "Updates", f"{info['behind']} update(s) available:\n\n{lines}{more}"
                f"{note}\n\nInstall now?"):
            return
        ok, out = updater.update()
        if ok:
            self._pending_update = None
            self.gear_menu.entryconfigure(self._update_idx, label=self._update_label)
            self.gear.configure(text="⚙")
            messagebox.showinfo("Updates", "Updated. Restart the app to load the new version.")
        else:
            messagebox.showerror("Updates", f"Update failed:\n\n{out}")

    def _refresh_change_menu(self):
        self.change_menu.delete(0, "end")
        chars = list_characters()
        for c in chars:
            self.change_menu.add_command(label=c, command=lambda c=c: self._load(c))
        state = "normal" if chars else "disabled"
        self.gear_menu.entryconfigure("Change Character", state=state)

    # ---------------- views ----------------
    def _build_start(self):
        self.start = ttk.Frame(self.root, padding=40)
        self.start_msg = ttk.Label(self.start, text="No character loaded",
                                   font=("TkDefaultFont", 11))
        self.pick_row = ttk.Frame(self.start)
        ttk.Label(self.pick_row, text="Load  ").pack(side="left")
        self.pick_var = tk.StringVar()
        self.pick_cb = ttk.Combobox(self.pick_row, state="readonly", width=22,
                                    textvariable=self.pick_var)
        self.pick_cb.pack(side="left")
        self.pick_cb.bind("<<ComboboxSelected>>",
                          lambda e: self._load(self.pick_var.get()))
        self.create_btn = ttk.Button(self.start, text="Create a character",
                                     command=self.character_new)

    def _build_grid(self):
        self.grid = ttk.Frame(self.root, padding=10)
        self.header = ttk.Label(self.grid, text="", font=("TkDefaultFont", 10, "bold"))
        self.header.pack(anchor="w", pady=(0, 8))

        self.table = ttk.Frame(self.grid)
        self.table.pack(fill="both", expand=True)
        self.cells = {}  # (raid, position) -> ttk.Button
        self.tips = {}   # (raid, position) -> Tooltip

        ttk.Label(self.table, text="", width=11, anchor="w").grid(
            row=0, column=0, padx=2, pady=(0, 4), sticky="w")
        for c, pos in enumerate(POSITIONS, start=1):
            ttk.Label(self.table, text=pos, anchor="center").grid(
                row=0, column=c, padx=2, pady=(0, 4), sticky="ew")
            self.table.columnconfigure(c, weight=1, uniform="pos")

        for r, raid in enumerate(RAIDS, start=1):
            name = ttk.Label(self.table, text=raid, width=11, anchor="w",
                             cursor="hand2")
            name.grid(row=r, column=0, padx=2, pady=2, sticky="w")
            name.bind("<Button-1>", lambda e, ra=raid: self.open_raid(ra))
            Tooltip(name, "Move order")
            self.table.rowconfigure(r, weight=1)
            for c, pos in enumerate(POSITIONS, start=1):
                btn = ttk.Button(self.table, takefocus=False,
                                 command=lambda ra=raid, po=pos: self.open_cell(ra, po))
                btn.grid(row=r, column=c, padx=2, pady=2, sticky="nsew")
                self.cells[(raid, pos)] = btn
                self.tips[(raid, pos)] = Tooltip(btn, "No teams found")

    def _boot(self):
        chars = list_characters()
        if len(chars) == 1:
            self._load(chars[0])
        else:
            self._show_start()

    def _show_start(self):
        self.character = None
        self.grid.pack_forget()
        for w in (self.start_msg, self.pick_row, self.create_btn):
            w.pack_forget()
        self.start_msg.pack(pady=(0, 14))
        chars = list_characters()
        if chars:
            self.pick_cb["values"] = chars
            self.pick_var.set("")
            self.pick_row.pack(pady=(0, 12))
        self.create_btn.pack()
        self.start.pack(fill="both", expand=True)

    def _load(self, name):
        self.character = name
        self.start.pack_forget()
        self.grid.pack(fill="both", expand=True)
        self.refresh_grid()

    # ---------------- paths / status ----------------
    def _char_dir(self):
        return os.path.join(SAVES, self.character)

    def _paste_path(self, raid, position):
        return os.path.join(self._char_dir(), raid, f"{position}.txt")

    def _mark(self, raid, position):
        state = evaluate_position(raid, position, self._paste_path(raid, position))
        return {"empty": "–", "partial": "!", "invalid": "✗", "valid": "✓"}[state]

    def refresh_grid(self):
        self.header.config(text=f"Character:  {self.character}")
        for (raid, pos), btn in self.cells.items():
            btn.config(text=self._mark(raid, pos))

    def open_cell(self, raid, position):
        ScanWindow(self, raid, position)

    def open_raid(self, raid):
        MovesWindow(self, raid)

    # ---------------- Character menu ----------------
    def character_new(self):
        name = simpledialog.askstring("New Character", "Character name:", parent=self.root)
        if not name:
            return
        safe = re.sub(r'[<>:"/\\|?*]', "", name).strip()
        if not safe:
            messagebox.showwarning("New Character", "That name can't be used for a folder.")
            return
        if safe in list_characters() and not messagebox.askyesno(
                "New Character", f"'{safe}' already exists. Load it?"):
            return
        os.makedirs(os.path.join(SAVES, safe), exist_ok=True)
        self._refresh_change_menu()
        self._load(safe)

    def character_delete(self):
        if not self.character:
            messagebox.showinfo("Delete Character", "No character loaded.")
            return
        if messagebox.askyesno("Delete Character",
                               f"Delete '{self.character}' and all of its saved teams?"):
            shutil.rmtree(self._char_dir(), ignore_errors=True)
            self._refresh_change_menu()
            self._boot()

    # ---------------- Team menu ----------------
    def team_new(self):
        if not self.character:
            messagebox.showinfo("New Team", "Load a character first.")
            return
        messagebox.showinfo("New Team", "Coming in the next iteration.")


if __name__ == "__main__":
    root = tk.Tk()
    theme.apply(root)
    App(root)
    root.mainloop()
