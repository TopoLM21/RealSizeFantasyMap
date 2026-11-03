"""Integration checks with a real Tk window; skipped without DISPLAY on Linux."""

import os
import json
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
        self.places_path = Path(self.tmp.name) / "places.json"
        catalog = json.loads((Path(__file__).resolve().parents[1] / "data/places.json").read_text(encoding="utf-8"))
        for place in catalog["places"]:
            if place["id"] == "nasha":
                place["source_pixel"] = None
                place["position_accuracy"] = "unplaced"
        self.places_path.write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
        self.root = tk.Tk()
        self.app = AtlasApp(self.root, markers_path=self.path, places_path=self.places_path)
        self.root.update()

    def tearDown(self):
        with patch("app.messagebox.askyesnocancel", return_value=False):
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
            if widget is self.app.poi_editor_bar and not self.app.edit_places.get():
                return []
            result = [widget] if isinstance(widget, tk.Button) else []
            for child in widget.winfo_children():
                result.extend(buttons(child))
            return result
        self.assertTrue(all(b.winfo_ismapped() and b.winfo_height() >= 20 for b in buttons(self.root)))

    def test_place_becomes_measurement_marker_without_duplicates(self):
        place = next(p for p in self.app.places if p["id"] == "mondstadt")
        self.app.add_place_marker(place)
        self.app.add_place_marker(place)
        self.assertEqual(len(self.app.markers), 1)
        self.assertEqual(load_markers(self.path)[0]["name"], "Мондштадт")
        unplaced = next(p for p in self.app.places if p["x"] is None)
        self.app.add_place_marker(unplaced)
        self.assertEqual(len(self.app.markers), 1)
        self.assertTrue(self.app.add_mode)
        self.assertEqual(self.app.pending_place_name, unplaced["name"])
        self.app.cancel_add()

    def test_smoothing_switch_and_tk_fallback_render(self):
        from unittest.mock import patch
        self.app.render()
        self.assertTrue(self.app.smooth_coast.get())
        self.app.smooth_coast.set(False)
        self.app.render()
        self.assertTrue(any(self.app.canvas.type(i) == "polygon" for i in self.app.canvas.find_all()))
        self.app.smooth_coast.set(True)
        with patch("map_renderer.Image", None):
            self.app.render()
        self.app.show_places_dialog("mondstadt")
        self.root.update()

    def enable_editor(self):
        self.app.edit_places.set(True)
        self.app.toggle_place_editor()
        self.root.update()

    def drag_poi(self, dx=60, dy=35):
        place = self.app.place_by_id("mondstadt")
        x, y = map(round, self.app.view.screen(place["x"], place["y"]))
        self.app.canvas.event_generate("<ButtonPress-1>", x=x, y=y)
        self.app.canvas.event_generate("<B1-Motion>", x=x+dx, y=y+dy)
        self.app.canvas.event_generate("<ButtonRelease-1>", x=x+dx, y=y+dy)
        self.root.update()

    def test_poi_drag_is_opt_in_and_does_not_pan_or_move_user_markers(self):
        place = self.app.place_by_id("mondstadt")
        self.app.add_place_marker(place)
        marker = dict(self.app.markers[0])
        before = self.app.place_state(place)
        file_before = self.places_path.read_bytes()
        self.enable_editor()
        center = (self.app.view.cx, self.app.view.cy)
        self.drag_poi()
        self.assertNotEqual(self.app.place_state(place), before)
        self.assertEqual((self.app.view.cx, self.app.view.cy), center)
        self.assertEqual(self.app.markers[0], marker)
        self.assertEqual(self.places_path.read_bytes(), file_before)
        self.assertIn("mondstadt", self.app.poi_dirty_ids)
        self.app.undo_place_edit()
        self.assertEqual(self.app.place_state(place), before)
        self.assertFalse(self.app.poi_dirty_ids)

    def test_catalog_save_reloads_moved_poi_and_ctrl_s_does_not_create_markers(self):
        from places import load_places
        self.enable_editor()
        self.drag_poi()
        expected = self.app.place_state(self.app.place_by_id("mondstadt"))
        self.app.save_shortcut()
        restored = next(p for p in load_places(self.places_path, self.app.coastline) if p["id"] == "mondstadt")
        self.assertEqual(self.app.place_state(restored), expected)
        self.assertFalse(self.app.poi_dirty_ids)
        self.assertFalse(self.path.exists())

    def test_unplaced_poi_is_added_to_catalog_without_creating_a_user_marker(self):
        from places import load_places
        place = next(p for p in self.app.places if p["x"] is None)
        self.app.begin_place_position(place["id"])
        self.root.update()
        self.app.canvas.event_generate("<ButtonPress-1>", x=400, y=350)
        self.app.canvas.event_generate("<ButtonRelease-1>", x=400, y=350)
        self.root.update()
        self.assertIsNotNone(place["source_pixel"])
        self.assertFalse(self.app.markers)
        self.assertTrue(self.app.save_places_edits())
        reloaded = next(p for p in load_places(self.places_path, self.app.coastline) if p["id"] == place["id"])
        self.assertEqual(reloaded["source_pixel"], place["source_pixel"])
        self.assertEqual(reloaded["position_accuracy"], "user_adjusted")

    def test_normal_mode_drag_pans_without_editing_places(self):
        before = self.app.place_state(self.app.place_by_id("mondstadt"))
        center = (self.app.view.cx, self.app.view.cy)
        self.drag_poi()
        self.assertEqual(self.app.place_state(self.app.place_by_id("mondstadt")), before)
        self.assertNotEqual((self.app.view.cx, self.app.view.cy), center)

    def test_editor_shows_minor_pois_and_cancelling_close_keeps_unsaved_work(self):
        self.enable_editor()
        self.app.render()
        self.assertTrue(any(p["kind"] == "town" for p in self.app.visible_places))
        self.drag_poi()
        with patch("app.messagebox.askyesnocancel", return_value=None):
            self.app.close()
        self.assertTrue(self.root.winfo_exists())
        self.assertTrue(self.app.poi_dirty_ids)


if __name__ == "__main__":
    unittest.main()
