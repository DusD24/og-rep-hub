# Reddit Evidence Crawl Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a resumable, privacy-safe public Reddit crawl for four seeded rep communities, normalize the strongest new receipts, and expand the catalog’s collections and research view without weakening evidence gates.

**Architecture:** A standard-library Python crawler reads a committed source registry, fetches public Reddit HTML/JSON with bounded retries, sanitizes sensitive content, and writes resumable local-private run artifacts. Public JSON remains the manual normalization boundary: selected candidates are copied into existing evidence/family/variant records only after source and privacy review. Existing site rendering is extended through data-driven research records and dynamic validation counts.

**Tech Stack:** Python 3.13 standard library, JSON/JSONL, `urllib.request`, `unittest`, static HTML/CSS/JavaScript, existing normalized JSON data model.

## Global Constraints

- Seed `r/RealRepLadies`, `r/RepTherapy`, `r/RepLadiesWorld`, and `r/RepCulture_Bags`; discover additional subreddits only from public wiki/sidebar links and a bounded queue.
- Keep raw and candidate captures under ignored `local-private/research-runs/`; never commit raw post/comment bodies.
- Redact phone numbers, email addresses, payment/account references, addresses, private-message language, credentials, contact URLs, and secret-like tokens before persistence.
- Do not automatically promote candidates into `data/evidence.json`, `data/contacts.json`, seller rankings, or public claims.
- Preserve exact variant distinctions, seller/factory separation, author independence, publication dates, attribution, conflicting observations, and time-bound availability.
- Keep price display-only and do not send outreach or facilitate purchases.
- Use TDD for every new production behavior: write the failing test, run it, implement the minimum, run the focused test, then run the full suite.

---

### Task 1: Add the safe source registry and crawler test fixtures

**Files:**
- Create: `data/research_sources.json`
- Create: `tests/test_scraper.py`
- Create: `scripts/scrape_reddit.py`

**Interfaces:**
- `load_registry(path: Path) -> dict`
- `sanitize_text(value: str) -> tuple[str, dict[str, bool]]`
- `canonical_subreddit_url(value: str) -> str | None`
- `discover_subreddits(html: str, known: set[str]) -> list[str]`

- [ ] **Step 1: Write the failing registry and sanitization tests**

```python
def test_registry_has_four_seed_communities_and_review_queries():
    registry = load_registry(ROOT / "data" / "research_sources.json")
    names = {row["subreddit"] for row in registry["sources"]}
    self.assertTrue({"RealRepLadies", "RepTherapy", "RepLadiesWorld", "RepCulture_Bags"} <= names)
    self.assertTrue({"review", "QC", "PSP", "receipt", "wear"} <= set(registry["search_terms"]))

def test_sanitize_text_redacts_sensitive_public_fields_without_losing_review_signal():
    text, flags = sanitize_text(
        "Seller WhatsApp +86 123 456 7890; paid $240 by PayPal; review says leather is soft."
    )
    self.assertNotIn("123 456 7890", text)
    self.assertNotIn("$240", text)
    self.assertIn("leather is soft", text)
    self.assertEqual(flags["contact_present"], True)
    self.assertEqual(flags["payment_present"], True)

def test_discover_subreddits_only_returns_public_reddit_subreddit_paths():
    html = '<a href="https://www.reddit.com/r/NewRepBags/">new</a><a href="https://example.com/r/nope">no</a>'
    self.assertEqual(discover_subreddits(html, {"RepCulture_Bags"}), ["NewRepBags"])
```

- [ ] **Step 2: Run the focused tests and verify they fail because the scraper API is absent**

Run: `python3 -m unittest tests.test_scraper -v`

Expected: FAIL with import or missing-function errors for `scripts/scrape_reddit.py`.

- [ ] **Step 3: Add the registry and minimal pure helpers**

Use a top-level object with `schema_version`, `last_verified`, `max_discovered_subreddits`, `search_terms`, and `sources`. Each source has `subreddit`, `landing_url`, `wiki_paths`, and `include_comments`. Use only safe public URLs and no captured content.

Implement `sanitize_text` with ordered substitutions for URLs containing WhatsApp/Telegram, email/phone patterns, payment/account phrases, address-like lines, private-message phrases, credentials, and secret-like tokens. Return the redacted string plus booleans such as `contact_present`, `payment_present`, `address_present`, `private_message_present`, and `secret_present`.

- [ ] **Step 4: Run the focused tests and confirm they pass**

