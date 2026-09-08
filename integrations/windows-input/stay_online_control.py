"""Control Center lifecycle only; all game input stays in the existing guard."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from queue import Empty, Queue, SimpleQueue
import subprocess
from threading import Event, Thread

import psutil


@dataclass(frozen=True)
class GuardStatus:
    running: bool
    text: str
    available: bool = True


class StayOnlineControl:
    def __init__(self, root: Path):
        self.root = root
        self.runtime = root / "data/runtime/stay-online"
        self.opt_in = self.runtime / "enabled.json"
        self.commands: Queue[tuple[int, bool]] = Queue()
        self.results: SimpleQueue[tuple[int, GuardStatus]] = SimpleQueue()
        self.closed = Event()

    def status(self) -> GuardStatus:
        try:
            state = json.loads((self.runtime / "state.json").read_text(encoding="utf-8"))
            if not isinstance(state, dict):
                raise ValueError("invalid state object")
            if state.get("status") != "RUNNING":
                return GuardStatus(False, "Oprit · limită atinsă sau sesiune încheiată.")
            process = psutil.Process(int(state["pid"]))
            command = process.cmdline()
            runner = self.root / "integrations/windows-input/run_stay_online_guard.py"
            if not any(os.path.normcase(arg) == os.path.normcase(str(runner)) for arg in command):
                return GuardStatus(False, "Oprit · procesul salvat nu este Anti-AFK.")
            stamp = datetime.fromisoformat(state["updated_at"].replace("Z", "+00:00"))
            if process.create_time() > stamp.timestamp() + 1:
                return GuardStatus(False, "Oprit · stare de la un proces anterior.")
            age = (datetime.now(timezone.utc) - stamp).total_seconds()
            if not 0 <= age <= 15:
                return GuardStatus(True, "Proces prezent · starea nu se mai actualizează.")
            packet = state.get("afk_observation") or {}
            if not isinstance(packet, dict):
                raise ValueError("invalid observation object")
            if state.get("last_error") or not packet.get("known") or not packet.get("predator_in_world"):
                return GuardStatus(True, "Pornit · așteaptă date AFK valide din joc.")
            if packet.get("input_blocked") or packet.get("combat_or_dead"):
                return GuardStatus(True, "Pornit · intervenția este blocată momentan.")
            return GuardStatus(True, "Pornit · un Space la AFK confirmat; fără mers.")
        except (FileNotFoundError, psutil.NoSuchProcess):
            return GuardStatus(False, "Oprit · bifează pentru maximum 24 de ore.")
        except (OSError, ValueError, TypeError, KeyError, psutil.Error):
            return GuardStatus(False, "Stare necunoscută · nu pot verifica procesul.", False)

    def set_enabled(self, enabled: bool) -> None:
        current = self.status()
        if not current.available:
            raise RuntimeError("Nu pot verifica procesul existent; nu pornesc un duplicat.")
        self.runtime.mkdir(parents=True, exist_ok=True)
        if not enabled:
            # Disable future startup even if cooperative shutdown later fails.
            self.opt_in.unlink(missing_ok=True)
        if current.running != enabled:
            script = "Start" if enabled else "Stop"
            command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                       "-File", str(self.root / f"scripts/{script}-LabStayOnlineGuard.ps1"),
                       "-RepositoryRoot", str(self.root)]
            if enabled:
                command += ["-AcknowledgeStayOnline", "-MaxHours", "24"]
            # Detached descendants may inherit pipe handles: do not wait on
            # their stdout/stderr EOF when the short launcher has exited.
            result = subprocess.run(command, cwd=self.root, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                    timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode:
                raise RuntimeError("Comanda a eșuat; verifică jurnalul Anti-AFK.")
            after = self.status()
            if not after.available or after.running != enabled:
                raise RuntimeError("Procesul nu a confirmat schimbarea; verifică jurnalul Anti-AFK.")
        if enabled:
            try:
                preference = json.loads(self.opt_in.read_text(encoding="utf-8"))
                if not isinstance(preference, dict):
                    preference = {}
            except (OSError, ValueError):
                preference = {}
            preference.update(enabled=True, maximum_guard_hours=24)
            temporary = self.opt_in.with_suffix(f".{os.getpid()}.tmp")
            temporary.write_text(json.dumps(preference) + "\n", encoding="utf-8")
            temporary.replace(self.opt_in)

    def start(self) -> None:
        Thread(target=self._run, daemon=True, name="cc-anti-afk").start()

    def _run(self) -> None:
        # Existing local opt-in is applied once, never an endless restart loop.
        pending = True if self.opt_in.is_file() else None
        revision = 0
        error = None
        while not self.closed.is_set():
            if pending is not None:
                try:
                    self.set_enabled(pending)
                    error = None
                except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
                    error = str(exc) if isinstance(exc, RuntimeError) else "Nu am putut schimba Anti-AFK."
            current = self.status()
            self.results.put((revision, GuardStatus(current.running, error or current.text, current.available)))
            try:
                revision, pending = self.commands.get(timeout=1)
            except Empty:
                pending = None


class StayOnlinePanel:
    """Tk methods run only on the UI thread; subprocesses never do."""
    def __init__(self, parent, root: Path):
        import tkinter as tk
        from tkinter import ttk

        self.control = StayOnlineControl(root)
        self.revision = 0
        self.enabled = tk.BooleanVar(value=False)
        self.text = tk.StringVar(value="Verific Anti-AFK…")
        frame = ttk.Frame(parent)
        frame.pack(side="right", padx=16)
        self.checkbox = ttk.Checkbutton(frame, text="Anti-AFK", variable=self.enabled,
                                       command=self._toggle, state="disabled")
        self.checkbox.pack(anchor="w")
        ttk.Label(frame, textvariable=self.text, wraplength=250,
                  foreground="#555555").pack(anchor="w")
        self.control.start()

    def _toggle(self) -> None:
        # Discard old polling results before waiting for this command's result.
        while not self.control.results.empty():
            self.control.results.get_nowait()
        self.revision += 1
        self.checkbox.configure(state="disabled")
        self.text.set("Pornesc…" if self.enabled.get() else "Opresc…")
        self.control.commands.put((self.revision, self.enabled.get()))

    def refresh(self) -> None:
        latest = None
        while True:
            try:
                revision, result = self.control.results.get_nowait()
                if revision == self.revision:
                    latest = result
            except Empty:
                break
        if latest is not None:
            self.enabled.set(latest.running)
            self.text.set(latest.text)
            self.checkbox.configure(state="normal" if latest.available else "disabled")

    def close(self) -> None:
        # Preserve the existing independently launched, time-bounded guard.
        self.control.closed.set()
