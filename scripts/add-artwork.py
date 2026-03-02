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
import html
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from urllib.parse import parse_qs, urlparse
from pathlib import Path


BASE = Path(__file__).resolve().parent.parent
TEMPLATES = BASE / "templates"
WORK_TEMPLATE = TEMPLATES / "work-template.html"
ARCHIVE_TEMPLATE = TEMPLATES / "archive-template.html"
CARD_TEMPLATE = TEMPLATES / "archive-card-template.html"
NETWORK_DATA = BASE / "assets" / "data" / "network-catalog.json"
GALLERY_ROOT = BASE / "assets" / "images" / "gallery"

START_MARKER = "<!-- AUTO-GENERATED-START -->"
END_MARKER = "<!-- AUTO-GENERATED-END -->"
MENU_LINK_TEMPLATE = '            <a href="/archives/{year}/{month}/"><div class="menu">&gt; {year}.{month}</div></a>'
WORKS_LINE_TEMPLATE = "                <li>&gt; {year}.{month}</li>"
THUMBNAIL_EXTS = [".jpg", ".jpeg", ".png", ".webp", ".gif"]
LISTING_EXCLUDE_SLUGS = {"auto-test"}
LISTING_EXCLUDE_KEYWORDS = ("auto test", "auto-test")


YOUTUBE_THUMBNAILS = [
    "maxresdefault.jpg",
    "hqdefault.jpg",
    "mqdefault.jpg",
    "sddefault.jpg",
]


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKC", value.strip())
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


def is_hidden_work(work_slug: str, title: str) -> bool:
    slug = (work_slug or "").strip().lower()
    title_text = (title or "").strip().lower()
    if slug in LISTING_EXCLUDE_SLUGS:
        return True
    if slug.startswith("auto-"):
        return True
    for keyword in LISTING_EXCLUDE_KEYWORDS:
        if keyword in title_text:
            return True
    if "테스트" in title_text and "auto" in slug:
        return True
    if "자동" in title_text and "생성" in title_text:
        return True
    return False


def strip_html(value: str) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", "", value)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def extract_gallery_thumbnail(
    html_text: str,
    year: str,
    month: str,
    work_slug: str,
    fallback: str,
    work_path: str,
) -> str:
    """Parse gallery image path from work page and normalize fallback.

    Prefer dedicated work image wrapper first, then gallery card style.
    """
    candidates = [
        re.compile(
            r'<div class="image-wrapper"[\s\S]*?<img[^>]+src="([^"]+)"',
            re.IGNORECASE,
        ),
        re.compile(
            r'<img[^>]+class="gallery_img"[^>]+src="([^"]+)"',
            re.IGNORECASE,
        ),
    ]
    for pattern in candidates:
        match = pattern.search(html_text)
        if not match:
            continue
        path = match.group(1).strip()
        if path.startswith("/assets/images/gallery/"):
            return path

    for ext in THUMBNAIL_EXTS:
        candidate = f"{year}/{month}/{work_slug}{ext}"
        if (GALLERY_ROOT / candidate).exists():
            return f"/assets/images/gallery/{candidate}"

    # 3) Use archive card thumbnail if available
    thumbnail_from_archive = find_archive_thumbnail(work_path)
    if thumbnail_from_archive:
        return thumbnail_from_archive

    # 4) If this page has a youtube/video embed, fallback to video thumbnail
    video_thumbnail = extract_video_thumbnail(html_text)
    if video_thumbnail:
        return video_thumbnail

    return fallback


def parse_youtube_id(src: str) -> str:
    parsed = urlparse(src)
    if parsed.netloc.endswith("youtube.com") and parsed.path.startswith("/embed/"):
        return parsed.path.split("/", 2)[-1].split("?")[0].split("&")[0]
    if parsed.netloc in {"youtu.be"}:
        return parsed.path.strip("/").split("?")[0].split("&")[0]
    if parsed.netloc.endswith("youtube.com") and parsed.path == "/watch":
        vid = parse_qs(parsed.query).get("v", [""])
        return vid[0] if vid else ""
    return ""


