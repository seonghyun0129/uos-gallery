#!/usr/bin/env python3
"""OpenClaw-like artwork bootstrapper.

Generates:
- works/{artistSlug}/{year}/{month}/{workSlug}/index.html
- assets/images/gallery/{year}/{month}/{workSlug}.{ext}
- archives/{year}/{month}/index.html (between AUTO markers)

Usage:
  python3 scripts/add-artwork.py \
    --artist-name "박나현" \
    --title "TMI PLI" \
    --year 2023 --month 10 \
    --description "..." \
    --image ./src/tmi-pli-cover.jpg
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path


BASE = Path(__file__).resolve().parent.parent
TEMPLATES = BASE / "templates"
WORK_TEMPLATE = TEMPLATES / "work-template.html"
ARCHIVE_TEMPLATE = TEMPLATES / "archive-template.html"
CARD_TEMPLATE = TEMPLATES / "archive-card-template.html"

START_MARKER = "<!-- AUTO-GENERATED-START -->"
END_MARKER = "<!-- AUTO-GENERATED-END -->"
MENU_LINK_TEMPLATE = '            <a href="/archives/{year}/{month}/"><div class="menu">&gt; {year}.{month}</div></a>'
WORKS_LINE_TEMPLATE = "                <li>&gt; {year}.{month}</li>"


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.strip())
    value = value.lower()
    value = re.sub(r"[\s_]+", "-", value)
    value = re.sub(r"[^a-z0-9가-힣\-]", "-", value)
    value = re.sub(r"-+", "-", value)
    value = value.strip("-")

    if not value:
        # fallback for names with unsupported chars
        # keep deterministic and path-safe
        value = re.sub(r"[^a-z0-9]", "-", value)
        value = re.sub(r"-+", "-", value).strip("-")

    if not value:
        raise ValueError("slug could not be generated from input")

    return value


def replace_tokens(template_text, replacements):
    text = template_text
    for key, val in replacements.items():
        text = text.replace("{{" + key + "}}", val)
    return text


def collect_archive_months(archives_dir: Path) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for year_dir in archives_dir.iterdir():
        if not year_dir.is_dir() or not year_dir.name.isdigit():
            continue
        for month_dir in year_dir.iterdir():
            if not month_dir.is_dir() or not re.fullmatch(r"\d{2}", month_dir.name):
                continue
            if not (month_dir / "index.html").exists():
                continue
            items.append((year_dir.name.zfill(4), month_dir.name))
    items.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return items


def render_archive_links(months: list[tuple[str, str]]) -> str:
    return "\n".join(MENU_LINK_TEMPLATE.format(year=year, month=month) for year, month in months)


def render_works_lines(months: list[tuple[str, str]]) -> str:
    return "\n".join(WORKS_LINE_TEMPLATE.format(year=year, month=month) for year, month in months)


def replace_nav_block(html: str, class_name: str, new_items: str) -> tuple[str, bool]:
    pattern = re.compile(rf'<nav class="{class_name}">[\s\S]*?</nav>')
    if not pattern.search(html):
        return html, False
    replacement = f'<nav class="{class_name}">\\n{new_items}\\n        </nav>'
    new_html, count = pattern.subn(replacement, html, count=1)
    return new_html, count > 0


def replace_works_block(html: str, months: list[tuple[str, str]]) -> tuple[str, bool]:
    pattern = re.compile(r"<li>&lt;works&gt;</li>\n([\s\S]*?)<li>&lt;/works&gt;</li>")
    if not pattern.search(html):
        return html, False
    works_lines = render_works_lines(months)
    if not works_lines:
        works_lines = ""
    replacement = f"<li>&lt;works&gt;</li>\\n{works_lines}\\n                <li>&lt;/works&gt;</li>"
    new_html, count = pattern.subn(replacement, html, count=1)
    return new_html, count > 0


def sync_navigation_links(base_dir: Path) -> list[Path]:
    archives_dir = base_dir / "archives"
    months = collect_archive_months(archives_dir)
    nav_links = render_archive_links(months)

    # 1) root index
    index_file = base_dir / "index.html"
    html = index_file.read_text(encoding="utf-8")
    changed_files: list[Path] = []
    changed = False

    html, web_changed = replace_nav_block(html, "web_nav", nav_links)
    html, mobile_changed = replace_nav_block(html, "mobile_nav", nav_links)
    html, works_changed = replace_works_block(html, months)
    changed = web_changed or mobile_changed or works_changed
    if changed:
        index_file.write_text(html, encoding="utf-8")
        changed_files.append(index_file)

    # 2) existing archive pages
    for archive_index in sorted((archives_dir.glob("[0-9][0-9][0-9][0-9]/*/index.html"))):
        html = archive_index.read_text(encoding="utf-8")
        w, wc = replace_nav_block(html, "web_nav", nav_links)
        m, mc = replace_nav_block(w, "mobile_nav", nav_links)
        if wc or mc:
            archive_index.write_text(m, encoding="utf-8")
            changed_files.append(archive_index)

    return changed_files


def run(cmd):
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{result.stdout}\n{result.stderr}")


def parse_existing_cards(block):
    # Returns list of (path, title, html)
    cards = []
    patterns = [
        re.compile(
            r'''<div class=\"work\">[\s\S]*?<a href=\"([^\"]+)\">[\s\S]*?<p class=\"gallery_info\">([^<]*)</p>[\s\S]*?</div>''',
            re.IGNORECASE,
        ),
        re.compile(
            r'''<a\s+class=\"archive-card\"\s+href=\"([^\"]+)\"[\s\S]*?<h3>(.*?)</h3>[\s\S]*?</a>''',
            re.IGNORECASE,
        ),
    ]
    for pattern in patterns:
        for match in pattern.finditer(block):
            path = match.group(1).strip()
            title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
            cards.append((path, title, match.group(0).strip()))
    return cards


def render_archive_block(existing_block, new_card, new_path, new_title):
    existing = [c for c in parse_existing_cards(existing_block)]

    # preserve existing cards + optional new card
    cards = {path: (title, html) for path, title, html in existing}
    cards[new_path] = (new_title, new_card)

    sorted_cards = sorted(cards.items(), key=lambda item: item[1][0].lower())
    inner = "\n\n".join(html for _, (_, html) in sorted_cards)
    if inner:
        inner = "\n" + inner + "\n"
    return inner


def update_archive(
    archives_dir: Path,
    year: str,
    month: str,
    card: str,
    work_path: str,
    title: str,
) -> None:
    year_dir = archives_dir / year / month
    year_dir.mkdir(parents=True, exist_ok=True)

    index_file = year_dir / "index.html"
    if not index_file.exists():
        if not ARCHIVE_TEMPLATE.exists():
            raise FileNotFoundError(f"Missing template: {ARCHIVE_TEMPLATE}")
        archive_html = ARCHIVE_TEMPLATE.read_text(encoding="utf-8")
        archive_html = replace_tokens(
            archive_html,
            {
                "YEAR": year,
                "MONTH": month,
            },
        )
        index_file.write_text(archive_html, encoding="utf-8")

    html = index_file.read_text(encoding="utf-8")
    if START_MARKER not in html or END_MARKER not in html:
        raise ValueError(f"Archive file missing AUTO markers: {index_file}")

    start = html.index(START_MARKER) + len(START_MARKER)
    end = html.index(END_MARKER)
    head, middle, tail = html[:start], html[start:end], html[end:]

    updated = render_archive_block(middle, card, work_path, title)
    if updated == middle:
        print("[skip] archive card already exists")
        return

    index_file.write_text(f"{head}{updated}{tail}", encoding="utf-8")
    print(f"[ok] updated archive index: {index_file}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Add artwork page + archive card from templates")
    parser.add_argument("--artist-name", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--year", required=True)
    parser.add_argument("--month", required=True)
    parser.add_argument("--description", default="")
    parser.add_argument("--image", required=True, help="Path to source image file")
    parser.add_argument("--artist-slug", default="")
    parser.add_argument("--work-slug", default="")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--no-git", action="store_true", help="Do not run git add/commit/push")

    args = parser.parse_args()

    year = str(args.year).zfill(4)
    month = str(args.month).zfill(2)

    artist_slug = args.artist_slug or slugify(args.artist_name)
    work_slug = args.work_slug or slugify(args.title)

    image_src = Path(args.image).expanduser()
    if not image_src.exists():
        raise FileNotFoundError(f"Image not found: {image_src}")
    image_ext = image_src.suffix.lower() or ".jpg"

    works_dir = BASE / "works"
    work_dir = works_dir / artist_slug / year / month / work_slug
    works_index = work_dir / "index.html"

    if works_index.exists() and not args.overwrite:
        raise FileExistsError(f"Work page already exists: {works_index}. Use --overwrite.")

    if not WORK_TEMPLATE.exists():
        raise FileNotFoundError(f"Missing template: {WORK_TEMPLATE}")

    # image copy
    image_dst = BASE / "assets" / "images" / "gallery" / year / month / f"{work_slug}{image_ext}"
    image_dst.parent.mkdir(parents=True, exist_ok=True)
    if image_dst.exists() and not args.overwrite:
        raise FileExistsError(f"Image already exists: {image_dst}. Use --overwrite.")
    shutil.copy2(image_src, image_dst)

    work_dir.mkdir(parents=True, exist_ok=True)
    template_html = WORK_TEMPLATE.read_text(encoding="utf-8")
    work_html = replace_tokens(
        template_html,
        {
            "TITLE": args.title,
            "ARTIST": args.artist_name,
            "YEAR": year,
            "MONTH": month,
            "DESCRIPTION": args.description,
            "IMAGE_PATH": f"/assets/images/gallery/{year}/{month}/{work_slug}{image_ext}",
        },
    )
    works_index.write_text(work_html, encoding="utf-8")

    # archive card
    if not CARD_TEMPLATE.exists():
        raise FileNotFoundError(f"Missing template: {CARD_TEMPLATE}")

    card_template = CARD_TEMPLATE.read_text(encoding="utf-8")
    work_path = f"/works/{artist_slug}/{year}/{month}/{work_slug}/"
    card_html = replace_tokens(
        card_template,
        {
            "WORK_PATH": work_path,
            "THUMBNAIL_PATH": f"/assets/images/gallery/{year}/{month}/{work_slug}{image_ext}",
            "TITLE": args.title,
            "ARTIST": args.artist_name,
        },
    )

    update_archive(
        archives_dir=BASE / "archives",
        year=year,
        month=month,
        card=card_html,
        work_path=work_path,
        title=args.title,
    )

    updated_pages = sync_navigation_links(BASE)
    staging_targets = {
        str(works_index),
        str(image_dst),
        str(BASE / "archives" / year / month / "index.html"),
        *(str(p) for p in updated_pages),
    }

    if not args.no_git:
        if staging_targets:
            run(["git", "add", *sorted(staging_targets)])
        run(["git", "commit", "-m", f"feat: add artwork {args.title}"])
        run(["git", "push"])

    print("[done]")
    print(f"  artist: {artist_slug}")
    print(f"  slug  : {work_slug}")
    print(f"  page  : /works/{artist_slug}/{year}/{month}/{work_slug}/")
    print(f"  image : /assets/images/gallery/{year}/{month}/{work_slug}{image_ext}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)
