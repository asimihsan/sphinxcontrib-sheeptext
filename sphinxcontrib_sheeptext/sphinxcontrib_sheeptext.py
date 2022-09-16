import codecs
import re
import os
import posixpath
import subprocess
import sys
from os import path
from pathlib import Path
from subprocess import CalledProcessError, check_output
from typing import Any, Dict, List, Tuple

import sphinx
from docutils import nodes
from docutils.nodes import Node
from docutils.parsers.rst import directives
from sphinx.application import Sphinx
from sphinx.errors import SphinxError
from sphinx.locale import __
from sphinx.util import logging, sha1
from sphinx.util.docutils import SphinxDirective, SphinxTranslator
from sphinx.util import i18n
from sphinx.util.osutil import ensuredir
from sphinx.writers.html import HTMLTranslator
from sphinx.writers.latex import LaTeXTranslator

OPTION_FILENAME = "filename"

logger = logging.getLogger(__name__)


try:
    from PIL import Image
except ImportError:
    Image = None


class SheepTextError(SphinxError):
    category = "SheepText error"


def html_format(argument):
    format_values = list(_KNOWN_HTML_FORMATS.keys())
    return directives.choice(argument, format_values)


class SheepText(SphinxDirective):
    """Directive to insert SheepText markup

    Example::

        .. sheeptext::
           box "Client"
           arrow "(1)"
           box "Server"
    """

    has_content = True
    required_arguments = 0
    optional_arguments = 1
    final_argument_whitespace = True  # allow whitespace in arguments[-1]
    option_spec = {
        "alt": directives.unchanged,
        "caption": directives.unchanged,
        "height": directives.length_or_unitless,
        "html_format": html_format,
        "name": directives.unchanged,
        "scale": directives.percentage,
        "width": directives.length_or_percentage_or_unitless,
    }

    def run(self):
        warning = self.state.document.reporter.warning
        env = self.state.document.settings.env
        if self.arguments and self.content:
            return [
                warning(
                    "sheeptext directive cannot have both content and " "a filename argument",
                    line=self.lineno,
                )
            ]
        if self.arguments:
            fn = i18n.search_image_for_language(self.arguments[0], env)
            relfn, absfn = env.relfn2path(fn)
            env.note_dependency(relfn)
            try:
                sheeptext_code = _read_utf8(absfn)
            except (IOError, UnicodeDecodeError) as err:
                return [warning('SheepText file "%s" cannot be read: %s' % (fn, err), line=self.lineno)]
        else:
            relfn = env.doc2path(env.docname, base=None)
            sheeptext_code = "\n".join(self.content)

        node = sheeptext(self.block_text, **self.options)
        node["sheeptext"] = sheeptext_code
        node["incdir"] = os.path.dirname(relfn)
        node["filename"] = os.path.split(relfn)[1]

        self.add_name(node)
        if "html_format" in self.options:
            node["html_format"] = self.options["html_format"]

        return [node]


class sheeptext(nodes.General, nodes.Inline, nodes.Element):
    pass


def render_sheeptext(self: SphinxTranslator, code: str) -> str:
    try:
        return subprocess.check_output(["sheeptext"], input=code, shell=True, text=True)
    except OSError:
        logger.warning(__("SheepText binary could not be run."))
        if not hasattr(self.builder, "_sheeptext_warned"):
            self.builder._sheeptext_warned = {}  # type: ignore
        self.builder._sheeptext_warned["python"] = True  # type: ignore
        return None, None
    except CalledProcessError as exc:
        raise SheepTextError(
            __("sheeptext exited with error:\n[stderr]\n%r\n" "[stdout]\n%r") % (exc.stderr, exc.stdout)
        )


def render_html(
    self: HTMLTranslator,
    node: sheeptext,
    code: str,
    imgcls: str = None,
) -> None:

    try:
        text = render_sheeptext(self, code)
    except SheepTextError as exc:
        logger.warning(__("python code %r: %s"), code, exc)
        raise nodes.SkipNode

    if imgcls:
        imgcls += " sheeptext"
    else:
        imgcls = "sheeptext"

    self.body.append(text)

    raise nodes.SkipNode


def html_visit_sheeptext(self: HTMLTranslator, node: sheeptext) -> None:
    render_html(self, node, node["sheeptext"])


def unsupported_visit_sheeptext(self, node: sheeptext):
    logger.warning("sheeptext: unsupported output format (node skipped)")
    raise nodes.SkipNode


