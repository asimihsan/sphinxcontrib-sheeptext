# sphinxcontrib-sheeptext

Render [SheepText](https://sheeptext.com) diagrams as inline SVG in Sphinx
documentation. Each `.. sheeptext::` directive body is piped to the
`sheeptext render` CLI on stdin at build time; the SVG written to stdout is
inlined into the page, so every published diagram is validated against the
current SheepText parser on every build.

## Install

```bash
pip install sphinxcontrib-sheeptext   # or a pinned path/git dependency
```

You also need the `sheeptext` CLI (Rust; package `sheeptext-cli`, installed
binary name `sheeptext`).

## Setup

```python
# conf.py
extensions = ["sphinxcontrib_sheeptext"]

# Optional: defaults to "sheeptext" resolved via PATH. Point at an explicit
# executable when the CLI is not on PATH (e.g. a workspace build).
sheeptext_binary = "/path/to/sheeptext"
```

## Usage

```rst
.. sheeptext::
   :alt: start leads to end

   box "start"
   arrow right
   box "end"
```

Or reference a source file (path relative to the document):

```rst
.. sheeptext:: diagrams/flow.sheeptext
```

Options:

- `alt` — accessibility text; emitted as `role="img"` + `aria-label` on the
  wrapper `<div class="sheeptext-diagram">` that surrounds every diagram
  (style/scale diagrams via that class in your theme CSS).
- `name` — standard docutils cross-reference name.

## Failure behavior

- A diagram that fails to render **fails the build** with a `SheepText error`
  containing the CLI's stderr diagnostic and the `source:line` location.
- A missing/unrunnable binary fails the build with an actionable message
  naming the `sheeptext_binary` config value.
- An unreadable file argument is a docutils *warning* (an authoring-time
  typo); run `sphinx-build -W` to make that fatal too, as sheeptext.com's
  site build does.

## Tests

```bash
uv sync --all-groups
SHEEPTEXT_BINARY=/path/to/sheeptext uv run pytest
```

Tests run against the real CLI: `SHEEPTEXT_BINARY` first, then PATH;
binary-dependent tests skip with an actionable message when neither is
available.
