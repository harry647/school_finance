import tkinter as tk
from tkinter import ttk


PRIMARY = "#1E88E5"
PRIMARY_DARK = "#1565C0"
BACKGROUND = "#FAFAFA"
SURFACE = "#FFFFFF"
TEXT_PRIMARY = "#212121"
TEXT_SECONDARY = "#757575"
SUCCESS = "#2E7D32"
WARNING = "#F57C00"
DANGER = "#C62828"
BORDER = "#E0E0E0"
MUTED_FG = "#757575"
PAID_BG = "#ccffcc"
OVERDUE_BG = "#ffcccc"

PAD_XS = 4
PAD_SM = 8
PAD_MD = 16
PAD_LG = 24

FONT_TITLE = ("Segoe UI", 16, "bold")
FONT_HEADER = ("Segoe UI", 12, "bold")
FONT_BODY = ("Segoe UI", 10)
FONT_MUTED = ("Segoe UI", 9)
FONT_TITLE_LG = ("Segoe UI", 14, "bold")
FONT_BODY_ITALIC = ("Segoe UI", 9, "italic")
FONT_HEADER_BOLD = ("Segoe UI", 10, "bold")

ZEBRA_ODD = "#F4F6F8"
ZEBRA_EVEN = "#FFFFFF"


def apply_theme():
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure("TFrame", background=BACKGROUND)
    style.configure("TLabel", background=BACKGROUND, font=FONT_MUTED)

    style.configure("TButton", font=FONT_MUTED, padding=6)
    style.map("TButton", background=[("active", BORDER)])

    style.configure("Accent.TButton", background=PRIMARY, foreground=SURFACE, font=FONT_MUTED, padding=6)
    style.map("Accent.TButton",
              background=[("active", PRIMARY_DARK), ("pressed", PRIMARY_DARK)],
              foreground=[("active", SURFACE), ("pressed", SURFACE)])

    style.configure("Danger.TButton", background=DANGER, foreground=SURFACE, font=FONT_MUTED, padding=6)
    style.map("Danger.TButton",
              background=[("active", "#B71C1C"), ("pressed", "#B71C1C")],
              foreground=[("active", SURFACE), ("pressed", SURFACE)])

    style.configure("TNotebook", background=BACKGROUND, tabmargins=[2, 5, 2, 0])
    style.configure("TNotebook.Tab", padding=[10, 4], font=FONT_MUTED)

    style.configure("Treeview", rowheight=22, font=FONT_MUTED, background=SURFACE)
    style.configure("Treeview.Heading", font=FONT_MUTED, background=BORDER)
    style.map("Treeview", background=[("selected", PRIMARY)], foreground=[("selected", SURFACE)])
    style.configure("Treeview", fieldbackground=SURFACE)

    style.configure("TLabelframe", background=BACKGROUND)
    style.configure("TLabelframe.Label", background=BACKGROUND, font=FONT_MUTED)

    style.configure("TEntry", fieldbackground=SURFACE, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER)
    style.map("TEntry", fieldbackground=[("focus", SURFACE)], bordercolor=[("focus", PRIMARY)])

    style.configure("TCombobox", fieldbackground=SURFACE, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER)
    style.map("TCombobox", fieldbackground=[("focus", SURFACE)], bordercolor=[("focus", PRIMARY)])

    style.configure("Card.TFrame", background=SURFACE, borderwidth=1, relief="solid", padding=PAD_MD)


