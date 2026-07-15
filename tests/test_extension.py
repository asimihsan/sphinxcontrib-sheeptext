"""End-to-end extension tests against the real sheeptext CLI.

The binary resolves from the SHEEPTEXT_BINARY env var first (site CI exports
the freshly built workspace binary), then PATH. Absent both, binary-dependent
tests skip with an actionable message -- the missing-binary failure test
always runs.
"""

import os
import re
import shutil
from pathlib import Path

import pytest
from sphinx.errors import SphinxError


def resolved_sheeptext_binary() -> str | None:
    override = os.environ.get("SHEEPTEXT_BINARY")
    if override:
        return override if Path(override).exists() else None
    return shutil.which("sheeptext")


requires_sheeptext = pytest.mark.skipif(
    resolved_sheeptext_binary() is None,
    reason=(
        "sheeptext binary not found: set SHEEPTEXT_BINARY to the built CLI "
        "(e.g. the monorepo's target/*/sheeptext) or put sheeptext on PATH"
    ),
)


@requires_sheeptext
@pytest.mark.sphinx("html", testroot="basic")
def test_inline_content_renders_svg_with_accessible_wrapper(app):
    app.build()
    out = (app.outdir / "index.html").read_text(encoding="utf-8")
    # Anchored: the SVG must sit inside OUR wrapper, not any theme SVG.
    assert re.search(r'class="sheeptext-diagram"[^>]*>\s*<svg', out)
    assert 'role="img"' in out
    assert 'aria-label="start leads to end"' in out


@requires_sheeptext
@pytest.mark.sphinx("html", testroot="file")
def test_file_argument_renders_svg(app):
    app.build()
    out = (app.outdir / "index.html").read_text(encoding="utf-8")
    assert re.search(r'class="sheeptext-diagram"[^>]*>\s*<svg', out)


@requires_sheeptext
@pytest.mark.sphinx("html", testroot="broken")
def test_render_failure_fails_build_with_cli_diagnostic_and_location(app):
    with pytest.raises(SphinxError) as excinfo:
        app.build()
    message = str(excinfo.value)
    # CLI diagnostic text is present verbatim (non-empty stderr), plus the
    # source location docname:line.
    assert "sheeptext render failed for" in message
    assert re.search(r"index\.rst:\d+", message)
    # CLI stderr diagnostic verbatim (stable substring of the parser error).
    assert "unknown command form" in message


@pytest.mark.sphinx("html", testroot="missing-binary")
def test_missing_binary_fails_build_actionably(app):
    with pytest.raises(SphinxError) as excinfo:
        app.build()
    message = str(excinfo.value)
    assert "/nonexistent/sheeptext-does-not-exist" in message
    assert "sheeptext_binary" in message
