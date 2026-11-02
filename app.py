"""Offline Teyvat atlas. Run with Python 3.10+ and Tkinter; no pip packages."""

import argparse
import csv
import json
import math
import sys
import tkinter as tk
import uuid
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from geometry import (KM_PER_DEGREE, WORLD_BOUNDS, Viewport, distance_km,
                      great_circle, to_latlon)
from storage import load_markers, save_markers

ROOT = Path(__file__).resolve().parent
BG = "#101c27"
PANEL = "#152532"
OCEAN = "#142f40"
LAND = "#34554f"
COAST = "#79ac94"
TEXT = "#e4e9e1"
MUTED = "#99abae"
GOLD = "#efc17b"


def km(value):
    return f"{value:,.1f}".replace(",", " ").replace(".", ",") + " км"


class AtlasApp:
    def __init__(self, root, markers_path=None, demo=False):
        self.root = root
        self.markers_path = markers_path or Path.home() / ".realsizefantasymap" / "markers.json"
        self.coastline = json.loads((ROOT / "data/coastline.json").read_text(encoding="utf-8"))
        self.markers = []
        self.selected = None
        self.add_mode = False
        self.show_grid = tk.BooleanVar(value=True)
        self.show_labels = tk.BooleanVar(value=False)
        self.view = Viewport()
        self.press = None
        self.dragged = False
        self.fitted = False
        self.pending_render = None
        self.dirty = False
        self.status = tk.StringVar(value="Готово · карта работает без интернета")
        root.title("Real Size Fantasy Map — Тейват")
        root.geometry("1360x900")
        root.minsize(1020, 680)
        root.configure(bg=BG)
        self._styles()
        self._layout()
        self._bindings()
        if self.markers_path.exists():
            try:
                self.markers = load_markers(self.markers_path)
            except (OSError, ValueError, UnicodeError) as exc:
                messagebox.showwarning("Метки не загружены", f"{exc}\nИсходный файл сохранён.", parent=root)
        if demo and not self.markers and not self.markers_path.exists():
            self.load_demo()
        else:
            self.refresh_list()
        root.protocol("WM_DELETE_WINDOW", self.close)

    def _styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT,
                        rowheight=34, borderwidth=0, font=("DejaVu Sans", 10))
        style.configure("Treeview.Heading", background=BG, foreground=MUTED,
                        font=("DejaVu Sans", 9), relief="flat")
        style.map("Treeview", background=[("selected", "#38534f")],
                  foreground=[("selected", "#fff1d9")])

    def label(self, parent, text, color=TEXT, size=10, **kw):
        return tk.Label(parent, text=text, fg=color, bg=parent.cget("bg"),
                        font=("DejaVu Sans", size), **kw)

    def button(self, parent, text, command, accent=False, **kw):
        return tk.Button(parent, text=text, command=command, bg=GOLD if accent else "#223744",
                         fg=BG if accent else TEXT, activebackground="#5a776b",
                         activeforeground=TEXT, relief="flat", bd=0, padx=12, pady=8,
                         font=("DejaVu Sans", 10), cursor="hand2", **kw)

    def _layout(self):
        header = tk.Frame(self.root, bg=BG, padx=22, pady=14)
        header.pack(fill="x")
        self.label(header, "◈  REAL SIZE", GOLD, 15).pack(side="left")
        self.label(header, " /  FANTASY MAP", MUTED, 11).pack(side="left", padx=10)
        self.label(header, "ТЕЙВАТ   ·   АТЛАС ПЛАНЕТЫ", TEXT, 10).pack(side="right")
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=16)
        sidebar_shell = tk.Frame(body, bg=PANEL, width=330)
        sidebar_shell.pack(side="left", fill="y", padx=(0, 12))
        sidebar_shell.pack_propagate(False)
        self.sidebar_canvas = tk.Canvas(sidebar_shell, bg=PANEL, highlightthickness=0, width=310)
        sidebar_scroll = ttk.Scrollbar(sidebar_shell, orient="vertical", command=self.sidebar_canvas.yview)
        sidebar_scroll.pack(side="right", fill="y")
        self.sidebar_canvas.pack(side="left", fill="both", expand=True)
        self.sidebar_canvas.configure(yscrollcommand=sidebar_scroll.set)
        sidebar = tk.Frame(self.sidebar_canvas, bg=PANEL, padx=18, pady=18)
        sidebar_window = self.sidebar_canvas.create_window(0, 0, anchor="nw", window=sidebar)

        def size_sidebar(event=None):
            self.sidebar_canvas.itemconfigure(sidebar_window, width=self.sidebar_canvas.winfo_width(),
                height=max(sidebar.winfo_reqheight(), self.sidebar_canvas.winfo_height()))
            self.sidebar_canvas.configure(scrollregion=self.sidebar_canvas.bbox("all"))

        self.sidebar_canvas.bind("<Configure>", size_sidebar)
        sidebar.bind("<Configure>", lambda e: self.sidebar_canvas.configure(
            scrollregion=self.sidebar_canvas.bbox("all")))
        self.label(sidebar, "01 / ИССЛЕДОВАНИЕ", GOLD, 9, anchor="w").pack(fill="x")
        self.label(sidebar, "Берега Тейвата", size=20, anchor="w").pack(fill="x", pady=(10, 5))
        self.label(sidebar, self.coastline.get("subtitle", self.coastline["title"]),
                   MUTED, 9, anchor="w").pack(fill="x")
        self.label(sidebar, "20 000 км", GOLD, 25, anchor="w").pack(fill="x", pady=(18, 0))
        self.label(sidebar, "ширина полушария на экваторе", MUTED, 9, anchor="w").pack(fill="x")
        tk.Frame(sidebar, bg="#2e414a", height=1).pack(fill="x", pady=18)
        self.add_button = self.button(sidebar, "+  Поставить метку", self.toggle_add, accent=True)
        self.add_button.pack(fill="x")
        self.label(sidebar, "Или двойной щелчок по карте", MUTED, 9).pack(pady=(7, 14))
        self.label(sidebar, "02 / РАССТОЯНИЯ ОТ МЕТКИ", GOLD, 9, anchor="w").pack(fill="x")
        self.selected_text = tk.StringVar(value="Выберите точку отсчёта")
        tk.Label(sidebar, textvariable=self.selected_text, wraplength=270, justify="left",
                 bg=PANEL, fg=TEXT, font=("DejaVu Sans", 12), anchor="w").pack(fill="x", pady=(10, 4))
        self.coord_text = tk.StringVar(value="Добавьте две или больше меток")
        tk.Label(sidebar, textvariable=self.coord_text, bg=PANEL, fg=MUTED,
                 font=("DejaVu Sans", 9), anchor="w").pack(fill="x", pady=(0, 10))
        self.tree = ttk.Treeview(sidebar, columns=("name", "distance"), show="headings",
                                selectmode="browse", height=4)
        self.tree.heading("name", text="Метка")
        self.tree.heading("distance", text="По поверхности")
        self.tree.column("name", width=135, minwidth=70)
        self.tree.column("distance", width=125, minwidth=90, anchor="e")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.tree_select)
        self.tree.bind("<Double-Button-1>", lambda e: self.focus_selected())
        actions = tk.Frame(sidebar, bg=PANEL)
        actions.pack(fill="x", pady=8)
        self.button(actions, "Имя", self.rename_selected).pack(side="left")
        self.button(actions, "К точке", self.focus_selected).pack(side="left", padx=5)
        self.button(actions, "Удалить", self.delete_selected).pack(side="left")
        files = tk.Frame(sidebar, bg=PANEL)
        files.pack(fill="x", pady=(4, 8))
        self.button(files, "Импорт", self.import_markers).pack(side="left")
        self.button(files, "JSON", self.export_markers).pack(side="left", padx=5)
        self.button(files, "CSV", self.export_distances).pack(side="left")
        self.button(sidebar, "Добавить пример меток", self.load_demo).pack(fill="x", pady=(0, 10))
        self.label(sidebar, "Дуга большого круга · сфера\nОкружность 40 000 км", MUTED, 9,
                   justify="left", anchor="w").pack(fill="x")
        main = tk.Frame(body, bg=BG)
        main.pack(side="left", fill="both", expand=True)
        toolbar = tk.Frame(main, bg=BG)
        toolbar.pack(fill="x", pady=(0, 10))
        self.button(toolbar, "Тейват", lambda: self.fit("teyvat")).pack(side="left")
        self.button(toolbar, "Планета", lambda: self.fit("planet")).pack(side="left", padx=6)
        self.button(toolbar, "Океан", lambda: self.fit("ocean")).pack(side="left")
        for text, variable in (("Сетка", self.show_grid), ("Регионы", self.show_labels)):
            tk.Checkbutton(toolbar, text=text, variable=variable, command=self.schedule_render,
                           fg=MUTED, bg=BG, selectcolor=PANEL, activebackground=BG,
                           activeforeground=TEXT, font=("DejaVu Sans", 9)).pack(side="left", padx=5)
        self.button(toolbar, "?", self.help).pack(side="right")
        self.button(toolbar, "−", lambda: self.zoom_center(1 / 1.3)).pack(side="right", padx=5)
        self.button(toolbar, "+", lambda: self.zoom_center(1.3)).pack(side="right")
        self.canvas = tk.Canvas(main, bg=BG, highlightthickness=0, cursor="fleur")
        self.canvas.pack(fill="both", expand=True)
        legend = tk.Frame(main, bg=BG)
        legend.pack(fill="x", pady=9)
        legend_text = ("━ Берег   ┄ Край снимка (берег неизвестен)" if self.coastline.get("frontiers")
                       else "━ Берег · приближённо по изображению")
        self.label(legend, legend_text, MUTED, 9).pack(side="left")
        self.pointer_text = tk.StringVar(value="")
        tk.Label(legend, textvariable=self.pointer_text, fg=TEXT, bg=BG,
                 font=("DejaVu Sans", 9)).pack(side="right")
        footer = tk.Frame(self.root, bg=BG, padx=20, pady=10)
        footer.pack(fill="x")
        tk.Label(footer, textvariable=self.status, fg=MUTED, bg=BG,
                 font=("DejaVu Sans", 9)).pack(side="left")
        self.label(footer, "ЛКМ: перемещение   /   Колесо: масштаб   /   F: весь Тейват", MUTED, 9).pack(side="right")

    def _bindings(self):
        self.canvas.bind("<Configure>", self.resize)
        self.canvas.bind("<ButtonPress-1>", self.mouse_down)
        self.canvas.bind("<B1-Motion>", self.mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.mouse_up)
        self.canvas.bind("<Double-Button-1>", self.double_click)
        self.canvas.bind("<Button-3>", self.right_click)
        self.canvas.bind("<Motion>", self.pointer_move)
        self.canvas.bind("<MouseWheel>", self.wheel)
        self.canvas.bind("<Button-4>", self.wheel)
        self.canvas.bind("<Button-5>", self.wheel)
        self.root.bind("<Escape>", lambda e: self.cancel_add())
        self.root.bind("<Delete>", lambda e: self.delete_selected())
        self.root.bind("<Key-f>", lambda e: self.fit("teyvat"))
        self.root.bind("<Control-s>", lambda e: self.persist())
        self.root.bind("<Key-plus>", lambda e: self.zoom_center(1.3))
        self.root.bind("<Key-minus>", lambda e: self.zoom_center(1 / 1.3))

    def resize(self, event):
        self.view.width, self.view.height = event.width, event.height
        if not self.fitted and event.width > 100:
            self.fit("teyvat")
            self.fitted = True
        self.schedule_render()

    def fit(self, area):
        bounds = {"teyvat": (-10_800, -10_000, 10_800, 10_000),
                  "planet": WORLD_BOUNDS, "ocean": (10_000, -10_000, 30_000, 10_000)}
        self.view.fit(bounds[area])
        self.schedule_render()

    def zoom_center(self, factor):
        self.view.zoom(self.view.width / 2, self.view.height / 2, factor)
        self.schedule_render()

    def wheel(self, event):
        direction = 1 if getattr(event, "num", 0) == 4 or getattr(event, "delta", 0) > 0 else -1
        self.view.zoom(event.x, event.y, 1.2 ** direction)
        self.schedule_render()
        return "break"

    def mouse_down(self, event):
        self.press = (event.x, event.y)
        self.last_mouse = self.press
        self.dragged = False

    def mouse_drag(self, event):
        if self.press is None:
            return
        if math.hypot(event.x - self.press[0], event.y - self.press[1]) > 4:
            self.dragged = True
        if self.dragged:
            self.view.pan(event.x - self.last_mouse[0], event.y - self.last_mouse[1])
            self.schedule_render()
        self.last_mouse = (event.x, event.y)

    def mouse_up(self, event):
        if self.press is None:
            return
        if not self.dragged:
            hit = self.hit_marker(event.x, event.y)
            if hit:
                self.select(hit["id"])
            elif self.add_mode:
                self.add_at(event.x, event.y)
        self.press = None

    def double_click(self, event):
        self.press = None
        if not self.hit_marker(event.x, event.y):
            self.add_at(event.x, event.y)
        return "break"

    def right_click(self, event):
        marker = self.hit_marker(event.x, event.y)
        if marker:
            self.select(marker["id"])
            menu = tk.Menu(self.root, tearoff=False)
            menu.add_command(label="Переименовать", command=self.rename_selected)
            menu.add_command(label="Удалить", command=self.delete_selected)
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

    def hit_marker(self, sx, sy):
        for marker in reversed(self.markers):
            px, py = self.view.screen(marker["x"], marker["y"])
            if math.hypot(px - sx, py - sy) < 13:
                return marker
        return None

    def pointer_move(self, event):
        x, y = self.view.world(event.x, event.y)
        if -10_000 <= x <= 30_000 and -10_000 <= y <= 10_000:
            lat, lon = to_latlon(x, y)
            self.pointer_text.set(f"{abs(lat):.2f}° {'с.ш.' if lat >= 0 else 'ю.ш.'}  "
                                  f"{abs(lon):.2f}° {'в.д.' if lon >= 0 else 'з.д.'}")
        else:
            self.pointer_text.set("За пределами проекции")

    def toggle_add(self):
        self.add_mode = not self.add_mode
        self.add_button.configure(text="Отмена · Esc" if self.add_mode else "+  Поставить метку")
        self.canvas.configure(cursor="crosshair" if self.add_mode else "fleur")
        self.status.set("Щёлкните по карте, чтобы поставить метку" if self.add_mode else "Готово")

    def cancel_add(self):
        if self.add_mode:
            self.toggle_add()

    def add_at(self, sx, sy):
        if len(self.markers) >= 1000:
            messagebox.showinfo("Метки", "В прототипе поддерживается до 1000 меток", parent=self.root)
            return
        x, y = self.view.world(sx, sy)
        if not (-10_000 <= x <= 30_000 and -10_000 <= y <= 10_000):
            self.status.set("Выберите точку внутри прямоугольника планеты")
            return
        name = simpledialog.askstring("Новая метка", "Название (до 100 символов):",
                                      initialvalue=f"Метка {len(self.markers) + 1}", parent=self.root)
        if name is None:
            return
        name = name.strip()
        if not name or len(name) > 100:
            messagebox.showerror("Название", "Введите от 1 до 100 символов", parent=self.root)
            return
        marker = {"id": str(uuid.uuid4()), "name": name, "x": x, "y": y}
        self.markers.append(marker)
        self.cancel_add()
        self.select(marker["id"])
        self.persist()

    def selected_marker(self):
        return next((m for m in self.markers if m["id"] == self.selected), None)

    def select(self, ident):
        self.selected = ident
        self.refresh_list()
        self.schedule_render()

    def tree_select(self, event):
        chosen = self.tree.selection()
        if chosen and chosen[0] != self.selected:
            self.select(chosen[0])

    def refresh_list(self):
        origin = self.selected_marker()
        self.tree.delete(*self.tree.get_children())
        if origin:
            self.selected_text.set(origin["name"])
            lat, lon = to_latlon(origin["x"], origin["y"])
            self.coord_text.set(f"φ {lat:+.2f}°   λ {lon:+.2f}°")
        else:
            self.selected_text.set("Выберите точку отсчёта")
            self.coord_text.set("Щёлкните по метке на карте или в списке")
        ordered = sorted(self.markers, key=lambda m: distance_km((origin["x"], origin["y"]),
                         (m["x"], m["y"])) if origin else m["name"].casefold())
        for m in ordered:
            value = "точка отсчёта" if m == origin else (
                km(distance_km((origin["x"], origin["y"]), (m["x"], m["y"]))) if origin else "—")
            self.tree.insert("", "end", iid=m["id"], values=(m["name"], value))
        if origin:
            self.tree.selection_set(origin["id"])

    def rename_selected(self):
        marker = self.selected_marker()
        if not marker:
            return
        name = simpledialog.askstring("Название метки", "Новое название:",
                                      initialvalue=marker["name"], parent=self.root)
        if name is None:
            return
        if not name.strip() or len(name.strip()) > 100:
            messagebox.showerror("Название", "Введите от 1 до 100 символов", parent=self.root)
            return
        marker["name"] = name.strip()
        self.refresh_list()
        self.schedule_render()
        self.persist()

    def delete_selected(self):
        if not self.selected_marker():
            return
        self.markers = [m for m in self.markers if m["id"] != self.selected]
        self.select(None)
        self.persist()

    def focus_selected(self):
        marker = self.selected_marker()
        if marker:
            self.view.cx, self.view.cy = marker["x"], marker["y"]
            self.schedule_render()

    def load_demo(self):
        # Illustrative positions in this arbitrary planetary projection, not official POIs.
        demo = self.coastline.get("demo_markers", [])
        existing = {m["name"] for m in self.markers}
        for name, x, y in demo:
            if name not in existing and len(self.markers) < 1000:
                self.markers.append({"id": str(uuid.uuid4()), "name": name, "x": x, "y": y})
        self.select(self.markers[0]["id"] if self.markers else None)
        self.persist()

    def persist(self):
        try:
            save_markers(self.markers_path, self.markers)
            self.dirty = False
            self.status.set(f"{len(self.markers)} меток · сохранено в {self.markers_path}")
            return True
        except (OSError, ValueError) as exc:
            self.dirty = True
            self.status.set(f"Не удалось сохранить метки: {exc}")
            return False

    def import_markers(self):
        path = filedialog.askopenfilename(title="Импорт меток", filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            markers = load_markers(path)
        except (OSError, ValueError, UnicodeError) as exc:
            messagebox.showerror("Ошибка импорта", str(exc), parent=self.root)
            return
        if self.markers and not messagebox.askyesno("Импорт меток", "Заменить текущие метки импортированными?",
                                                   parent=self.root):
            return
        self.markers = markers
        self.select(markers[0]["id"] if markers else None)
        self.persist()

    def export_markers(self):
        path = filedialog.asksaveasfilename(title="Экспорт меток", defaultextension=".json",
                                          initialfile="teyvat-markers.json", filetypes=[("JSON", "*.json")])
        if path:
            try:
                save_markers(path, self.markers)
                self.status.set(f"Экспортировано: {path}")
            except (OSError, ValueError) as exc:
                messagebox.showerror("Ошибка экспорта", str(exc), parent=self.root)

    def export_distances(self):
        origin = self.selected_marker()
        if not origin:
            messagebox.showinfo("Расстояния", "Сначала выберите точку отсчёта", parent=self.root)
            return
        path = filedialog.asksaveasfilename(title="Экспорт расстояний", defaultextension=".csv",
                                          initialfile="distances.csv", filetypes=[("CSV", "*.csv")])
        if path:
            try:
                with Path(path).open("w", encoding="utf-8-sig", newline="") as f:
                    writer = csv.writer(f, delimiter=";")
                    writer.writerow(["От", "До", "Расстояние по сфере, км"])
                    for marker in self.markers:
                        if marker != origin:
                            # A leading apostrophe prevents spreadsheet formula execution in names.
                            names = ["'" + m["name"] if m["name"].startswith(("=", "+", "-", "@"))
                                     else m["name"] for m in (origin, marker)]
                            writer.writerow([*names, f"{distance_km((origin['x'], origin['y']), (marker['x'], marker['y'])):.3f}"])
                self.status.set(f"Расстояния экспортированы: {path}")
            except OSError as exc:
                messagebox.showerror("Ошибка экспорта", str(exc), parent=self.root)

    def schedule_render(self):
        if self.pending_render is None:
            self.pending_render = self.root.after(16, self.render)

    def render(self):
        if self.pending_render is not None:
            self.root.after_cancel(self.pending_render)
        self.pending_render = None
        c, v = self.canvas, self.view
        c.delete("all")
        x1, y1 = v.screen(WORLD_BOUNDS[0], WORLD_BOUNDS[1])
        x2, y2 = v.screen(WORLD_BOUNDS[2], WORLD_BOUNDS[3])
        c.create_rectangle(x1, y1, x2, y2, fill=OCEAN, outline="#304957")
        if self.show_grid.get():
            step = 30 if v.scale < .07 else (10 if v.scale < .3 else 2)
            for lon in range(-90, 271, step):
                x = v.screen(lon * KM_PER_DEGREE, 0)[0]
                c.create_line(x, y1, x, y2, fill="#244352", dash=(2, 7))
            for lat in range(-90, 91, step):
                y = v.screen(0, -lat * KM_PER_DEGREE)[1]
                c.create_line(x1, y, x2, y, fill="#244352", dash=(2, 7))
        # Hemisphere boundary is a meridian, not an arbitrary distance threshold.
        x = v.screen(10_000, 0)[0]
        c.create_line(x, y1, x, y2, fill="#47606a", dash=(6, 8))
        for ring in self.coastline["polygons"]:
            points = [v.screen(*p) for p in ring]
            xs, ys = zip(*points)
            if max(xs) < 0 or min(xs) > v.width or max(ys) < 0 or min(ys) > v.height:
                continue
            c.create_polygon(*[n for p in points for n in p], fill=LAND, outline=COAST, width=1.2)
        for segment in self.coastline.get("frontiers", []):
            coords = [n for p in segment for n in v.screen(*p)]
            c.create_line(*coords, fill=LAND, width=3)
            c.create_line(*coords, fill="#8a9992", width=1, dash=(3, 4))
        for x, title in ((0, "Т Е Й В А Т"), (20_000, "О К Е А Н")):
            px, py = v.screen(x, -9500)
            c.create_text(px, py, text=title, fill="#77959a", font=("DejaVu Sans", 12))
        if self.show_labels.get():
            for text, x, y in self.coastline.get("region_labels", []):
                c.create_text(*v.screen(x, y), text=text, fill="#bdc4ae", font=("DejaVu Sans", 9))
        origin = self.selected_marker()
        if origin:
            for m in self.markers:
                if m == origin:
                    continue
                a, b = (origin["x"], origin["y"]), (m["x"], m["y"])
                paths = great_circle(a, b, steps=64)
                for path in paths:
                    if len(path) > 1:
                        c.create_line(*[n for p in path for n in v.screen(*p)],
                                      fill=GOLD, width=1.3, dash=(5, 5))
                # Label on the largest visible path segment, away from point icons.
                path = max(paths, key=len)
                if path:
                    sx, sy = v.screen(*path[len(path) // 2])
                    self.canvas_label(sx, sy, km(distance_km(a, b)))
        for index, m in enumerate(self.markers, 1):
            sx, sy = v.screen(m["x"], m["y"])
            if not (-150 < sx < v.width + 150 and -60 < sy < v.height + 60):
                continue
            active = m == origin
            if active:
                c.create_oval(sx - 14, sy - 14, sx + 14, sy + 14, outline=GOLD, width=1)
            c.create_oval(sx - 8, sy - 8, sx + 8, sy + 8,
                          fill=GOLD if active else "#c5dcd1", outline=BG, width=2)
            c.create_text(sx, sy, text=str(index), fill=BG, font=("DejaVu Sans", 7, "bold"))
            c.create_text(sx + 15, sy - 15, text=m["name"], fill=GOLD if active else TEXT,
                          font=("DejaVu Sans", 10), anchor="w")
        self.draw_scale()

    def canvas_label(self, x, y, text):
        c = self.canvas
        label = c.create_text(x, y, text=text, fill=GOLD, font=("DejaVu Sans", 9))
        bx1, by1, bx2, by2 = c.bbox(label)
        bg = c.create_rectangle(bx1 - 6, by1 - 4, bx2 + 6, by2 + 4, fill=BG, outline="")
        c.tag_lower(bg, label)

    def draw_scale(self):
        # A horizontal equirectangular scale varies with latitude. Compute locally.
        v, c = self.view, self.canvas
        x, y = 28, v.height - 35
        _, wy = v.world(x, y)
        if not -10_000 < wy < 10_000:
            wy = max(-9900, min(9900, v.cy))
        width_px = 140
        value = distance_km((0, wy), (width_px / v.scale, wy))
        c.create_rectangle(x - 12, y - 31, x + 195, y + 17, fill=BG, outline="")
        c.create_line(x, y, x + width_px, y, fill=TEXT, width=2)
        for sx in (x, x + width_px):
            c.create_line(sx, y - 5, sx, y + 3, fill=TEXT)
        lat = -wy / KM_PER_DEGREE
        c.create_text(x, y - 17, anchor="w", text=f"≈ {km(value)} · φ {lat:+.0f}°",
                      fill=TEXT, font=("DejaVu Sans", 9))

    def help(self):
        messagebox.showinfo("Управление и масштаб", "Перетащите карту левой кнопкой мыши.\n"
            "Колесо приближает карту к курсору.\n"
            "Двойной щелчок или «Поставить метку» — новая точка.\n"
            "Щелчок по метке — расстояния до всех остальных.\n"
            "Правый щелчок — имя и удаление. Delete — удалить.\n"
            "F — весь Тейват. Esc — отмена установки. Ctrl+S — сохранить.\n\n"
            "Ширина Тейвата = 20 000 км по экватору.\n"
            "Окружность сферы = 40 000 км. Второе полушарие — океан.\n"
            "Расстояния — кратчайшие дуги большого круга, без учёта рельефа.\n"
            "Проекция искажает размеры у полюсов; зум не меняет расстояния.\n\n"
            "Контуры извлечены из предоставленной карты 1024×1024.\n"
            "Использован уточнённый рисунок с чёрными контурами на белом фоне.\n"
            "Замкнутые области выделены без расширения штрихов и ручных поправок.\n"
            "Погрешность в несколько пикселей может составлять десятки километров.\n"
            "Демо-метки и подписи регионов расположены приблизительно.", parent=self.root)

    def close(self):
        if self.dirty and not self.persist():
            if not messagebox.askyesno("Метки не сохранены", "Закрыть приложение без сохранения изменений?",
                                       parent=self.root):
                return
        if self.pending_render is not None:
            self.root.after_cancel(self.pending_render)
            self.pending_render = None
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--markers", type=Path, help="Путь к JSON меток (по умолчанию в домашней папке)")
    parser.add_argument("--demo", action="store_true", help="Добавить пример меток, если список пуст")
    args = parser.parse_args()
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"Не удалось открыть графическое окно: {exc}\nЗапустите приложение на компьютере с рабочим столом.",
              file=sys.stderr)
        return 1
    AtlasApp(root, markers_path=args.markers, demo=args.demo)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
