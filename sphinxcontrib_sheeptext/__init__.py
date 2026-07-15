"""sphinxcontrib-sheeptext: render SheepText diagrams as inline SVG.

Add ``"sphinxcontrib_sheeptext"`` to ``extensions`` in ``conf.py``.
"""

from sphinxcontrib_sheeptext.sphinxcontrib_sheeptext import (
    SheepText,
    SheepTextError,
    __version__,
    setup,
)

__all__ = ["SheepText", "SheepTextError", "__version__", "setup"]
