#!/usr/bin/env python3
"""Source and apply hero images for bags.json variant records that lack one.

Same fetch/apply split as draft_evidence.py, for the same reason. Everything
mechanical -- picking a candidate evidence record per variant, fetching the
real post JSON to find its image, downloading, hashing, and checking it is a
genuine JPEG -- is done here for free. The one thing that can't be automated
is deciding whether a photo actually looks like a reviewer's own casual
snapshot rather than official product photography or something privacy-
sensitive: that needs a human (or a vision-capable reviewer) to actually look
at the downloaded file before it enters the public data graph. So `fetch`
only stages candidates under local-private/ and writes a manifest; `apply`
registers whatever survives that review.

  --fetch  pick a candidate evidence record per bag missing a tile_media_id,
           fetch each one's real image via the authenticated Reddit client,
           download it to a private staging directory, and write a manifest
           for review. Requires REDDIT_CLIENT_ID (see .env.example).
  --apply  read a reviewed manifest and register the surviving entries:
           move the file into media/evidence/, add the media.json row
           (usage_scope=variant_tile, never target_tile -- that scope is
           reserved for family-level heroes and is checked 1:1 against every
           family's tile_media_id), link it into the source evidence record's
           media_ids, and set the bag's tile_media_id.

Sourcing rules (same contract as the family-level hero backfill in
docs/superpowers/specs/2026-08-13-missing-collection-hero-images-design.md):
only a direct Reddit-hosted image tied to an already-normalized evidence
record. No official product photography, no PSP with identifying order data,
no external-preview.redd.it (that host reflects third-party links, not
uploads). A candidate with no qualifying image is reported, not guessed.

Before trusting a `--fetch` manifest, open a sample of the staged JPEGs and
look at them. This tool cannot tell a casual in-hand photo from a studio
product shot; a real one did make it through the image-format checks during
the Speedy backfill this script was extracted from.

Usage:
  python3 scripts/backfill_variant_heroes.py --fetch --family bag-family-louis-vuitton-speedy
  # ...look at local-private/hero-staging/<family-slug>/*.jpg, edit the
  # manifest to drop anything that doesn't belong...
  python3 scripts/backfill_variant_heroes.py --apply local-private/hero-staging/<family-slug>/manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from model import DATA, ROOT, load  # noqa: E402
from scrape_reddit import RedditClient  # noqa: E402
from validate import jpeg_dimensions  # noqa: E402

STAGING_ROOT = ROOT / "local-private" / "hero-staging"
MEDIA_PATH = DATA / "media.json"
EVIDENCE_PATH = DATA / "evidence.json"
BAGS_PATH = DATA / "bags.json"
FAMILIES_PATH = DATA / "bag_families.json"

# Evidence types most likely to be the reviewer's own casual photo rather than
# a screenshot bundle of seller PSPs (which risk showing order/payment detail
# in-frame) or a pure discussion thread (which may have no photo at all).
EVIDENCE_TYPE_PREFERENCE = (
    "in_hand_review", "long_term_wear", "auth_comparison", "factory_comparison", "psp_qc",
)

# Hosts that serve a genuine upload. external-preview.redd.it reflects a
# *third-party* link (e.g. a seller catalog page) through Reddit's proxy and
# is explicitly out of scope -- see the design doc this tool follows. This is
# an exact-hostname allowlist, not a substring check: "preview.redd.it" in
# "external-preview.redd.it" is true, which would silently let the excluded
# host back in.
ALLOWED_IMAGE_HOSTS = frozenset({"i.redd.it", "preview.redd.it"})


def _is_allowed_image_url(url: str) -> bool:
    return urlparse(url).hostname in ALLOWED_IMAGE_HOSTS


USER_AGENT = "OG-Rep-Hub-Research/1.0 (public-source catalog)"


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-")


def pick_candidates(bag: dict[str, Any], evidence: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    linked = [row for row in evidence if bag["id"] in (row.get("bag_ids") or [])]

    def sort_key(row: dict[str, Any]) -> tuple[int, int]:
        lane = row.get("evidence_type")
        rank = EVIDENCE_TYPE_PREFERENCE.index(lane) if lane in EVIDENCE_TYPE_PREFERENCE else len(EVIDENCE_TYPE_PREFERENCE)
        return (rank, -len(row.get("paraphrase") or ""))

    linked.sort(key=sort_key)
    return linked[:limit]


def extract_image_url(post: dict[str, Any]) -> tuple[str | None, int | None, int | None]:
    """Return (url, width, height) for a genuine Reddit-hosted image, or (None, None, None)."""
    if post.get("is_gallery") and post.get("media_metadata"):
        order = [g["media_id"] for g in post.get("gallery_data", {}).get("items", [])]
        keys = order or list(post["media_metadata"].keys())
        for key in keys:
            source = (post["media_metadata"].get(key) or {}).get("s", {})
            url = source.get("u")
            if url and _is_allowed_image_url(url):
                return url.replace("&amp;", "&"), source.get("x"), source.get("y")
        return None, None, None

    # Text/self posts can still contain a genuine inline Reddit upload in
    # media_metadata even when Reddit does not mark the post as a gallery.
    # Check it before the preview fallback so the fetch pass does not discard
    # an otherwise valid owner photo.
    if post.get("media_metadata"):
        for metadata in post["media_metadata"].values():
            source = (metadata or {}).get("s", {})
            url = source.get("u")
            if url and _is_allowed_image_url(url):
                return url.replace("&amp;", "&"), source.get("x"), source.get("y")

    if post.get("post_hint") == "image" and post.get("url"):
        url = post["url"]
        if _is_allowed_image_url(url):
            preview = (post.get("preview") or {}).get("images", [{}])[0].get("source", {})
            return url.replace("&amp;", "&"), preview.get("width"), preview.get("height")

    preview_images = (post.get("preview") or {}).get("images")
    if preview_images:
        source = preview_images[0].get("source", {})
        url = source.get("url")
        if url and _is_allowed_image_url(url):
            return url.replace("&amp;", "&"), source.get("width"), source.get("height")

    return None, None, None


def fetch_post(client: RedditClient, subreddit: str, post_id: str) -> dict[str, Any] | None:
    try:
        data = client.get_json(f"https://www.reddit.com/r/{subreddit}/comments/{post_id}.json?raw_json=1")
        return data[0]["data"]["children"][0]["data"]
    except Exception as error:  # noqa: BLE001 -- report and move on, one bad post must not stop the batch
        print(f"    fetch failed: {error}", file=sys.stderr)
        return None


def download(url: str, dest: Path) -> bytes | None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read()
    except Exception as error:  # noqa: BLE001
        print(f"    download failed: {error}", file=sys.stderr)
        return None
    dest.write_bytes(body)
    return body


def cmd_fetch(args: argparse.Namespace) -> int:
    families = load("bag_families")
    bags = load("bags")
    evidence = load("evidence")

    family = next((f for f in families if f["id"] == args.family or f["model"] == args.family), None)
    if not family:
        print(f"no family matches {args.family!r}", file=sys.stderr)
        return 1

    targets = [b for b in bags if b["family_id"] == family["id"] and not b.get("tile_media_id")]
    if not targets:
        print("every variant in this family already has a tile_media_id")
        return 0

    slug = family["slug"]
    staging_dir = STAGING_ROOT / slug
    staging_dir.mkdir(parents=True, exist_ok=True)

    client = RedditClient(delay=args.delay)
    if not client.authenticated:
        print("REDDIT_CLIENT_ID is not set -- source .env first (see .env.example)", file=sys.stderr)
        return 1

    manifest: list[dict[str, Any]] = []
    for bag in targets:
        print(f"{bag['id']} ({bag['name']})")
        candidates = pick_candidates(bag, evidence, args.candidates_per_variant)
        if not candidates:
            print("  no linked evidence at all")
            manifest.append({"bag_id": bag["id"], "name": bag["name"], "status": "no_evidence"})
            continue

        found = False
        for row in candidates:
            match = re.search(r"/comments/([a-z0-9]+)/", row["url"])
            if not match:
                continue
            post_id = match.group(1)
            print(f"  trying {row['id']} ({row['evidence_type']}) ...")
            post = fetch_post(client, row["subreddit"], post_id)
            if post is None:
                continue
            url, width, height = extract_image_url(post)
            if not url:
                print("    no qualifying image on this post")
                continue

            file_slug = f"{slugify(family['model'])}-{bag['id'].removeprefix('bag-').removeprefix(slugify(family['model']) + '-')}-reddit"
            file_slug = re.sub(r"-+", "-", file_slug)
            dest = staging_dir / f"{file_slug}.jpg"
            body = download(url, dest)
            if body is None:
                continue

            dims = jpeg_dimensions(dest)
            if dims is None:
                print(f"    not a real JPEG (source was {url.split('?')[0].rsplit('.', 1)[-1]}); skipping")
                dest.unlink(missing_ok=True)
                continue

            sha256 = hashlib.sha256(body).hexdigest()
            manifest.append({
                "bag_id": bag["id"], "name": bag["name"], "status": "candidate",
                "evidence_id": row["id"], "author": post.get("author"), "subreddit": row["subreddit"],
                "permalink": f"https://www.reddit.com{post.get('permalink')}",
                "source_url": url, "file": str(dest.relative_to(ROOT)),
                "sha256": sha256, "width": dims[0], "height": dims[1],
            })
            print(f"    OK  {dims[0]}x{dims[1]}  {dest.name}")
            found = True
            break

        if not found:
            manifest.append({"bag_id": bag["id"], "name": bag["name"], "status": "no_image_found"})
        time.sleep(args.delay)

    manifest_path = staging_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    ok = sum(1 for row in manifest if row["status"] == "candidate")
    print(f"\n{ok}/{len(targets)} variants got a candidate image")
    print(f"manifest: {manifest_path.relative_to(ROOT)}")
    print(f"staged photos: {staging_dir.relative_to(ROOT)}/*.jpg")
    print("\nLook at every staged photo before running --apply. Delete any manifest row")
    print("(and its file) that looks like product photography, shows identifying detail,")
    print("or otherwise doesn't belong, the same way one Speedy candidate was dropped.")
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    manifest = json.loads(args.manifest.read_text())
    candidates = [row for row in manifest if row["status"] == "candidate"]
    if not candidates:
        print("no candidate rows in this manifest")
        return 0

    media = load("media")
    evidence = load("evidence")
    bags = load("bags")
    families = load("bag_families")
    bags_by_id = {b["id"]: b for b in bags}
    ev_by_id = {r["id"]: r for r in evidence}
    existing_media_ids = {m["id"] for m in media}
    existing_urls = {m["source_url"] for m in media}

    problems = []
    for row in candidates:
        if row["bag_id"] not in bags_by_id:
            problems.append(f"{row['bag_id']}: unknown bag id")
        if row["evidence_id"] not in ev_by_id:
            problems.append(f"{row['evidence_id']}: unknown evidence id")
        src = ROOT / row["file"]
        if not src.is_file():
            problems.append(f"{row['file']}: staged file missing (was it deleted during review?)")
    if problems:
        print("Fix these first:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    added = 0
    for row in candidates:
        media_id = f"media-{Path(row['file']).stem}"
        if media_id in existing_media_ids or row["source_url"] in existing_urls:
            print(f"skip (already registered): {media_id}")
            continue

        bag = bags_by_id[row["bag_id"]]
        dest = ROOT / "media" / "evidence" / Path(row["file"]).name
        shutil.copyfile(ROOT / row["file"], dest)

        media.append({
            "id": media_id,
            "path": str(dest.relative_to(ROOT)),
            "attribution": f"u/{row['author']} via r/{row['subreddit']}",
            "source_url": row["source_url"],
            "post_url": row["permalink"],
            "author": row["author"],
            "subreddit": row["subreddit"],
            "capture_date": args.capture_date,
            "removal_checked_at": args.capture_date,
            "sha256": row["sha256"],
            "width": row["width"],
            "height": row["height"],
            "research_purpose": f"Receipt-linked community variant-tile image for the {bag['name']} variant.",
            "alt": row.get("alt") or f"{bag['name']} shown in a Reddit reviewer's photograph.",
            "source_platform": "Reddit",
            "usage_scope": "variant_tile",
            "evidence_id": row["evidence_id"],
        })
        ev_row = ev_by_id[row["evidence_id"]]
        ev_row.setdefault("media_ids", [])
        if media_id not in ev_row["media_ids"]:
            ev_row["media_ids"].append(media_id)
        bag["tile_media_id"] = media_id
        added += 1
        print(f"registered {media_id} -> {bag['id']}")

    for path, rows in ((MEDIA_PATH, media), (EVIDENCE_PATH, evidence), (BAGS_PATH, bags)):
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")

    print(f"\n{added} media entries registered.")
    print("Now run: python3 scripts/validate.py && python3 scripts/score.py --check")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fetch", action="store_true", help="stage candidate images for a family's variants")
    mode.add_argument("--apply", type=Path, dest="manifest", help="register a reviewed manifest's surviving rows")
    parser.add_argument("--family", help="family id or model name (required with --fetch)")
    parser.add_argument("--candidates-per-variant", type=int, default=4)
    parser.add_argument("--delay", type=float, default=0.7)
    parser.add_argument("--capture-date", default=time.strftime("%Y-%m-%d"))
    args = parser.parse_args()

    if args.fetch:
        if not args.family:
            parser.error("--fetch requires --family")
        return cmd_fetch(args)
    return cmd_apply(args)


if __name__ == "__main__":
    raise SystemExit(main())
