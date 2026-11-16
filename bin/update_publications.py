#!/usr/bin/env python

"""Add new publications to papers.bib from OpenAlex, using the ORCID below.

Google Scholar blocks automated requests (GitHub Actions, proxy services, and
per-publication pages behind a JavaScript check), so OpenAlex is the source.
Existing entries are never removed or overwritten, except preprints, which are
replaced once their published version shows up.
"""

import json
import os
import re
import sys
import urllib.parse
import urllib.request

BIBLIOGRAPHY_FILE = "_bibliography/papers.bib"
ORCID = "0000-0003-2263-3880"

# OpenAlex work types to add. Datasets/software are only added when they are
# CRAN packages; this skips Zenodo releases, Figshare data and Publons reviews.
INCLUDED_TYPES = {
    "article", "preprint", "review", "book", "book-chapter", "dissertation",
    "conference-abstract", "letter", "report",
}

# Works on OpenAlex that should never be added (title or DOI). Deleting an
# entry from papers.bib is not enough, it would come back on the next run.
EXCLUDED_WORKS = [
]

# al-folio custom fields to preserve from existing entries
CUSTOM_FIELDS = {
    "abbr", "bibtex_show", "preview", "html", "pdf", "award", "award_name",
    "selected", "altmetric", "abstract", "doi", "arxiv", "code", "poster",
    "slides", "supp", "blog", "dimensions",
}


def normalize_title(title: str) -> str:
    return re.sub(r"\W+", "", title.lower())


def parse_existing_entries(filepath: str) -> list:
    """Return [{"key", "title", "doi", "year", "text", "custom"}] for entries in papers.bib."""
    result = []
    if not os.path.exists(filepath):
        return result

    with open(filepath) as f:
        content = f.read()

    def field(body, name):
        m = re.search(rf"^\s*{name}\s*=\s*\{{(.*)\}},?\s*$", body, re.MULTILINE)
        return m.group(1) if m else ""

    for entry_match in re.finditer(r"@\w+\{(\w+),(.*?)\n\}", content, re.DOTALL):
        body = entry_match.group(2)
        custom = {}
        for field_match in re.finditer(r"(\w+)\s*=\s*\{([^}]*)\}", body):
            fname = field_match.group(1).strip().lower()
            fvalue = field_match.group(2).strip()
            if fname in CUSTOM_FIELDS:
                custom[fname] = fvalue
        result.append({
            "key": entry_match.group(1),
            "title": normalize_title(field(body, "title")),
            "doi": field(body, "doi").lower(),
            "year": int(field(body, "year") or 0),
            "text": entry_match.group(0),
            "custom": custom,
        })

    return result


def is_preprint(entry: dict) -> bool:
    return "rxiv" in entry["text"].lower()


def has_authors(entry: dict) -> bool:
    return bool(re.search(r"^\s*author\s*=", entry["text"], re.MULTILINE))


