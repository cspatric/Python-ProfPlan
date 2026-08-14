"""Turn a generated activity into a printable handout.

The model writes Markdown: headings, GFM tables, block quotes, and LaTeX
between dollar signs. On screen that is rendered by the frontend; a teacher who
wants to hand it out needs the same thing on paper, laid out for A4 rather than
for a browser window.

The route is Markdown -> HTML -> PDF. ``markdown`` does the first step and
WeasyPrint the second, because the second is real CSS layout: page size, page
breaks that do not split a table row from its header, and a footer with page
numbers. Drawing the same document by hand with a PDF primitive library would
mean reimplementing all of that.

One honest limitation: the LaTeX the model sometimes writes is *not*
typeset. There is no formula engine here, and pretending otherwise would mean
silently dropping the parts that failed to parse. Instead the delimiters are
stripped and the expression is set in italics, so ``$x_{i,j}$`` reads as
*x_{i,j}* rather than as stray dollar signs.
"""

import re
from dataclasses import dataclass
from datetime import date

import markdown as markdown_lib

#: Inline math, `$...$`, with the delimiters not doubled (which would be a
#: display block) and no space right after the opening `$` (which is usually a
#: currency amount, "R$ 5,00", not a formula).
_INLINE_MATH = re.compile(r"(?<!\$)\$(?!\s)([^$\n]+?)(?<!\s)\$(?!\$)")

_STYLESHEET = """
@page {
    size: A4;
    margin: 2cm 1.8cm 2cm 1.8cm;
    @bottom-center {
        content: counter(page) " / " counter(pages);
        font-family: "DejaVu Sans", sans-serif;
        font-size: 8pt;
        color: #94a3b8;
    }
}

body {
    font-family: "DejaVu Sans", sans-serif;
    font-size: 10pt;
    line-height: 1.55;
    color: #262f3d;
}

/* Cover block: what the activity is, before what it says. */
.masthead { border-bottom: 2px solid #1e4fa3; padding-bottom: 12pt;
            margin-bottom: 18pt; }
.masthead .kicker { font-size: 8pt; letter-spacing: 0.08em; text-transform: uppercase;
                    color: #1e4fa3; font-weight: bold; }
.masthead h1 { font-size: 17pt; margin: 6pt 0 8pt 0; color: #101828; }
.masthead dl { margin: 0; font-size: 8.5pt; color: #667085; }
.masthead dt { display: inline; font-weight: bold; }
.masthead dd { display: inline; margin: 0 14pt 0 3pt; }

h1 { font-size: 14pt; margin: 18pt 0 8pt 0; color: #101828; }
h2 { font-size: 12pt; margin: 16pt 0 6pt 0; color: #101828; }
h3 { font-size: 10.5pt; margin: 14pt 0 5pt 0; color: #344054; }
/* A heading alone at the foot of a page is a heading on the wrong page. */
h1, h2, h3 { page-break-after: avoid; }

p { margin: 0 0 8pt 0; }
ul, ol { margin: 0 0 8pt 0; padding-left: 16pt; }
li { margin-bottom: 3pt; }

blockquote {
    margin: 10pt 0; padding: 8pt 12pt;
    border-left: 3pt solid #1e4fa3; background: #f4f7fb;
}
blockquote p:last-child { margin-bottom: 0; }

hr { border: none; border-top: 1px solid #e4e7ec; margin: 14pt 0; }

table { width: 100%; border-collapse: collapse; margin: 10pt 0; font-size: 8.5pt; }
th, td { border: 1px solid #d0d5dd; padding: 4pt 6pt; text-align: left;
         vertical-align: top; }
th { background: #f4f7fb; font-weight: bold; }
/* Repeat the header on every page a long table spills onto, and never break
   a row across the page boundary. */
thead { display: table-header-group; }
tr { page-break-inside: avoid; }

code { font-family: "DejaVu Sans Mono", monospace; font-size: 8.5pt;
       background: #f2f4f7; padding: 1pt 3pt; }
pre { background: #101828; color: #f8fafc; padding: 8pt; overflow-wrap: break-word;
      white-space: pre-wrap; font-size: 8.5pt; }
pre code { background: none; color: inherit; padding: 0; }

.math { font-style: italic; }

.footnote { margin-top: 22pt; padding-top: 8pt; border-top: 1px solid #e4e7ec;
            font-size: 7.5pt; color: #98a2b3; }
"""


@dataclass(frozen=True, slots=True)
class HandoutContext:
    """Everything the cover block prints, gathered by the caller."""

    title: str
    body: str
    is_graded: bool
    subject_name: str | None = None
    module_title: str | None = None
    starts_at: date | None = None
    ends_at: date | None = None
    description: str | None = None


def _mark_math(text: str) -> str:
    """Drop the ``$`` delimiters and mark the expression for italics."""
    return _INLINE_MATH.sub(r'<span class="math">\1</span>', text)


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _period(context: HandoutContext) -> str | None:
    if context.starts_at is None:
        return None
    if context.ends_at and context.ends_at != context.starts_at:
        return f"{context.starts_at:%d %b %Y} to {context.ends_at:%d %b %Y}"
    return f"{context.starts_at:%d %b %Y}"


def _masthead(context: HandoutContext) -> str:
    rows = [
        ("Subject", context.subject_name),
        ("Module", context.module_title),
        ("Date", _period(context)),
    ]
    facts = "".join(
        f"<dt>{label}:</dt><dd>{_escape(value)}</dd>" for label, value in rows if value
    )
    kicker = "Evaluation" if context.is_graded else "Activity"
    summary = f"<p>{_escape(context.description)}</p>" if context.description else ""
    return (
        '<header class="masthead">'
        f'<p class="kicker">{kicker}</p>'
        f"<h1>{_escape(context.title)}</h1>"
        f"<dl>{facts}</dl>"
        "</header>"
        f"{summary}"
    )


def render_handout_html(context: HandoutContext) -> str:
    """The full HTML document, kept separate so it can be asserted on."""
    body = markdown_lib.markdown(
        _mark_math(context.body),
        extensions=["tables", "fenced_code", "sane_lists", "attr_list"],
    )
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>{_escape(context.title)}</title>"
        f"<style>{_STYLESHEET}</style></head><body>"
        f"{_masthead(context)}"
        f"{body}"
        '<p class="footnote">Generated by ProfPlan. Review the content before '
        "handing it to a class: it was written by an AI.</p>"
        "</body></html>"
    )


def render_handout_pdf(context: HandoutContext) -> bytes:
    """The activity as an A4 PDF, ready to be printed or handed out."""
    # Imported here, not at module load: WeasyPrint opens pango and cairo
    # through cffi the moment it is imported, so a top-level import makes
    # every process that merely touches this module (the Celery worker, a
    # test run on a machine without those libraries) fail at startup over a
    # feature it never uses.
    from weasyprint import HTML

    return HTML(string=render_handout_html(context)).write_pdf()


def handout_filename(title: str) -> str:
    """A filename a file manager will accept, derived from the title."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", title).strip("-").lower()
    return f"{slug or 'activity'}.pdf"