Run: `python3 -m unittest tests.test_scraper -v`

Expected: all registry, sanitization, and subreddit-discovery tests pass.

- [ ] **Step 5: Commit the registry and pure helper contract**

```bash
git add data/research_sources.json scripts/scrape_reddit.py tests/test_scraper.py
git commit -m "feat: add privacy-safe Reddit crawl contracts"
```

### Task 2: Implement the resumable public Reddit crawler

**Files:**
- Modify: `scripts/scrape_reddit.py`
- Modify: `tests/test_scraper.py`

**Interfaces:**
- `class RedditClient`: `get_json(url: str) -> object`, `get_text(url: str) -> str`
- `class RunStore`: `load_manifest() -> dict`, `save_manifest(manifest: dict) -> None`, `append_capture(record: dict) -> bool`
- `class RedditScraper`: `run() -> dict`
- CLI: `python3 scripts/scrape_reddit.py --registry data/research_sources.json --run-dir local-private/research-runs/<run-id> --max-pages 3 --max-posts 250 --delay 1.5`

- [ ] **Step 1: Write failing tests for endpoint construction, pagination, resume, and retry isolation**

```python
def test_search_endpoint_encodes_query_and_cursor():
    self.assertIn("restrict_sr=1", search_url("RepCulture_Bags", "receipt", "t3_after"))
    self.assertIn("after=t3_after", search_url("RepCulture_Bags", "receipt", "t3_after"))

def test_resume_skips_post_ids_already_in_manifest():
    store = RunStore(self.run_dir)
    store.append_capture({"id": "post-1", "kind": "post"})
    scraper = RedditScraper(self.registry, store, client=FakeClient(...), max_posts=10)
    summary = scraper.run()
    self.assertEqual(summary["new_capture_count"], 0)

def test_one_failed_endpoint_is_recorded_and_other_sources_continue():
    client = FakeClient(fail_urls={"https://www.reddit.com/r/RepTherapy/wiki/"})
    summary = RedditScraper(self.registry, RunStore(self.run_dir), client=client).run()
    self.assertGreater(summary["successful_endpoint_count"], 0)
    self.assertTrue(summary["errors"])
```

- [ ] **Step 2: Run focused tests and verify the missing crawler behavior fails**

Run: `python3 -m unittest tests.test_scraper -v`

Expected: FAIL on endpoint helpers, manifest behavior, and error isolation.

- [ ] **Step 3: Implement the minimum crawler**

Construct public endpoints for about, sidebar, wiki, search, post metadata, and comments. Use `urllib.request.Request` with a descriptive user agent, `Accept: application/json` for JSON, bounded retries for 429/5xx/network errors, and `time.sleep(delay)` between requests. Parse search `data.children` and `data.after`; parse comment listing trees recursively up to `max_comments`.

For each post/comment, emit a sanitized capture containing `id`, `kind`, `url`, `subreddit`, `author`, `publication_date`, `title`, `flair`, sanitized `text`, `redaction_flags`, and `captured_at`. Deduplicate by `kind:id` and write JSONL records atomically through the run store. Write `manifest.json`, `candidates.json`, and `run-summary.json` after each source/query boundary so interruption leaves resumable progress.

Extract candidate records with `candidate_id`, `source_id`, `url`, `subreddit`, `author`, `publication_date`, `title`, `flair`, `evidence_type`, `bag_terms`, `seller_terms`, `factory_terms`, `redacted_excerpt`, `redaction_flags`, and `status: needs_normalization`. Classify evidence from flair/title/text using explicit precedence: QC/PSP, long-term wear, auth comparison, factory comparison, in-hand review, seller context, collection, W2C, discussion, then other.

Inspect landing/sidebar/wiki HTML for `/r/<name>` links, exclude already-known names, cap discovered names from the registry, and record disabled/empty wiki states instead of treating them as fatal errors.

- [ ] **Step 4: Run the focused crawler tests and confirm green**

Run: `python3 -m unittest tests.test_scraper -v`

Expected: all fake-transport tests pass with no network calls.

- [ ] **Step 5: Commit the crawler**

```bash
git add scripts/scrape_reddit.py tests/test_scraper.py
git commit -m "feat: add resumable Reddit evidence crawler"
```

### Task 3: Replace fixed normalized-data counts with data-derived publication gates

**Files:**
- Modify: `scripts/validate.py`
- Modify: `tests/test_data.py`
- Modify: `tests/test_site.py`

