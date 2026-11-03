"""Optional supersampled coastline rendering; Tk-only fallback stays available."""

try:
    from PIL import Image, ImageDraw, ImageTk
except ImportError:
    Image = ImageDraw = ImageTk = None


class CoastRenderer:
    def __init__(self):
        self.photo = None
        self.cache_key = None

    @property
    def antialias_available(self):
        return Image is not None

    def draw(self, canvas, viewport, polygons, fill, outline, antialias=True):
        if antialias and self.antialias_available:
            self._draw_image(canvas, viewport, polygons, fill, outline)
            return
        for ring in polygons:
            points = [viewport.screen(*p) for p in ring]
            xs, ys = zip(*points)
            if max(xs) < 0 or min(xs) > viewport.width or max(ys) < 0 or min(ys) > viewport.height:
                continue
            canvas.create_polygon(*[n for p in points for n in p], fill=fill,
                                  outline=outline, width=1.2)

    def _draw_image(self, canvas, view, polygons, fill, outline):
        width, height = max(1, int(view.width)), max(1, int(view.height))
        key = (width, height, view.cx, view.cy, view.scale, id(polygons), fill, outline)
        if key != self.cache_key:
            # Four samples per axis at ordinary window sizes; cap large-window memory.
            factor = max(1, min(4, int((16_000_000 / (width * height)) ** .5)))
            surface = Image.new("RGBA", (width * factor, height * factor), (0, 0, 0, 0))
            draw = ImageDraw.Draw(surface)
            for ring in polygons:
                points = [view.screen(*p) for p in ring]
                xs, ys = zip(*points)
                if max(xs) < -2 or min(xs) > width + 2 or max(ys) < -2 or min(ys) > height + 2:
                    continue
                scaled = [(x * factor, y * factor) for x, y in points]
                draw.polygon(scaled, fill=fill)
                draw.line(scaled, fill=outline, width=max(1, round(1.2 * factor)), joint="curve")
            if factor > 1:
                surface = surface.resize((width, height), Image.Resampling.LANCZOS)
            self.photo = ImageTk.PhotoImage(surface, master=canvas)
            self.cache_key = key
        canvas.create_image(0, 0, anchor="nw", image=self.photo)
