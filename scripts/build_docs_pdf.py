"""Baut docs/netdiag-dokumentation.pdf aus README.md + docs/*.md.

Nicht Teil des Laufzeit-Produkts — reines Entwickler-Werkzeug, um allen
vier Dokumenten (README, INSTALLATION, BENUTZERHANDBUCH, TROUBLESHOOTING)
als ein zusammenhaengendes PDF mit Titelseite, Inhaltsverzeichnis und
funktionierenden internen Links zu erzeugen.

Aufruf:  python scripts/build_docs_pdf.py
"""
import io
import re
from pathlib import Path

import markdown
from xhtml2pdf import pisa

ROOT = Path(__file__).parent.parent
OUT_PDF = ROOT / "docs" / "netdiag-dokumentation.pdf"

# (Datei, Anzeigename, Anker-Praefix)
DOCS = [
    (ROOT / "README.md", "Überblick", "rd"),
    (ROOT / "docs" / "INSTALLATION.md", "Installation", "inst"),
    (ROOT / "docs" / "BENUTZERHANDBUCH.md", "Benutzerhandbuch", "hb"),
    (ROOT / "docs" / "TROUBLESHOOTING.md", "Troubleshooting", "ts"),
]

# Exakte String-Ersetzungen für interne Links, bevor Markdown gerendert wird.
# (Dokument-Datei, alt, neu)
LINK_FIXES = [
    ("README.md", "[docs/INSTALLATION.md](docs/INSTALLATION.md)",
     "[docs/INSTALLATION.md](#inst-installation)"),
    ("README.md", "[docs/BENUTZERHANDBUCH.md](docs/BENUTZERHANDBUCH.md)",
     "[docs/BENUTZERHANDBUCH.md](#hb-benutzerhandbuch)"),
    ("README.md", "[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)",
     "[docs/TROUBLESHOOTING.md](#ts-troubleshooting)"),
    ("README.md", "[docs/KONZEPT-v3.md](docs/KONZEPT-v3.md)",
     "docs/KONZEPT-v3.md *(nicht Teil dieses PDFs)*"),
    ("README.md", "[Installation](docs/INSTALLATION.md)",
     "[Installation](#inst-installation)"),
    ("README.md", "[docs/KONZEPT.md](docs/KONZEPT.md)",
     "docs/KONZEPT.md *(nicht Teil dieses PDFs)*"),

    ("INSTALLATION.md", "[CLAUDE.md](../CLAUDE.md)", "CLAUDE.md"),
    ("INSTALLATION.md", "[Fernzugriff aktivieren](#fernzugriff-aktivieren-optional)",
     "[Fernzugriff aktivieren](#inst-fernzugriff-aktivieren-optional)"),
    ("INSTALLATION.md", "[Benutzerhandbuch](BENUTZERHANDBUCH.md#port-aktionen)",
     "[Benutzerhandbuch](#hb-port-aktionen)"),
    ("INSTALLATION.md", "[Troubleshooting](TROUBLESHOOTING.md)",
     "[Troubleshooting](#ts-troubleshooting)"),

    ("BENUTZERHANDBUCH.md", "[INSTALLATION.md](INSTALLATION.md)",
     "[INSTALLATION.md](#inst-installation)"),
    ("BENUTZERHANDBUCH.md", "[Verwaltung](#verwaltung)", "[Verwaltung](#hb-verwaltung)"),
    ("BENUTZERHANDBUCH.md", "[Troubleshooting](TROUBLESHOOTING.md)",
     "[Troubleshooting](#ts-troubleshooting)"),

    ("TROUBLESHOOTING.md",
     "[Installation → Fernzugriff](INSTALLATION.md#fernzugriff-aktivieren-optional)",
     "[Installation → Fernzugriff](#inst-fernzugriff-aktivieren-optional)"),
    ("TROUBLESHOOTING.md",
     "[Installation → Fernzugriff aktivieren](INSTALLATION.md#fernzugriff-aktivieren-optional)",
     "[Installation → Fernzugriff aktivieren](#inst-fernzugriff-aktivieren-optional)"),
]

