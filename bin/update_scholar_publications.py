#!/usr/bin/env python

import os
import re
import sys
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


def parse_existing_custom_fields(filepath: str) -> dict:
    """Return a dict of bibtex_key -> {field: value} for all custom al-folio fields."""
    result = {}
    if not os.path.exists(filepath):
        return result

    with open(filepath) as f:
        content = f.read()

    for entry_match in re.finditer(r"@\w+\{(\w+),(.*?)\n\}", content, re.DOTALL):
        key = entry_match.group(1)
        body = entry_match.group(2)
        fields = {}
        for field_match in re.finditer(r"(\w+)\s*=\s*\{([^}]*)\}", body):
            fname = field_match.group(1).strip().lower()
            fvalue = field_match.group(2).strip()
            if fname in CUSTOM_FIELDS:
                fields[fname] = fvalue
        if fields:
            result[key] = fields

    return result


def make_key(pub: dict) -> str:
    """Generate a BibTeX key: firstauthorlastname + year + firsttitleword."""
    bib = pub.get("bib", {})
    author = bib.get("author", "")
    year = str(bib.get("pub_year", "0000"))
    title = bib.get("title", "unknown")

    first_author = author.split(" and ")[0].strip()
    if "," in first_author:
        last_name = first_author.split(",")[0].strip()
    else:
        parts = first_author.split()
        last_name = parts[-1] if parts else "unknown"
    last_name = re.sub(r"[^a-zA-Z]", "", last_name).lower()

    title_words = re.sub(r"[^a-zA-Z\s]", "", title).split()
    title_word = title_words[0].lower() if title_words else "unknown"

    return f"{last_name}{year}{title_word}"


def pub_to_bibtex(pub: dict, existing_custom: dict) -> str:
    """Convert a scholarly publication dict to a BibTeX entry string."""
    bib = pub.get("bib", {})

    venue = (bib.get("venue") or "").lower()
    journal = bib.get("journal") or ""

    if any(w in venue for w in ("conference", "proceedings", "workshop", "symposium")):
        entry_type = "inproceedings"
        venue_field = "booktitle"
    else:
        entry_type = "article"
        venue_field = "journal"

    key = make_key(pub)

    def field_line(name, value):
        if value:
            return f"  {name:<12} = {{{value}}},"
        return None

    raw_fields = [
        field_line("title", bib.get("title", "")),
        field_line("author", bib.get("author", "")),
        field_line(venue_field, journal or bib.get("venue", "")),
        field_line("volume", bib.get("volume", "")),
        field_line("number", bib.get("number", "")),
        field_line("pages", bib.get("pages", "")),
        field_line("year", bib.get("pub_year", "")),
        field_line("publisher", bib.get("publisher", "")),
        field_line("url", pub.get("pub_url", "")),
    ]

    for fname, fvalue in existing_custom.get(key, {}).items():
        raw_fields.append(field_line(fname, fvalue))

    lines = [f"@{entry_type}{{{key},"] + [l for l in raw_fields if l] + ["}"]
    return "\n".join(lines)


def main() -> None:
    scholar_id = load_scholar_user_id()
    print(f"Fetching publications for Google Scholar ID: {scholar_id}")

    existing_custom = parse_existing_custom_fields(BIBLIOGRAPHY_FILE)
    print(f"Preserving custom fields from {len(existing_custom)} existing entries.")

    scholarly.set_timeout(15)
    scholarly.set_retries(3)

    try:
        author = scholarly.search_author_id(scholar_id)
        author_data = scholarly.fill(author)
    except Exception as e:
        print(f"Error fetching author data from Google Scholar: {e}")
        sys.exit(1)

    publications = author_data.get("publications", [])
    print(f"Found {len(publications)} publications on Scholar.")

    # Sort newest first
    publications.sort(
        key=lambda p: int(p.get("bib", {}).get("pub_year") or 0),
        reverse=True,
    )

    entries = []
    for pub in publications:
        try:
            entry = pub_to_bibtex(pub, existing_custom)
            entries.append(entry)
            title = pub.get("bib", {}).get("title", "Unknown")
            year = pub.get("bib", {}).get("pub_year", "?")
            print(f"  [{year}] {title}")
        except Exception as e:
            title = pub.get("bib", {}).get("title", "Unknown")
            print(f"  Warning: skipping '{title}': {e}")

    content = "---\n---\n\n" + "\n\n".join(entries) + "\n"

    with open(BIBLIOGRAPHY_FILE, "w") as f:
        f.write(content)

    print(f"\nWrote {len(entries)} entries to {BIBLIOGRAPHY_FILE}")


if __name__ == "__main__":
    main()