def extract_video_thumbnail(html_text: str) -> str:
    # Priority: iframe src
    iframe_match = re.search(
        r'<iframe[^>]+src="([^"]+)"',
        html_text,
        re.IGNORECASE,
    )
    if iframe_match:
        vid = parse_youtube_id(iframe_match.group(1).strip())
        if vid:
            for suffix in YOUTUBE_THUMBNAILS:
                return f"https://i.ytimg.com/vi/{vid}/{suffix}"

    poster_match = re.search(
        r'<video[^>]+poster="([^"]+)"',
        html_text,
        re.IGNORECASE,
    )
    if poster_match:
        poster = poster_match.group(1).strip()
        if poster.startswith("/assets/images/"):
            return poster
    return ""


def find_archive_thumbnail(work_path: str) -> str:
    # work_path: "/works/{artist}/{year}/{month}/{slug}/"
    archives_root = BASE / "archives"
    if not archives_root.exists():
        return ""

    path_pattern = re.compile(
        rf'<a\s+href="{re.escape(work_path)}"[^>]*>[\s\S]*?<img[^>]+src="([^"]+)"',
        re.IGNORECASE,
    )
    for archive_file in sorted(archives_root.glob("*/*/index.html")):
        try:
            html_text = archive_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        match = path_pattern.search(html_text)
        if not match:
            continue
        src = match.group(1).strip()
        if src.startswith("/assets/images/gallery/"):
            return src
    return ""


def parse_work_page(index_file: Path, artist_slug: str, year: str, month: str, work_slug: str) -> dict[str, str]:
    html_text = index_file.read_text(encoding="utf-8", errors="ignore")

    title = "Unknown"
    title_match = re.search(r"<title>[^|>]*\|\s*(.*?)</title>", html_text, flags=re.IGNORECASE)
    if title_match:
        title = strip_html(title_match.group(1)) or title

    artist = artist_slug
    artist_match = re.search(
        rf'<a\s+class="member"[^>]*href="/works/{re.escape(artist_slug)}/{year}/{month}/{re.escape(work_slug)}/"[^>]*>(.*?)</a>',
        html_text,
        re.IGNORECASE | re.DOTALL,
    )
    if artist_match:
        artist = strip_html(artist_match.group(1)) or artist

    description = ""
    desc_match = re.search(r'<div class="work_text2">(.*?)</div>', html_text, re.IGNORECASE | re.DOTALL)
    if not desc_match:
        desc_match = re.search(r'<p class="description">(.*?)</p>', html_text, re.IGNORECASE | re.DOTALL)
    if desc_match:
        description = strip_html(desc_match.group(1))

    work_path = f"/works/{artist_slug}/{year}/{month}/{work_slug}/"
    fallback = f"/assets/images/gallery/{year}/{month}/{work_slug}.jpg"
    thumb_path = extract_gallery_thumbnail(
        html_text,
        year,
        month,
        work_slug,
        fallback,
        work_path,
    )

    return {
        "id": f"{artist_slug}:{year}:{month}:{work_slug}",
        "title": title,
        "artist": artist,
        "artistSlug": artist_slug,
        "year": year,
        "month": month,
        "path": f"/works/{artist_slug}/{year}/{month}/{work_slug}/",
        "thumbnail": thumb_path,
        "description": description,
    }


def collect_work_catalog(works_dir: Path) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for index_file in sorted(works_dir.glob("*/*/*/*/index.html")):
        rel = index_file.relative_to(works_dir)
        if len(rel.parts) != 5:
            continue
        artist_slug, year, month, work_slug, _ = rel.parts
        if not year.isdigit() or not month.isdigit():
            continue
        year = year.zfill(4)
        month = month.zfill(2)
        try:
            item = parse_work_page(index_file, artist_slug, year, month, work_slug)
            if is_hidden_work(work_slug, item.get("title", "")):
                continue
            items.append(item)
        except Exception:
            continue
    items.sort(key=lambda item: (item["year"], item["month"], item["title"].lower()), reverse=True)
    return items


