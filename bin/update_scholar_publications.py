#!/usr/bin/env python

import json
import os
import re
import sys
import urllib.parse
import urllib.request
import yaml
from scholarly import scholarly

BIBLIOGRAPHY_FILE = "_bibliography/papers.bib"

# al-folio custom fields to preserve from existing entries
CUSTOM_FIELDS = {
    "abbr", "bibtex_show", "preview", "html", "pdf", "award", "award_name",
    "selected", "altmetric", "abstract", "doi", "arxiv", "code", "poster",
    "slides", "supp", "blog", "dimensions",
}


def load_scholar_user_id() -> str:
    config_file = "_data/socials.yml"
    if not os.path.exists(config_file):
        print(f"Configuration file {config_file} not found.")
        sys.exit(1)
    try:
        with open(config_file) as f:
            config = yaml.safe_load(f)
        scholar_user_id = config.get("scholar_userid")
        if not scholar_user_id:
            print("No 'scholar_userid' found in _data/socials.yml.")
            sys.exit(1)
        return scholar_user_id
    except yaml.YAMLError as e:
        print(f"Error parsing YAML: {e}")
        sys.exit(1)


def normalize_title(title: str) -> str:
    return re.sub(r"\W+", "", title.lower())


def parse_existing_entries(filepath: str) -> dict:
    """Return normalized title -> {"key", "text", "custom"} for entries in papers.bib."""
    result = {}
    if not os.path.exists(filepath):
        return result

    with open(filepath) as f:
        content = f.read()

    for entry_match in re.finditer(r"@\w+\{(\w+),(.*?)\n\}", content, re.DOTALL):
        key = entry_match.group(1)
        body = entry_match.group(2)
        title = re.search(r"^\s*title\s*=\s*\{(.*)\},?\s*$", body, re.MULTILINE)
        if not title:
            continue
        custom = {}
        for field_match in re.finditer(r"(\w+)\s*=\s*\{([^}]*)\}", body):
            fname = field_match.group(1).strip().lower()
            fvalue = field_match.group(2).strip()
            if fname in CUSTOM_FIELDS:
                custom[fname] = fvalue
        result[normalize_title(title.group(1))] = {
            "key": key,
            "text": entry_match.group(0),
            "custom": custom,
        }

    return result


def needs_refresh(entry: dict) -> bool:
    """Re-fetch preprints (to pick up the published version) and entries without authors."""
    text = entry["text"].lower()
    return "rxiv" in text or not re.search(r"^\s*author\s*=", text, re.MULTILINE)


def setup_proxy() -> None:
    """Route requests through ScraperAPI when SCRAPER_API_KEY is set.

    Google Scholar blocks GitHub Actions IPs, so the workflow needs a proxy;
    local runs work without one.
    """
    api_key = os.environ.get("SCRAPER_API_KEY")
    if not api_key:
        return
    from scholarly import ProxyGenerator

    pg = ProxyGenerator()
    if not pg.ScraperAPI(api_key):
        print("Could not set up the ScraperAPI proxy; check SCRAPER_API_KEY.")
        sys.exit(1)
    scholarly.use_proxy(pg)
    print("Using ScraperAPI proxy.")


def make_key(meta: dict) -> str:
    """Generate a BibTeX key: firstauthorlastname + year + firsttitleword."""
    first_author = meta.get("author", "").split(" and ")[0].strip()
    _, last_name = split_name(first_author) if first_author else ([], "")
    last_name = re.sub(r"[^a-zA-Z]", "", last_name.split()[-1] if last_name else "").lower()

    title_words = re.sub(r"[^a-zA-Z\s]", "", meta.get("title", "")).split()
    title_word = title_words[0].lower() if title_words else "unknown"

    return f"{last_name or 'unknown'}{meta.get('year', '')}{title_word}"


PARTICLES = {"van", "von", "der", "den", "de", "del", "della", "di", "da", "du", "la", "le", "ter", "ten", "af"}


# Scholar spells the same person differently across papers; map known variants
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


