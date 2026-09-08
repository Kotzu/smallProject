"""Read-only CC tab; formatting/file reads happen outside widget callbacks."""

from tkinter import StringVar, ttk


class SonarPanel(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=12)
        self.status = StringVar(value="Sonar: aștept observațiile")
        self.notes = StringVar()
        self.previous_rows = None
        self.header = ttk.Label(self, textvariable=self.status)
        self.header.pack(fill="x", pady=(0, 8))
        content = ttk.Frame(self)
        content.pack(fill="both", expand=True)
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=1)
        self.table = ttk.Treeview(
            content,
            columns=("kind", "direction", "measure", "limits"),
            show="headings",
            height=12,
        )
        for name, title, width in (
            ("kind", "Element", 180),
            ("direction", "Direcție / nivel candidat", 140),
            ("measure", "Estimare geometrică", 300),
            ("limits", "Ce știm / ce nu știm", 600),
        ):
            self.table.heading(name, text=title)
            self.table.column(
                name, width=width, minwidth=width, stretch=(name == "limits")
            )
        vertical = ttk.Scrollbar(content, orient="vertical", command=self.table.yview)
        horizontal = ttk.Scrollbar(
            content, orient="horizontal", command=self.table.xview
        )
        self.table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.table.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        self.footer = ttk.Label(self, textvariable=self.notes, foreground="#555555")
        self.footer.pack(fill="x", pady=(8, 0))
        self.bind("<Configure>", self._resized)

    def _resized(self, event):
        if event.widget is self:
            width = max(100, event.width - 24)
            self.header.configure(wraplength=width)
            self.footer.configure(wraplength=width)

    def update_details(self, model):
        self.status.set(model.status)
        self.notes.set(model.notes)
        if model.rows != self.previous_rows:
            children = self.table.get_children()
            if children:
                self.table.delete(*children)
            for row in model.rows:
                self.table.insert("", "end", values=row)
            self.previous_rows = model.rows