**Interfaces:**
- `validate()` continues to return `list[str]`.
- Published-family tile count equals the number of `publication_status == "published"` families.
- Evidence count is no longer hard-coded to 38; every evidence row still must satisfy the existing relationship, safety, attribution, and date rules.

- [ ] **Step 1: Write failing tests for an additional published-family fixture and dynamic counts**

Add a test fixture through a temporary copy or a pure count helper rather than mutating committed data:

```python
def test_validation_rules_use_published_family_count_not_launch_constant():
    source = json.loads((ROOT / "scripts" / "validate.py").read_text(encoding="utf-8"))
    self.assertNotIn("expected exactly 38 normalized receipts", source)
    self.assertNotIn("expected exactly 12 launch families", source)
```

Add site-contract assertions that family/evidence counts are computed from loaded data and that research copy does not say “12 launch families” as a universal limit.

- [ ] **Step 2: Run the focused tests and watch them fail against fixed constants**

Run: `python3 -m unittest tests.test_data.DataTests.test_validation_rules_use_published_family_count_not_launch_constant tests.test_site.SiteContractTests -v`

Expected: FAIL because the validator and tests still encode the old constants.

- [ ] **Step 3: Implement data-derived gates**

Use `published_families = [row for row in family_rows if row.get("publication_status") == "published"]` and require each published family to have a tile, linked evidence, two authors, primary-subreddit coverage, and image-ready media. Set target-media expectations from `len(published_families)`; allow research-queue candidates to remain without tiles. Replace fixed evidence count checks with nonempty/relationship checks and leave existing data-specific tests as regression expectations only where they describe actual current records.

- [ ] **Step 4: Run focused data/site tests and then the full suite**

Run: `python3 -m unittest tests.test_data tests.test_site -v`

Expected: all existing data and site tests pass after updating only stale fixed-count assertions.

- [ ] **Step 5: Commit dynamic validation gates**

```bash
git add scripts/validate.py tests/test_data.py tests/test_site.py
git commit -m "refactor: make catalog publication gates data-driven"
```

### Task 4: Add the crawl to the public research view and source registry documentation

**Files:**
- Modify: `data/research.json`
- Modify: `RESEARCH_SUMMARY.md`
- Modify: `README.md`
- Modify: `tests/test_data.py`
- Modify: `tests/test_site.py`

**Interfaces:**
- `research.json` keeps existing `campaigns`, `research_lanes`, `scan_log`, glossary, and publication requirements.
- Add one dated crawl campaign and one scan log per run; candidates remain labeled `needs_normalization`.
- `renderResearch()` continues to render candidate sources through the existing scan-log path.

- [ ] **Step 1: Write failing tests for four-lane coverage and crawl metadata**

```python
def test_research_registry_and_log_cover_repculture_bags():
    research = load("research")
    lanes = {row["subreddit_focus"] for row in research["research_lanes"]}
    self.assertIn("RepCulture_Bags", lanes)
    self.assertTrue(any(row["status"] == "candidate_leads" for row in research["scan_log"]))
```

- [ ] **Step 2: Run the focused test and verify it fails before data changes**

Run: `python3 -m unittest tests.test_data.DataTests.test_research_registry_and_log_cover_repculture_bags -v`

Expected: FAIL because the current research log has no RepCulture_Bags lane.

- [ ] **Step 3: Add safe public research metadata**

Add a crawl campaign describing the four seeded communities, the disabled-wiki states, the public review/QC fields learned from the source guides, query coverage, and the run date. Add only source URLs, redacted notes, titles, authors, dates, evidence lanes, and unresolved status to `scan_log`; do not copy contact values, payment data, private messages, or actual replies. Update README and summary language to describe the crawl as evidence collection, not authentication or seller endorsement.

- [ ] **Step 4: Run the focused test and full site/data suite**

Run: `python3 -m unittest tests.test_data tests.test_site -v`

Expected: all tests pass and the Research route contains the new lane/candidates through existing rendering.

- [ ] **Step 5: Commit public research metadata**

```bash
git add data/research.json RESEARCH_SUMMARY.md README.md tests/test_data.py tests/test_site.py
git commit -m "feat: add multi-subreddit research lane"
```

### Task 5: Run the broad crawl and normalize high-confidence receipts/collections