def load_mock_items(output_file: Path) -> list[dict[str, str]]:
    if not output_file.exists():
        return []
    try:
        raw_payload = json.loads(output_file.read_text(encoding="utf-8"))
    except Exception:
        return []

    if not isinstance(raw_payload, dict):
        return []

    raw_items = raw_payload.get("mockItems")
    if not isinstance(raw_items, list):
        return []

    seen = set()
    normalized = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        if item.get("isMock") not in {None, True} and str(item.get("isMock")).lower() not in {"true", "1", "yes", "on"}:
            continue

        item = dict(item)
        item_id = item.get("id")
        if not item_id:
            continue
        if item_id in seen:
            continue
        seen.add(item_id)
        item["isMock"] = True
        normalized.append(item)
    return normalized


def build_network_catalog(works_dir: Path, output_file: Path) -> Path:
    items = collect_work_catalog(works_dir)
    mock_items = load_mock_items(output_file)
    payload: dict[str, object] = {}
    if output_file.exists():
        try:
            loaded = json.loads(output_file.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                payload = loaded
        except Exception:
            payload = {}

    payload = {
        "items": items,
        "mockItems": mock_items,
        "count": len(items),
        "mockCount": len(mock_items),
    }
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] updated network catalog: {output_file}")
    return output_file


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

    # 3) existing work detail pages
    works_dir = base_dir / "works"
    if works_dir.exists():
        for work_index in sorted(works_dir.rglob("index.html")):
            html = work_index.read_text(encoding="utf-8")
            w, wc = replace_nav_block(html, "web_nav", nav_links)
            m, mc = replace_nav_block(w, "mobile_nav", nav_links)
            if wc or mc:
                work_index.write_text(m, encoding="utf-8")
                changed_files.append(work_index)

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
    parser.add_argument("--artist-name")
    parser.add_argument("--artist", dest="artist", help="Alias for --artist-name.")
    parser.add_argument("--title")
    parser.add_argument("--year")
    parser.add_argument("--month")
    parser.add_argument("--description", default="")
    parser.add_argument("--image", help="Path to source image file")
    parser.add_argument("--artist-slug", default="")
    parser.add_argument("--work-slug", default="")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--no-git", action="store_true", help="Do not run git add/commit/push")
    parser.add_argument(
        "--sync-navigation",
        action="store_true",
        help="Sync navigation links only, without creating artwork",
    )
    parser.add_argument(
        "--sync-network",
        action="store_true",
        help="Rebuild network catalog only, without creating artwork",
    )

    args = parser.parse_args()

    if args.sync_navigation:
        updated_pages = sync_navigation_links(BASE)
        print("[done] sync navigation")
        for path in updated_pages:
            print(f"  updated: {path}")
    if args.sync_network:
        build_network_catalog(works_dir=BASE / "works", output_file=NETWORK_DATA)

    if args.sync_navigation or args.sync_network:
        return

    if not (args.artist_name or args.artist) or not args.title or not args.year or not args.month or not args.image:
        raise ValueError(
            "Missing required fields: --artist-name (or --artist), --title, --year, --month, --image"
        )

    year = str(args.year).zfill(4)
    month = str(args.month).zfill(2)

    artist_name = args.artist_name or args.artist
    artist_slug = args.artist_slug or slugify(artist_name)
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

    nav_links = render_archive_links(collect_archive_months(BASE / "archives"))
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
            "ARTIST": artist_name,
            "ARTIST_SLUG": artist_slug,
            "WORK_SLUG": work_slug,
            "YEAR": year,
            "MONTH": month,
            "DESCRIPTION": args.description,
            "IMAGE_PATH": f"/assets/images/gallery/{year}/{month}/{work_slug}{image_ext}",
            "NAV_WEB": nav_links,
            "NAV_MOBILE": nav_links,
        },
    )
    works_index.write_text(work_html, encoding="utf-8")

    hidden_from_listing = is_hidden_work(work_slug, args.title)
    if not hidden_from_listing:
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
                "ARTIST": artist_name,
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
    else:
        print(f"[skip] hidden from archive/network: {artist_slug}/{year}/{month}/{work_slug}")

    updated_pages = sync_navigation_links(BASE)
    build_network_catalog(works_dir=BASE / "works", output_file=NETWORK_DATA)
    staging_targets = {
        str(works_index),
        str(image_dst),
        *(str(p) for p in updated_pages),
        str(NETWORK_DATA),
    }
    if not hidden_from_listing:
        staging_targets.add(str(BASE / "archives" / year / month / "index.html"))

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