class BarChart(tk.Frame):
    def __init__(self, parent, data=None, color=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.data = data or []
        self.color = color or PRIMARY
        self._canvas = tk.Canvas(self, bg=BACKGROUND, highlightthickness=0, height=160)
        self._canvas.pack(fill="both", expand=True)
        self._tooltip = None
        self._bars = []
        self._canvas.bind("<Configure>", self._on_configure)
        self._canvas.bind("<Motion>", self._on_motion)
        self._canvas.bind("<Leave>", self._on_leave)
        self.after(50, self._draw)

    def _on_configure(self, event):
        self.after_idle(self._draw)

    def _on_leave(self, event):
        self._canvas.config(cursor="")
        self._hide_tooltip()

    def _draw(self):
        self._canvas.delete("all")
        self._bars = []
        if not self.data:
            return

        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        if cw < 10 or ch < 10:
            return

        pad_left = 50
        pad_right = 10
        pad_top = 24
        pad_bottom = 30

        max_val = max((d["total"] for d in self.data), default=1)
        if max_val == 0:
            max_val = 1

        chart_w = cw - pad_left - pad_right
        chart_h = ch - pad_top - pad_bottom

        n = len(self.data)
        gap = max(6, min(18, chart_w * 0.12 / n)) if n > 1 else max(10, chart_w * 0.2)
        bar_w = max(10, (chart_w - gap * (n + 1)) / n)

        for i, d in enumerate(self.data):
            x = pad_left + gap + i * (bar_w + gap)
            bar_h = (d["total"] / max_val) * chart_h
            y1 = pad_top + chart_h - bar_h
            y2 = pad_top + chart_h

            tag = "bar_{}".format(i)
            if bar_h > 4:
                r = min(8, bar_w / 2, bar_h / 2)
                self._draw_rounded_rect(x, y1, x + bar_w, y2, r, self.color, tag)
            else:
                self._canvas.create_rectangle(x, y1, x + bar_w, y2, fill=self.color, width=0, tags=tag)

            if bar_h > 18:
                self._canvas.create_text(
                    x + bar_w / 2, y1 - 10,
                    text="{:,}".format(int(d["total"])),
                    font=FONT_MUTED, fill=TEXT_SECONDARY,
                    tags=tag
                )

            label = d["label"]
            if len(label) > 12:
                label = label[:10] + ".."
            self._canvas.create_text(
                x + bar_w / 2, pad_top + chart_h + 16,
                text=label,
                font=FONT_MUTED, fill=TEXT_SECONDARY
            )

            self._bars.append({
                "bbox": (x, y1, x + bar_w, y2),
                "data": d
            })

    def _draw_rounded_rect(self, x1, y1, x2, y2, r, color, tag):
        r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
        self._canvas.create_arc(x1, y1, x1 + 2 * r, y1 + 2 * r, start=90, extent=90, style="pieslice", fill=color, outline=color, tags=tag)
        self._canvas.create_arc(x2 - 2 * r, y1, x2, y1 + 2 * r, start=0, extent=90, style="pieslice", fill=color, outline=color, tags=tag)
        self._canvas.create_arc(x2 - 2 * r, y2 - 2 * r, x2, y2, start=270, extent=90, style="pieslice", fill=color, outline=color, tags=tag)
        self._canvas.create_arc(x1, y2 - 2 * r, x1 + 2 * r, y2, start=180, extent=90, style="pieslice", fill=color, outline=color, tags=tag)
        self._canvas.create_rectangle(x1 + r, y1, x2 - r, y2, fill=color, outline=color, tags=tag)
        self._canvas.create_rectangle(x1, y1 + r, x2, y2 - r, fill=color, outline=color, tags=tag)

    def _on_motion(self, event):
        x, y = event.x, event.y
        found = None
        for bar in self._bars:
            bx1, by1, bx2, by2 = bar["bbox"]
            if bx1 - 4 <= x <= bx2 + 4 and by1 - 4 <= y <= by2 + 4:
                found = bar
                break

        if found:
            self._canvas.config(cursor="hand2")
            self._show_tooltip(found, event.x_root, event.y_root)
        else:
            self._canvas.config(cursor="")
            self._hide_tooltip()

    def _show_tooltip(self, bar, x_root, y_root):
        if self._tooltip:
            self._tooltip.destroy()
        self._tooltip = tk.Toplevel(self)
        self._tooltip.wm_overrideredirect(True)
        self._tooltip.wm_geometry("+{}+{}".format(x_root + 12, y_root + 12))
        ttk.Label(
            self._tooltip,
            text="{}: KES {:,.2f}".format(bar["data"]["label"], bar["data"]["total"]),
            background=SURFACE,
            foreground=TEXT_PRIMARY,
            font=FONT_MUTED,
            padding=(6, 3)
        ).pack()

    def _hide_tooltip(self):
        if self._tooltip:
            self._tooltip.destroy()
            self._tooltip = None

    def update_data(self, data):
        self.data = data or []
        self._draw()


def sort_treeview_column(tree, col, reverse=False):
    data = []
    for item in tree.get_children():
        values = tree.item(item)["values"]
        tags = tree.item(item)["tags"]
        data.append((values, tags))

    col_index = None
    for i, cid in enumerate(tree["columns"]):
        if cid == col:
            col_index = i
            break

    if col_index is None:
        return

    def sort_key(item):
        val = item[0][col_index]
        try:
            return (0, float(val))
        except (ValueError, TypeError):
            return (1, str(val).lower())

    data.sort(key=sort_key, reverse=reverse)

    tree.delete(*tree.get_children())
    for idx, (values, tags) in enumerate(data):
        new_tags = [t for t in tags if t not in ("even", "odd")]
        new_tags.append("even" if idx % 2 == 0 else "odd")
        tree.insert("", "end", values=values, tags=tuple(new_tags))

    for c in tree["columns"]:
        base = tree.heading(c)["text"].replace(" ▲", "").replace(" ▼", "")
        if c == col:
            arrow = " ▼" if reverse else " ▲"
            tree.heading(c, text=base + arrow)
        else:
            tree.heading(c, text=base)

    tree._sorted_col = col
    tree._sorted_reverse = reverse
