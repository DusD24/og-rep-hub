# OG Rep Hub

OG Rep Hub is a public, evidence-linked research catalog for two Neverfull-style targets:

- primary: brown Monogram GM;
- secondary: Eden/floral MM colorways, with brown prioritized.

The site keeps bag, size, colorway, seller, factory/batch, listing status, and evidence separate. It records publicly advertised business contacts and public sources only. It does not contain private conversations, payment details, addresses, or purchase facilitation.

## Confidence model

Seller reliability is fulfillment (30%), service/communication (25%), QC transparency (20%), shipping consistency (15%), and payment/risk signals (10%). Bag confidence is accuracy (35%), construction/materials (25%), exact-variant and availability proof (20%), independent corroboration (10%), and recency (10%). Recommendation score is 65% bag confidence plus 35% seller reliability. Price is displayed but never scored.

Catalog pages only prove that an item was listed; they do not prove quality or live inventory. Repeated posts by one author count as one corroborating source. Tier A requires a score of at least 80, direct exact-variant evidence, two independent Reddit authors, and no unresolved major negative. Evidence-poor or catalog-only offerings remain visible but unranked.

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

- `data/`: normalized public JSON collections and generated rankings
- `scripts/`: validation, scoring, summary generation, and local server
- `tests/`: schema, score, safety, and site behavior tests
- `assets/`: dependency-free catalog UI
- `media/evidence/`: only selected, attributed decision-critical media (Git LFS)
- `local-private/`: gitignored space for any outreach replies or sensitive notes

## Availability and safety

Listing status is historical and time-sensitive. Contact a seller independently to confirm current availability; OG Rep Hub does not endorse sellers, authenticate goods, arrange purchases, or guarantee outcomes. Every public contact must include a public provenance URL and verification date. Please open an issue to correct a source, remove media, or report a safety concern.