def setup(app: Sphinx) -> Dict[str, Any]:
    app.add_node(
        sheeptext,
        html=(html_visit_sheeptext, None),
        latex=(unsupported_visit_sheeptext, None),
        man=(unsupported_visit_sheeptext, None),
        texinfo=(unsupported_visit_sheeptext, None),
        text=(unsupported_visit_sheeptext, None),
        confluence=(unsupported_visit_sheeptext, None),
        singleconfluence=(unsupported_visit_sheeptext, None),
    )
    app.add_directive("sheeptext", SheepText)

    return {"parallel_read_safe": True}


def _get_png_tag(self, fnames, node):
    refname, outfname = fnames["png"]
    alt = node.get("alt", node["uml"])

    # mimic StandaloneHTMLBuilder.post_process_images(). maybe we should
    # process images prior to html_vist.
    scale_attrs = [k for k in ("scale", "width", "height") if k in node]
    if scale_attrs and Image is None:
        logger.warning(
            (
                "sheeptext: unsupported scaling attributes: %s "
                "(install PIL or Pillow)" % ", ".join(scale_attrs)
            )
        )
    if not scale_attrs or Image is None:
        return '<img src="%s" alt="%s"/>\n' % (self.encode(refname), self.encode(alt))

    scale = node.get("scale", 100)
    styles = []

    # Width/Height
    vu = re.compile(r"(?P<value>\d+)\s*(?P<units>[a-zA-Z%]+)?")
    for a in ["width", "height"]:
        if a not in node:
            continue
        m = vu.match(node[a])
        if not m:
            raise SheepTextError("Invalid %s" % a)
        m = m.groupdict()
        w = int(m["value"])
        wu = m["units"] if m["units"] else "px"
        styles.append("%s: %s%s" % (a, w * scale / 100, wu))

    # Add physical size to assist rendering (defaults)
    if not styles:
        # the image may be corrupted if platuml isn't configured correctly,
        # which isn't a hard error.
        try:
            im = Image.open(outfname)
            im.load()
            styles.extend(
                "%s: %s%s" % (a, w * scale / 100, "px") for a, w in zip(["width", "height"], im.size)
            )
        except (IOError, OSError) as err:
            logger.warning("sheeptext: failed to get image size: %s" % err)

    return '<a href="%s"><img src="%s" alt="%s" style="%s"/>' "</a>\n" % (
        self.encode(refname),
        self.encode(refname),
        self.encode(alt),
        self.encode("; ".join(styles)),
    )


def _get_svg_style(fname):
    f = codecs.open(fname, "r", "utf-8")
    try:
        for l in f:
            m = re.search(r"<svg\b([^<>]+)", l)
            if m:
                attrs = m.group(1)
                break
        else:
            return
    finally:
        f.close()

    m = re.search(r'\bstyle=[\'"]([^\'"]+)', attrs)
    if not m:
        return
    return m.group(1)


def _get_svg_tag(self, fnames, node):
    refname, outfname = fnames["svg"]
    return "\n".join(
        [
            # copy width/height style from <svg> tag, so that <object> area
            # has enough space.
            '<object data="%s" type="image/svg+xml" style="%s">'
            % (self.encode(refname), _get_svg_style(outfname) or ""),
            _get_png_tag(self, fnames, node),
            "</object>",
        ]
    )


def _get_svg_img_tag(self, fnames, node):
    refname, outfname = fnames["svg"]
    alt = node.get("alt", node["uml"])
    return '<img src="%s" alt="%s"/>' % (self.encode(refname), self.encode(alt))


def _get_svg_obj_tag(self, fnames, node):
    refname, outfname = fnames["svg"]
    # copy width/height style from <svg> tag, so that <object> area
    # has enough space.
    return '<object data="%s" type="image/svg+xml" style="%s"></object>' % (
        self.encode(refname),
        _get_svg_style(outfname) or "",
    )


_KNOWN_HTML_FORMATS = {
    "png": (("png",), _get_png_tag),
    "svg": (("png", "svg"), _get_svg_tag),
    "svg_img": (("svg",), _get_svg_img_tag),
    "svg_obj": (("svg",), _get_svg_obj_tag),
}


def _read_utf8(filename):
    fp = codecs.open(filename, "rb", "utf-8")
    try:
        return fp.read()
    finally:
        fp.close()
