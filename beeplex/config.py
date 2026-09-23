"""Process configuration. Importing this module never creates files."""

import os
from pathlib import Path

DEMO = os.getenv("BEEPLEX_DEMO") == "1" or os.getenv("BEEX_MOCK") == "1"
LLM_ENABLED = os.getenv("BEEPLEX_LLM") == "1" and not DEMO
DATA_DIR = (
    Path(os.getenv("BEEPLEX_DATA_DIR", str(Path.home() / ".beeplex")))
    .expanduser()
    .resolve()
)
if DEMO:
    DATA_DIR = DATA_DIR / "demo"