def lookup_openalex(title: str) -> dict:
    """Find a work by exact (normalized) title on OpenAlex, preferring the published version.

    Google Scholar's per-publication pages sit behind a JavaScript check that
    scholarly cannot pass, so details come from OpenAlex instead.
    """
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(
        {"search": title, "per-page": 10}
    )
    req = urllib.request.Request(url, headers={"User-Agent": "al-folio-scholar-sync"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        works = json.load(resp).get("results", [])
    matches = [
        w
        for w in works
        if normalize_title(w.get("title") or "") == normalize_title(title)
        and any(
            "van der veen" in a["author"]["display_name"].lower()
            for a in w.get("authorships", [])
        )
    ]
    matches.sort(key=lambda w: w.get("type") == "preprint")
    return matches[0] if matches else None


def openalex_meta(work: dict, title: str, fallback_venue: str) -> dict:
    location = work.get("primary_location") or {}
    source = location.get("source") or {}
    biblio = work.get("biblio") or {}
    pages = "-".join(p for p in (biblio.get("first_page"), biblio.get("last_page")) if p)
    if biblio.get("first_page") == biblio.get("last_page"):
        pages = biblio.get("first_page") or ""
    doi = (work.get("doi") or "").replace("https://doi.org/", "")
    if not source and "cran.package" in doi.lower():
        fallback_venue = "R package"
    return {
        "title": title,
        "author": " and ".join(a["author"]["display_name"] for a in work.get("authorships", [])),
        "journal": re.sub(r"\s*\(.*\)$", "", source.get("display_name") or "") or fallback_venue,
        "volume": biblio.get("volume"),
        "number": biblio.get("issue"),
        "pages": pages,
        "year": work.get("publication_year"),
        "publisher": source.get("host_organization_name"),
        "doi": doi,
        "url": (location.get("landing_page_url") or work.get("doi") or "").replace("http://", "https://"),
    }


def scholar_meta(pub: dict, scholar_id: str) -> dict:
    """Minimal entry from the Scholar profile list (no authors available there)."""
    bib = pub.get("bib", {})
    return {
        "title": bib.get("title", ""),
        "journal": re.sub(r",?\s*\d{4}$", "", bib.get("citation", "")).strip(),
        "year": bib.get("pub_year", ""),
        "url": "https://scholar.google.com/citations?view_op=view_citation&citation_for_view="
        + pub.get("author_pub_id", f"{scholar_id}:"),
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
    scholar_id = load_scholar_user_id()
    print(f"Fetching publications for Google Scholar ID: {scholar_id}")

    existing = parse_existing_entries(BIBLIOGRAPHY_FILE)
    print(f"Found {len(existing)} existing entries in {BIBLIOGRAPHY_FILE}.")

    scholarly.set_timeout(15)
    scholarly.set_retries(3)
    setup_proxy()

    try:
        author = scholarly.search_author_id(scholar_id)
        author_data = scholarly.fill(author, sections=["basics", "publications"])
    except Exception as e:
        print(f"Error fetching author data from Google Scholar: {e}")
        if os.environ.get("GITHUB_ACTIONS") and not os.environ.get("SCRAPER_API_KEY"):
            print("Google Scholar blocks GitHub Actions; add a SCRAPER_API_KEY repository secret.")
        sys.exit(1)

    publications = author_data.get("publications", [])
    print(f"Found {len(publications)} publications on Scholar.")

    # Sort newest first
    publications.sort(
        key=lambda p: int(p.get("bib", {}).get("pub_year") or 0),
        reverse=True,
    )

    # Only look up details for new publications and preprints; everything else
    # is kept as it is in papers.bib. A failed lookup never replaces an entry.
    results = []
    failed = 0
    for pub in publications:
        title = pub.get("bib", {}).get("title", "Unknown")
        old = existing.get(normalize_title(title))
        if old and not needs_refresh(old):
            results.append((old, None))
            continue
        try:
            work = lookup_openalex(title)
        except Exception as e:
            failed += 1
            print(f"  Warning: OpenAlex lookup failed for '{title}': {e}")
            if old:
                results.append((old, None))
            continue
        has_authors = old and re.search(r"^\s*author\s*=", old["text"], re.MULTILINE)
        if work and has_authors and work.get("type") == "preprint":
            # Still a preprint: keep the existing (possibly hand-edited) entry.
            results.append((old, None))
            continue
        if work:
            meta = openalex_meta(work, title, scholar_meta(pub, scholar_id)["journal"])
            print(f"  [{meta['year']}] {title} (OpenAlex)")
        elif old:
            results.append((old, None))
            continue
        else:
            meta = scholar_meta(pub, scholar_id)
            print(f"  Warning: '{title}' not found on OpenAlex; adding it without authors.")
        results.append((old, meta))

    # Expand initials-only authors using spellings found on other papers.
    author_strings = [meta.get("author", "") for _, meta in results if meta]
    author_strings += [
        m.group(1)
        for old, _ in results
        if old
        for m in [re.search(r"^\s*author\s*=\s*\{(.*)\},?\s*$", old["text"], re.MULTILINE)]
        if m
    ]
    name_index = build_name_index(author_strings)

    entries = []
    for old, meta in results:
        if meta:
            key = old["key"] if old else make_key(meta)
            entry = meta_to_bibtex(meta, key, old["custom"] if old else {}, name_index)
        else:
            entry = re.sub(
                r"^(\s*author\s*=\s*\{)(.*)(\},?\s*)$",
                lambda m: m.group(1) + format_authors(m.group(2), name_index) + m.group(3),
                old["text"],
                flags=re.MULTILINE,
            )
        entries.append(entry)

    content = "---\n---\n\n" + "\n\n".join(entries) + "\n"

    with open(BIBLIOGRAPHY_FILE, "w") as f:
        f.write(content)

    fetched = sum(1 for _, meta in results if meta)
    print(f"\nWrote {len(entries)} entries to {BIBLIOGRAPHY_FILE} ({fetched} looked up, {failed} failed).")


if __name__ == "__main__":
    main()
