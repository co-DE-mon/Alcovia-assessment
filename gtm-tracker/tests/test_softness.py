"""The dashboard's colours are soft: muted chart hues, a light theme, nothing saturated. Colours are checked in OKLCH, the space the dataviz validator uses."""
import math
import tomllib

import ui
from tests.conftest import ROOT
from views import charts


def oklch(hex_color):
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lin = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = lin(r), lin(g), lin(b)
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s
    a = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s
    bb = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s
    return L, math.hypot(a, bb)


def test_every_series_colour_is_muted_but_still_reads_as_a_hue():
    for color in charts.SERIES:
        lightness, chroma = oklch(color)
        assert 0.60 <= lightness <= 0.77, (color, lightness)       # lighter than the old saturated set (blue was 0.57); 0.77 is the validator's ceiling
        assert 0.10 <= chroma <= 0.16, (color, chroma)             # 0.10 is the validator's floor; above 0.16 is the loud end


def test_the_series_palette_is_the_validated_soft_set():
    assert charts.SERIES == ["#6b97d4", "#e8845c", "#38aea6", "#d4a038", "#d98ab0", "#74a468"]


def test_the_meter_fill_matches_the_first_series_colour():
    assert charts.SERIES[0] in ui.CSS


def test_streamlit_theme_is_light_and_soft_so_native_widgets_do_not_show_default_red_or_dark_blue():
    theme = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text())["theme"]
    assert theme["base"] == "light" and theme["primaryColor"] == charts.SERIES[0]
    assert theme["backgroundColor"] == "#f4f6fa" and theme["secondaryBackgroundColor"] == "#eaeef5" and theme["textColor"] == "#2a3a4d"


def test_bar_labels_show_three_significant_figures_not_a_long_decimal():
    assert charts.label_format("~s") == ".3~s"
    assert charts.label_format(",") == ","
