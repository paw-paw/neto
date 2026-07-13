from __future__ import annotations

import json
import struct
from pathlib import Path

from streamlit.testing.v1 import AppTest

import app as app_module


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"


def test_design_assets_are_local_and_intact() -> None:
    logo = (ASSETS / "neto-logo.png").read_bytes()
    assert logo.startswith(b"\x89PNG\r\n\x1a\n")
    assert struct.unpack(">II", logo[16:24]) == (224, 224)

    font_names = (
        "JetBrainsMono-Regular.woff2",
        "JetBrainsMono-Medium.woff2",
        "DMSans-Regular-Medium.woff2",
    )
    for font_name in font_names:
        assert (ASSETS / "fonts" / font_name).read_bytes().startswith(b"wOF2")

    assert (ASSETS / "fonts" / "OFL-JetBrainsMono.txt").is_file()
    assert (ASSETS / "fonts" / "OFL-DMSans.txt").is_file()
    tokens = json.loads((ASSETS / "design" / "tokens.json").read_text("utf-8"))
    assert tokens["color"]["cosmic-void"]["$value"] == "#06051d"
    assert tokens["color"]["specimen-green"]["$value"] == "#00bc7d"


def test_theme_embeds_fonts_without_external_runtime_requests() -> None:
    stylesheet = app_module._load_app_styles()

    assert stylesheet.startswith("<style>")
    assert stylesheet.endswith("</style>")
    assert stylesheet.count("data:font/woff2;base64,") == 3
    assert "__JETBRAINS_MONO_REGULAR__" not in stylesheet
    assert "fonts.googleapis.com" not in stylesheet
    assert "--color-cosmic-void: #06051d" in stylesheet
    assert "--neto-font-mono" in stylesheet
    assert ".neto-brand .neto-brand__title" in stylesheet
    assert ".neto-brand__logo" in stylesheet
    assert "@media (max-width: 1100px), (max-aspect-ratio: 4/3)" in stylesheet
    assert "@media (max-width: 640px)" in stylesheet
    assert "width: 72px" in stylesheet


def test_streamlit_renders_branded_header_and_keeps_initial_controls() -> None:
    app_test = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
    app_test.run()

    assert not app_test.exception
    markup = "\n".join(item.value for item in app_test.markdown)
    assert 'class="neto-brand"' in markup
    assert 'class="neto-brand__logo"' in markup
    assert "NETO v0" in markup
    assert "Normalized Esports Tournament Output" in markup
    assert app_test.button(key="run_parse").disabled
