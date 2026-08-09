# OG Rep Hub

OG Rep Hub is a public, bag-first research guide for rep-bag communities. It organizes family-level bag files, exact variants, seller/factory mentions, and the Reddit posts behind each note. The initial Neverfull campaign is preserved as historical source material while the community-first expansion grows across 12 launch families:

- Louis Vuitton Neverfull
- Chanel Classic Flap
- Louis Vuitton Speedy
- The Row Margaux
- Loewe Flamenco
- Loewe Puzzle
- Bottega Veneta Andiamo
- Goyard Saint Louis
- Hermès Birkin 25
- Miu Miu Arcadie
- Dior Lady Dior
- Dior Book Tote

The family layer is bag-first; seller offerings still point to exact variant records. All 12 launch families now have independent two-author source coverage and a qualifying user-posted image that is locally archived, attributed, hashed, dimension-checked, linked to normalized evidence, and checked for removal requests. Family tiles are never replaced with official-brand, seller-catalog, generated, or unrelated website imagery.

## Evidence model

Evidence records preserve source type, evidence type, author, subreddit, publication date, exact-variant match, seller/factory names as reported, positive observations, negative observations, and media provenance. Repeated posts by one author count as one corroborating source. Supported evidence types include in-hand review, PSP/QC, auth comparison, long-term wear, factory comparison, and seller context. The research page also logs the RepTherapy vocabulary source and a separate initial scan of r/RepLadiesWorld; scan leads are not normalized evidence until their bag, author, and limits are checked.

Seller reliability is fulfillment (30%), service/communication (25%), QC transparency (20%), shipping consistency (15%), and payment/risk signals (10%). Bag confidence is accuracy (35%), construction/materials (25%), exact-variant and availability proof (20%), independent corroboration (10%), and recency (10%). Numerical Community signal appears only in detail views when the existing evidence gates are satisfied. Price is displayed but never scored.

The guide does not turn community shorthand into a site verdict. It does not authenticate goods, guarantee outcomes, claim current stock from a listing, or label a seller/factory with a site-level trust, safety, exactness, or “best” conclusion.

## Local use

Python 3.13.7 is pinned in `.python-version`; the code uses the standard library only.

```sh
python3 scripts/validate.py
python3 scripts/score.py --check
python3 -m unittest discover -s tests -v
python3 scripts/serve.py
```

Then open `http://localhost:8000/`.

## Repository layout

- `data/bag_families.json`: family-level catalog, publication status, evidence coverage, and verified tile references
- `data/bags.json`: exact variants retained from the original campaign
- `data/`: normalized public JSON collections and generated rankings
- `scripts/`: validation, scoring, summary generation, and local server
- `tests/`: schema, score, provenance, safety-boundary, and site behavior tests
- `assets/`: dependency-free catalog UI
- `media/evidence/`: selected decision-critical media with Reddit provenance and SHA-256 hashes
- `.github/ISSUE_TEMPLATE/`: public issue forms for bag suggestions, Reddit sources, and corrections/media removal
- `local-private/`: gitignored space for any local notes that are not part of the public corpus

## Public-data and attribution

Only public URLs and public post context belong in the repository. Do not add private messages, payment details, addresses, passwords, or unverified contact information. Seller and factory names are displayed as reported, with the source link and unresolved limits kept visible. Public contact rows are limited to bag sellers already in the directory and link back to the r/RepTherapy public seller wiki; they are community-listed provenance, not a site endorsement or current-availability claim. Jewelry, glasses, accessory-only, and untracked names from that broader wiki are intentionally omitted. Media attribution includes the Reddit post URL, author, subreddit, capture date, hash, alt text, and a removal path through the correction/media issue form.

Availability is historical and time-sensitive. Check recent PSPs and reviews directly before making decisions. OG Rep Hub is not affiliated with any brand, seller, factory, subreddit, or Reddit, and it does not facilitate purchases.