**Files:**
- Generated locally (ignored): `local-private/research-runs/<run-id>/manifest.json`
- Generated locally (ignored): `local-private/research-runs/<run-id>/captures.jsonl`
- Generated locally (ignored): `local-private/research-runs/<run-id>/candidates.json`
- Generated locally (ignored): `local-private/research-runs/<run-id>/run-summary.json`
- Modify after review: `data/evidence.json`, `data/bag_families.json`, `data/bags.json`, `data/offerings.json`, `data/sellers.json`, `data/factories.json`, `data/research.json`, and media files only when separately verified.

**Interfaces:**
- Run command: `python3 scripts/scrape_reddit.py --registry data/research_sources.json --run-dir local-private/research-runs/overnight-2026-08-08 --max-pages 10 --max-posts 2000 --max-comments 100 --delay 1.5 --resume`
- Normalize only candidates with public provenance and explicit status; leave all other candidates in `needs_normalization`.

- [ ] **Step 1: Run a bounded smoke crawl against all four seeds**

Run: `python3 scripts/scrape_reddit.py --registry data/research_sources.json --run-dir local-private/research-runs/smoke-2026-08-08 --max-pages 1 --max-posts 25 --max-comments 20 --delay 1.5`

Expected: exit 0 or a recorded partial result with `run-summary.json`, at least one manifest entry per seed, and no public-data files modified.

- [ ] **Step 2: Inspect counts and sensitive-content scan**

Run: `python3 - <<'PY'
import json
from pathlib import Path
root = Path("local-private/research-runs/smoke-2026-08-08")
summary = json.loads((root / "run-summary.json").read_text())
print(summary["capture_count"], summary["candidate_count"], summary["errors"])
PY`

Expected: captures and candidates are nonnegative, errors are endpoint-scoped, and `rg -n "whatsapp|telegram|PayPal|routing number|account number|private message|password" local-private/research-runs/smoke-2026-08-08` finds no unredacted sensitive values in stored text.

- [ ] **Step 3: Run the bounded overnight crawl with resume enabled**

Run: `python3 scripts/scrape_reddit.py --registry data/research_sources.json --run-dir local-private/research-runs/overnight-2026-08-08 --max-pages 10 --max-posts 2000 --max-comments 100 --delay 1.5 --resume --overnight-hours 10`

Expected: the process continues through the configured window, records progress after each boundary, and can be interrupted/restarted without duplicating captures.

- [ ] **Step 4: Normalize selected leads in evidence-first batches**

For each selected candidate, verify the public post, exact bag variant, author independence, seller/factory attribution, promotional disclosure, positive/negative observations, and media provenance. Add new families only when their source trail meets the published-family gate; otherwise add a clearly labeled research-queue candidate. Keep contacts unchanged unless a future explicit privacy review authorizes a public wiki row.

- [ ] **Step 5: Rebuild summary/rankings and verify normalized data**

Run: `python3 scripts/build_summary.py`  
Run: `python3 scripts/score.py`  
Run: `python3 scripts/validate.py`  
Run: `python3 scripts/score.py --check`

Expected: summary counts reflect the new corpus, ranking output remains deterministic, and validation reports no broken references or sensitive-data violations.

- [ ] **Step 6: Commit reviewed public records only**

```bash
git add data README.md RESEARCH_SUMMARY.md media/evidence tests
git commit -m "feat: expand public Reddit evidence corpus"
```

### Task 6: Final verification and handoff

**Files:**
- Verify: all changed repository files
- Verify: `local-private/research-runs/<run-id>/run-summary.json` and `manifest.json`

- [ ] **Step 1: Run the complete required checks**

```bash
python3 scripts/validate.py
python3 scripts/score.py --check
python3 -m unittest discover -s tests -v
```

- [ ] **Step 2: Run a local HTTP smoke test**

Start: `python3 scripts/serve.py`  
Check: `curl -fsS http://127.0.0.1:8000/`  
Check: `curl -fsS http://127.0.0.1:8000/data/research.json`

Expected: the root page and research JSON return HTTP 200 and the Research view data includes the new lane/run metadata.

- [ ] **Step 3: Audit scope against the goal**

Confirm the final report states: RepCulture_Bags was scanned; all seeded rep communities were crawled; wiki/sidebar/search surfaces were checked; overnight artifacts are resumable; evidence counts increased or the run’s captured/normalized counts explain the boundary; new collections are either published with gates or labeled research queue; and no private/contact/payment/address/buyer-conversation material was published.

- [ ] **Step 4: Commit any final verification-only documentation change**

```bash
git status --short
git log --oneline -6
```

Expected: only intentional files are changed and the final handoff names the run directory and verification commands.