def fetch_works(orcid: str) -> list:
    works, page = [], 1
    while True:
        url = "https://api.openalex.org/works?" + urllib.parse.urlencode(
            {"filter": f"author.orcid:{orcid}", "per-page": 200, "page": page}
        )
        req = urllib.request.Request(url, headers={"User-Agent": "al-folio-publications-sync"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            results = json.load(resp).get("results", [])
        works += results
        if len(results) < 200:
            return works
        page += 1


def wanted(work: dict) -> bool:
    doi = (work.get("doi") or "").lower()
    excluded = {normalize_title(x) for x in EXCLUDED_WORKS} | {x.lower() for x in EXCLUDED_WORKS}
    if normalize_title(work.get("title") or "") in excluded or doi.replace("https://doi.org/", "") in excluded:
        return False
    return work.get("type") in INCLUDED_TYPES or "cran.package" in doi


def make_key(meta: dict) -> str:
    """Generate a BibTeX key: firstauthorlastname + year + firsttitleword."""
    first_author = meta.get("author", "").split(" and ")[0].strip()
    _, last_name = split_name(first_author) if first_author else ([], "")
    last_name = re.sub(r"[^a-zA-Z]", "", last_name.split()[-1] if last_name else "").lower()

    title_words = re.sub(r"[^a-zA-Z\s]", "", meta.get("title", "")).split()
    title_word = title_words[0].lower() if title_words else "unknown"

    return f"{last_name or 'unknown'}{meta.get('year', '')}{title_word}"


PARTICLES = {"van", "von", "der", "den", "de", "del", "della", "di", "da", "du", "la", "le", "ter", "ten", "af"}


# The same person is spelled differently across papers; map known variants
# (lowercased, straight apostrophes) to one canonical form.
AUTHOR_ALIASES = {
    "bert van der veen": "Bert van der Veen",
    "b van der veen": "Bert van der Veen",
    "robert b o'hara": "Robert B O'Hara",
    "robert brian o'hara": "Robert B O'Hara",
    "robert o'hara": "Robert B O'Hara",
    "bob o'hara": "Robert B O'Hara",
    "rb o'hara": "Robert B O'Hara",
    "r b o'hara": "Robert B O'Hara",
    "francis kc hui": "Francis KC Hui",
    "fkc hui": "Francis KC Hui",
    "knut a hovstad": "Knut A Hovstad",
    "knut anders hovstad": "Knut A Hovstad",
    "knut hovstad": "Knut A Hovstad",
    "erik b solbu": "Erik B Solbu",
    "erik blystad solbu": "Erik B Solbu",
    "erik solbu": "Erik B Solbu",
    "marie henriksen": "Marie Vestergaard Henriksen",
    # initials-only variants that no other paper spells out
    "di warton": "David I Warton",
    "r herliansyah": "Riki Herliansyah",
}


def alias_key(name: str) -> str:
    """Lowercase, straight apostrophes, no dots, joined initials ("K. C." -> "kc")."""
    key = name.lower().replace("\u2019", "'").replace(".", " ")
    key = " ".join(key.split())
    return re.sub(r"\b(\w) (?=\w\b)", r"\1", key)


ALIASES = {alias_key(k): v for k, v in AUTHOR_ALIASES.items()}


def canonical_name(name: str) -> str:
    return ALIASES.get(alias_key(name), name)


def split_name(name: str) -> tuple:
    """Split "Bert van der Veen" into (["Bert"], "van der Veen")."""
    parts = name.split()
    start = next(
        (i for i, w in enumerate(parts) if i > 0 and w.lower() in PARTICLES),
        len(parts) - 1,
    )
    return parts[:start], " ".join(parts[start:])


def is_initials(token: str) -> bool:
    return token.rstrip(".").isupper() and len(token.rstrip(".")) <= 3


def initials_of(given: list) -> str:
    return "".join(
        t.rstrip(".").lower() if is_initials(t) else t[0].lower() for t in given
    )


def build_name_index(author_strings: list) -> dict:
    """Map (surname, initials) -> full name, for names spelled out somewhere.

    Ambiguous keys (two different full names, same initials) are dropped.
    """
    index = {}
    for authors in author_strings:
        for name in authors.split(" and "):
            name = name.replace("{", "").replace("}", "").strip()
            name = canonical_name(name)
            given, surname = split_name(name)
            if not given or all(is_initials(t) for t in given):
                continue
            key = (surname.lower(), initials_of(given))
            if index.setdefault(key, name) != name:
                index[key] = None
    return {k: v for k, v in index.items() if v}


def format_authors(authors: str, name_index: dict = None) -> str:
    """Brace multi-word surnames ("Bert van der Veen" -> "Bert {van der Veen}").

    Without braces BibTeX treats lowercase particles as a separate "von" part,
    which the bib layout drops (rendering "Bert Veen") and which never matches
    scholar.last_name in _config.yml.
    """
    out = []
    for name in authors.split(" and "):
        name = name.strip().replace("{", "").replace("}", "")
        name = canonical_name(name)
        given, surname = split_name(name)
        if name_index and given and all(is_initials(t) for t in given):
            name = name_index.get((surname.lower(), initials_of(given)), name)
        parts = name.split()
        start = next(
            (i for i, w in enumerate(parts) if i > 0 and w.lower() in PARTICLES), None
        )
        if start is not None and start < len(parts) - 1:
            surname = " ".join(parts[start:])
            if surname.lower() == "van der veen":
                surname = "van der Veen"
            name = " ".join(parts[:start] + ["{" + surname + "}"])
        out.append(name)
    return " and ".join(out)


def openalex_meta(work: dict) -> dict:
    location = work.get("primary_location") or {}
    source = location.get("source") or {}
    biblio = work.get("biblio") or {}
    pages = "-".join(p for p in (biblio.get("first_page"), biblio.get("last_page")) if p)
    if biblio.get("first_page") == biblio.get("last_page"):
        pages = biblio.get("first_page") or ""
    doi = (work.get("doi") or "").replace("https://doi.org/", "")
    venue = re.sub(r"\s*\(.*\)$", "", source.get("display_name") or "")
    if not venue and "cran.package" in doi.lower():
        venue = "R package"
    return {
        "title": work.get("title"),
        "author": " and ".join(a["author"]["display_name"] for a in work.get("authorships", [])),
        "journal": venue,
        "volume": biblio.get("volume"),
        "number": biblio.get("issue"),
        "pages": pages,
        "year": work.get("publication_year"),
        "publisher": source.get("host_organization_name"),
        "doi": doi,
        "url": (location.get("landing_page_url") or work.get("doi") or "").replace("http://", "https://"),
    }


def meta_to_bibtex(meta: dict, key: str, custom: dict, name_index: dict = None) -> str:
    def field_line(name, value):
        if value and name not in custom:
            return f"  {name:<12} = {{{value}}},"
        return None

    raw_fields = [
        field_line("title", meta.get("title")),
        field_line("author", format_authors(meta["author"], name_index) if meta.get("author") else ""),
        field_line("journal", meta.get("journal")),
        field_line("volume", meta.get("volume")),
        field_line("number", meta.get("number")),
        field_line("pages", meta.get("pages")),
        field_line("year", meta.get("year")),
        field_line("publisher", meta.get("publisher")),
        field_line("doi", meta.get("doi")),
        field_line("url", meta.get("url")),
    ]

    for fname, fvalue in custom.items():
        raw_fields.append(f"  {fname:<12} = {{{fvalue}}},")

    lines = [f"@article{{{key},"] + [l for l in raw_fields if l] + ["}"]
    return "\n".join(lines)


def main() -> None:
    print(f"Fetching works for ORCID {ORCID} from OpenAlex")
    existing = parse_existing_entries(BIBLIOGRAPHY_FILE)
    print(f"Found {len(existing)} existing entries in {BIBLIOGRAPHY_FILE}.")

    try:
        works = [w for w in fetch_works(ORCID) if w.get("title") and wanted(w)]
    except Exception as e:
        print(f"Error fetching works from OpenAlex: {e}")
        sys.exit(1)
    if not works:
        print("OpenAlex returned no works; leaving papers.bib unchanged.")
        sys.exit(1)

    # One work per title, preferring the published version over a preprint.
    works.sort(key=lambda w: w.get("type") == "preprint")
    by_title = {}
    for work in works:
        by_title.setdefault(normalize_title(work["title"]), work)

    entries = {id(e): (e, None) for e in existing}
    added = replaced = 0
    for title, work in by_title.items():
        doi = (work.get("doi") or "").lower().replace("https://doi.org/", "")
        old = next((e for e in existing if e["title"] == title or (doi and e["doi"] == doi)), None)
        if old is None:
            entries[id(work)] = (None, openalex_meta(work))
            added += 1
            print(f"  Adding [{work.get('publication_year')}] {work['title']}")
        elif (is_preprint(old) and work.get("type") != "preprint") or not has_authors(old):
            entries[id(old)] = (old, openalex_meta(work))
            replaced += 1
            print(f"  Updating [{work.get('publication_year')}] {work['title']}")

    # Expand initials-only authors using spellings found on other papers.
    author_strings = [meta.get("author", "") for _, meta in entries.values() if meta]
    author_strings += [
        m.group(1)
        for old, _ in entries.values()
        if old
        for m in [re.search(r"^\s*author\s*=\s*\{(.*)\},?\s*$", old["text"], re.MULTILINE)]
        if m
    ]
    name_index = build_name_index(author_strings)

    rendered = []
    for old, meta in entries.values():
        if meta:
            key = old["key"] if old else make_key(meta)
            entry = meta_to_bibtex(meta, key, old["custom"] if old else {}, name_index)
            year = int(meta.get("year") or 0)
        else:
            entry = re.sub(
                r"^(\s*author\s*=\s*\{)(.*)(\},?\s*)$",
                lambda m: m.group(1) + format_authors(m.group(2), name_index) + m.group(3),
                old["text"],
                flags=re.MULTILINE,
            )
            year = old["year"]
        rendered.append((year, entry))

    # Newest first; entries without a year go last.
    rendered.sort(key=lambda x: -(x[0] or -1))
    content = "---\n---\n\n" + "\n\n".join(e for _, e in rendered) + "\n"

    with open(BIBLIOGRAPHY_FILE, "w") as f:
        f.write(content)

    print(f"\nWrote {len(rendered)} entries to {BIBLIOGRAPHY_FILE} ({added} added, {replaced} updated).")


if __name__ == "__main__":
    main()