MD_EXTENSIONS = ["tables", "fenced_code", "sane_lists", "toc", "attr_list"]

CSS = """
@page {
    size: A4;
    margin: 2.2cm 2cm 2.4cm 2cm;
}
body {
    font-family: "DejaVu Sans", Helvetica, Arial, sans-serif;
    font-size: 9.5pt;
    line-height: 1.5;
    color: #1a1a1a;
}
h1, h2, h3, h4 {
    font-family: "DejaVu Sans", Helvetica, Arial, sans-serif;
    color: #0b3d5c;
    margin-top: 18px;
    margin-bottom: 8px;
}
h1 { font-size: 20pt; border-bottom: 2px solid #0b3d5c; padding-bottom: 6px; }
h2 { font-size: 14pt; border-bottom: 1px solid #b9d4e3; padding-bottom: 3px; margin-top: 22px; }
h3 { font-size: 11.5pt; color: #14577d; }
h4 { font-size: 10.5pt; color: #14577d; }
p, li { text-align: left; }
a { color: #0b6ea8; text-decoration: none; }
code {
    font-family: "DejaVu Sans Mono", "Courier New", monospace;
    font-size: 8.7pt;
    background-color: #f0f3f5;
    padding: 1px 3px;
    color: #a3142b;
}
pre {
    font-family: "DejaVu Sans Mono", "Courier New", monospace;
    font-size: 8.3pt;
    background-color: #f4f6f7;
    border: 0.5px solid #d5dde1;
    padding: 8px 10px;
    line-height: 1.35;
}
pre code { background-color: transparent; padding: 0; color: #1a1a1a; }
table {
    border-collapse: collapse;
    width: 100%;
    margin: 10px 0;
    font-size: 8.7pt;
}
th, td {
    border: 0.5px solid #c7d1d6;
    padding: 4px 7px;
    text-align: left;
    vertical-align: top;
}
th { background-color: #e7eef2; color: #0b3d5c; }
blockquote {
    border-left: 3px solid #0b6ea8;
    margin: 8px 0;
    padding: 2px 12px;
    color: #444;
    background-color: #f7fafc;
}
hr { border: none; border-top: 1px solid #d5dde1; margin: 20px 0; }
.doc-section { margin-top: 4px; }
.doc-divider {
    page-break-before: always;
}
.titlepage {
    text-align: center;
    padding-top: 130px;
}
.titlepage .brand {
    font-size: 32pt;
    font-family: "DejaVu Sans Mono", monospace;
    letter-spacing: 3px;
    color: #0b3d5c;
}
.titlepage .subtitle {
    font-size: 12.5pt;
    color: #333;
    margin-top: 10px;
}
.titlepage .meta {
    font-size: 9.5pt;
    color: #666;
    margin-top: 34px;
}
.toc-page { page-break-before: always; }
.toc-page h1 { margin-bottom: 18px; }
.toc-doc { font-weight: bold; margin-top: 12px; color: #0b3d5c; }
.toc-list { list-style: none; padding-left: 0; margin: 4px 0 0 0; }
.toc-list li { margin: 2px 0; }
.toc-sub { padding-left: 18px; color: #333; font-weight: normal; }
"""


_LIST_RE = re.compile(r"^(\s*)([-*+]|\d+\.)\s")


def fix_list_spacing(text: str) -> str:
    """python-markdown (anders als GitHub/CommonMark) braucht eine Leerzeile
    vor dem ersten Element einer Liste, sonst wird sie in den vorangehenden
    Absatz eingeschmolzen. Fügt sie nur vor echten Listenanfängen ein, nicht
    zwischen mehrzeiligen Folge-Items derselben Liste."""
    lines = text.split("\n")
    out: list[str] = []
    in_code = False
    in_list = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            out.append(line)
            continue
        if in_code:
            out.append(line)
            continue
        if stripped == "":
            in_list = False
            out.append(line)
            continue
        if _LIST_RE.match(line):
            if not in_list and out and out[-1].strip() != "":
                out.append("")
            in_list = True
            out.append(line)
            continue
        if in_list and (line.startswith("  ") or line.startswith("\t")):
            out.append(line)  # Fortsetzungszeile eines Listenpunkts
            continue
        in_list = False
        out.append(line)
    return "\n".join(out)


