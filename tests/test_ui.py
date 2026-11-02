"""Integration checks with a real Tk window; skipped without DISPLAY on Linux."""

import os
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import AtlasApp
from storage import load_markers


@unittest.skipIf(sys.platform.startswith("linux") and not os.environ.get("DISPLAY"),
                 "A graphical display is required for UI checks")
class UITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "markers.json"
        self.root = tk.Tk()
        self.app = AtlasApp(self.root, markers_path=self.path)
        self.root.update()

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def add(self, name, sx=420, sy=300):
        with patch("app.simpledialog.askstring", return_value=name):
            self.app.add_at(sx, sy)
        self.root.update()

    def test_add_select_rename_delete_and_persist(self):
        self.add("Первая")
        self.add("Вторая", 600, 450)
        first, second = self.app.markers
        self.app.select(first["id"])
        self.root.update()
        self.assertIn("км", self.app.tree.item(second["id"], "values")[1])
        with patch("app.simpledialog.askstring", return_value="Новый порт"):
            self.app.rename_selected()
        self.assertEqual(load_markers(self.path)[0]["name"], "Новый порт")
        self.app.delete_selected()
        self.assertEqual(len(load_markers(self.path)), 1)
        self.assertIsNone(self.app.selected)

    def test_mouse_drag_does_not_create_marker_and_wheel_anchors(self):
        app = self.app
        app.toggle_add()
        app.canvas.event_generate("<ButtonPress-1>", x=400, y=300)
        app.canvas.event_generate("<B1-Motion>", x=470, y=320)
        app.canvas.event_generate("<ButtonRelease-1>", x=470, y=320)
        self.root.update()
        self.assertFalse(app.markers)
        before = app.view.world(300, 200)
        app.canvas.event_generate("<MouseWheel>", x=300, y=200, delta=120)
        self.root.update()
        for expected, got in zip(before, app.view.world(300, 200)):
            self.assertAlmostEqual(expected, got)

    def test_single_click_and_double_click_create_once(self):
        app = self.app
        app.toggle_add()
        with patch("app.simpledialog.askstring", return_value="Порт"):
            app.canvas.event_generate("<ButtonPress-1>", x=400, y=350)
            app.canvas.event_generate("<ButtonRelease-1>", x=400, y=350)
            self.root.update()
        self.assertEqual(len(app.markers), 1)
        # The second click of a double-click on the new marker must not duplicate it.
        app.double_click(SimpleNamespace(x=400, y=350))
        self.assertEqual(len(app.markers), 1)
        self.assertFalse(app.add_mode)

    def test_export_import_and_invalid_import_preserves_markers(self):
        self.add("Порт")
        export = Path(self.tmp.name) / "export.json"
        with patch("app.filedialog.asksaveasfilename", return_value=str(export)):
            self.app.export_markers()
        self.app.delete_selected()
        with patch("app.filedialog.askopenfilename", return_value=str(export)):
            self.app.import_markers()
        self.assertEqual(self.app.markers[0]["name"], "Порт")
        export.write_text('{"version":1,"markers":[{}]}')
        with patch("app.filedialog.askopenfilename", return_value=str(export)), \
                patch("app.messagebox.showerror") as error:
            self.app.import_markers()
        error.assert_called_once()
        self.assertEqual(self.app.markers[0]["name"], "Порт")

    def test_demo_and_all_controls_fit_small_window(self):
        self.root.geometry("1020x680")
        self.root.update()
        self.app.load_demo()
        self.root.update()
        self.app.render()
        self.assertEqual(len(self.app.markers), 4)
        self.app.sidebar_canvas.yview_moveto(1)
        self.root.update()
        self.assertAlmostEqual(self.app.sidebar_canvas.yview()[1], 1)
        # Every visible button must have received its requested vertical space.
        def buttons(widget):
            result = [widget] if isinstance(widget, tk.Button) else []
            for child in widget.winfo_children():
                result.extend(buttons(child))
            return result
        self.assertTrue(all(b.winfo_ismapped() and b.winfo_height() >= 20 for b in buttons(self.root)))


if __name__ == "__main__":
    unittest.main()
