"""Sphinx extension rendering SheepText diagrams as inline SVG.

The ``.. sheeptext::`` directive pipes its body (or a referenced file) to the
``sheeptext render`` CLI on stdin and inlines the SVG it writes to stdout.
Render failures are hard build errors carrying the CLI diagnostic; a missing
binary fails the build with an actionable message. See README.md for setup.
"""

from __future__ import annotations

import html
import subprocess
from typing import Any

from docutils import nodes
from docutils.parsers.rst import directives
from sphinx.application import Sphinx
from sphinx.config import Config
from sphinx.errors import SphinxError
from sphinx.util import i18n, logging
from sphinx.util.docutils import SphinxDirective
from sphinx.writers.html import HTMLTranslator

__version__ = "0.2.0"

logger = logging.getLogger(__name__)


class SheepTextError(SphinxError):
    category = "SheepText error"


class sheeptext(nodes.General, nodes.Inline, nodes.Element):
    pass


class SheepText(SphinxDirective):
    """Directive to insert SheepText markup rendered as inline SVG.

    Example::

        .. sheeptext::
           :alt: Client sends a request to the server

           box "Client"
           arrow right
           box "Server"

    An optional single argument names a ``.sheeptext`` source file instead of
    inline content.
    """

    has_content = True
    required_arguments = 0
    optional_arguments = 1
    final_argument_whitespace = True
    option_spec = {
        "alt": directives.unchanged,
        "name": directives.unchanged,
    }

    def run(self) -> list[nodes.Node]:
        if self.arguments and self.content:
            return [
                self.state.document.reporter.warning(
                    "sheeptext directive cannot have both content and a filename argument",
                    line=self.lineno,
                )
            ]
        if self.arguments:
            fn = i18n.search_image_for_language(self.arguments[0], self.env)
            relfn, absfn = self.env.relfn2path(fn)
            self.env.note_dependency(relfn)
            try:
                with open(absfn, encoding="utf-8") as fp:
                    sheeptext_code = fp.read()
            except (OSError, UnicodeDecodeError) as err:
                # Authoring-time typo: warning-level. The site build runs
                # sphinx-build -W, which still makes this fatal there
                # (task-00000265 review M1).
                return [
                    self.state.document.reporter.warning(
                        f'SheepText file "{fn}" cannot be read: {err}',
                        line=self.lineno,
                    )
                ]
        else:
            sheeptext_code = "\n".join(self.content)

        node = sheeptext(self.block_text, **self.options)
        node["sheeptext"] = sheeptext_code
        # Source location so render errors can report docname:line.
        self.set_source_info(node)
        self.add_name(node)
        return [node]


def _render_sheeptext(config: Config, code: str, location: str) -> str:
    binary: str = config.sheeptext_binary
    command = [binary, "render"]
    try:
        # Explicit UTF-8: text=True alone uses the locale encoding, which
        # breaks non-ASCII sources on LANG=C runners.
        proc = subprocess.run(
            command,
            input=code,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except OSError as err:
        raise SheepTextError(
            f"SheepText binary {binary!r} could not be run ({err}). "
            "Install the sheeptext CLI on PATH or point the sheeptext_binary "
            "config value in conf.py at the executable."
        ) from err
    if proc.returncode != 0:
        raise SheepTextError(
            f"sheeptext render failed for {location} "
            f"(exit {proc.returncode}):\n{proc.stderr.strip()}"
        )
    svg = proc.stdout.lstrip()
    if not svg.startswith("<svg"):
        # Guards a future CLI banner/XML-prolog change: only a bare <svg>
        # root is valid to inline into HTML5.
        raise SheepTextError(
            f"sheeptext render for {location} produced unexpected output "
            f"(expected inline SVG starting with '<svg'): {svg[:80]!r}"
        )
    return svg


def html_visit_sheeptext(self: HTMLTranslator, node: sheeptext) -> None:
    location = f"{node.source}:{node.line}" if node.source else "<unknown source>"
    # Raise instead of appending: SheepTextError subclasses SphinxError, which
    # aborts the build with the diagnostic (hard failure, never a skipped
    # diagram).
    svg = _render_sheeptext(self.builder.config, node["sheeptext"], location)
    alt = node.get("alt")
    if alt:
        opening = (
            f'<div class="sheeptext-diagram" role="img" '
            f'aria-label="{html.escape(alt, quote=True)}">'
        )
    else:
        opening = '<div class="sheeptext-diagram">'
    self.body.append(opening + svg + "</div>\n")
    raise nodes.SkipNode


def unsupported_visit_sheeptext(self: Any, node: sheeptext) -> None:
    logger.warning("sheeptext: unsupported output format (node skipped)")
    raise nodes.SkipNode


def setup(app: Sphinx) -> dict[str, Any]:
    app.add_config_value("sheeptext_binary", "sheeptext", "env", types=(str,))
    app.add_node(
        sheeptext,
        html=(html_visit_sheeptext, None),
        latex=(unsupported_visit_sheeptext, None),
        man=(unsupported_visit_sheeptext, None),
        texinfo=(unsupported_visit_sheeptext, None),
        text=(unsupported_visit_sheeptext, None),
    )
    app.add_directive("sheeptext", SheepText)

    # Safe: rendering is subprocess-local, no builder/env mutation.
    return {
        "version": __version__,
        "env_version": 1,
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