def slugify(text):
    """Muss identisch zur toc-Extension von python-markdown sein."""
    import unicodedata
    value = unicodedata.normalize("NFKD", text)
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[-\s]+", "-", value)


def render_doc(path: str, prefix: str) -> tuple[str, list]:
    """Markdown -> (HTML mit prefixten Anker-IDs, TOC-Einträge Ebene 1-2)."""
    text = Path(path).read_text(encoding="utf-8") if Path(path).is_absolute() else None
    text = Path(path).read_text(encoding="utf-8")

    fname = Path(path).name
    for doc_name, old, new in LINK_FIXES:
        if doc_name == fname:
            assert old in text, f"Link-Fix nicht gefunden in {fname}: {old[:60]!r}"
            text = text.replace(old, new)

    if fname == "README.md":
        text = re.sub(r"^!\[CI\]\(.*\)\n\n", "", text, flags=re.MULTILINE)

    # Emoji ohne Glyphen in den PDF-Fonts (DejaVu Sans) durch Text ersetzen,
    # sonst erscheinen schwarze Tofu-Kästchen statt des Warnsymbols.
    text = text.replace("⚠ ", "ACHTUNG: ").replace("⚠", "ACHTUNG")

    text = fix_list_spacing(text)

    md = markdown.Markdown(extensions=MD_EXTENSIONS)
    html = md.convert(text)
    html = html.replace('id="', f'id="{prefix}-')

    toc_entries = []
    for tok in md.toc_tokens:
        toc_entries.append((1, prefix, tok["id"], tok["name"]))
        for child in tok.get("children", []):
            toc_entries.append((2, prefix, child["id"], child["name"]))
    return html, toc_entries


def build_toc_html(all_entries) -> str:
    parts = ['<div class="toc-page">', "<h1>Inhaltsverzeichnis</h1>"]
    parts.append('<ul class="toc-list">')
    for level, prefix, anchor_id, name in all_entries:
        cls = "toc-sub" if level == 2 else "toc-doc"
        parts.append(f'<li class="{cls}"><a href="#{prefix}-{anchor_id}">{name}</a></li>')
    parts.append("</ul></div>")
    return "\n".join(parts)


def main():
    doc_sections = []
    all_toc_entries = []

    for path, display_name, prefix in DOCS:
        html, toc_entries = render_doc(str(path), prefix)
        all_toc_entries.extend(toc_entries)
        doc_sections.append(f'<div class="doc-divider doc-section">{html}</div>')

    titlepage = """
    <div class="titlepage">
      <div class="brand">▮▮▮ netdiag</div>
      <div class="subtitle">Lokaler Netzwerk-Port-Tester &amp; Kabelkataster</div>
      <div class="subtitle">Vollständige Dokumentation</div>
      <div class="meta">
        Installation &middot; Benutzerhandbuch &middot; Troubleshooting<br>
        github.com/mrckch/netdiag
      </div>
    </div>
    """

    toc_html = build_toc_html(all_toc_entries)

    full_html = f"""<html><head><meta charset="utf-8"/><style>{CSS}</style></head>
    <body>
    {titlepage}
    {toc_html}
    {''.join(doc_sections)}
    </body></html>"""

    OUT_PDF.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PDF, "wb") as f:
        result = pisa.CreatePDF(io.StringIO(full_html), dest=f)

    if result.err:
        raise SystemExit(f"PDF-Erzeugung mit {result.err} Fehlern fehlgeschlagen")
    print(f"OK: {OUT_PDF} ({OUT_PDF.stat().st_size} Bytes)")


if __name__ == "__main__":
    main()
