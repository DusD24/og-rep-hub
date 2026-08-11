# Prominent Submission Links Design

## Goal

Make the existing Cloudflare-backed contribution forms easier to discover while keeping each call to action relevant to the page where it appears.

## Scope

This change reuses the existing `suggest-bag`, `submit-source`, and `correction-media-removal` dialogs and Worker endpoints. It changes only where their launch buttons appear, their surrounding copy, and the styling and tests needed for those placements. Form fields, validation, privacy protections, Turnstile behavior, Worker behavior, and GitHub issue creation remain unchanged.

## Page placements

### Research page

Move the three-card contribution section to the top of the rendered research content, immediately below the Rep Research heading and scope note. Use a broad heading such as “Contribute to the research” rather than “Bring a receipt,” because the section includes bag suggestions and correction requests as well as sources.

The cards remain:

- Suggest a Bag
- Submit a Reddit Source
- Correction or Media Removal

Each card opens its existing branded in-site dialog.

### Catalog page

Add a submission callout after the bag collection grid. The callout asks “Don’t see your bag?” and launches the existing Suggest a Bag dialog. It should read as the natural end of browsing the Catalog and must not interrupt filtering or the bag grid.

### Individual bag pages

Add a final contribution section after the existing facts and research-notes content. The section uses a collection-specific heading such as “Help improve this bag’s research” and offers two actions:

- Submit a Reddit Source
- Correction or Media Removal

Suggest a Bag does not appear here because the visitor is already viewing an existing collection. The two buttons launch the existing forms without changing their payloads or pre-filling new collection context.

## Interaction and accessibility

All new launchers use real `button` elements with the existing contribution-dialog data attributes. They remain keyboard accessible and inherit the current dialog focus management, Turnstile handling, submission feedback, and success state.

Headings and section relationships use accessible heading structure. Button copy stays explicit about the resulting action. Existing public-data and privacy language remains visible inside each form.

## Visual treatment

Reuse the existing contribution-card visual language so the new actions feel native to the site. The Research page retains a three-card layout on wide screens. The Catalog uses a compact panel with one emphasized Suggest a Bag action, while the bag-detail section uses two balanced actions. All placements collapse to one column at the existing mobile breakpoint.

No floating button or permanent primary-navigation item is added; contribution prominence remains contextual rather than sitewide and persistent.

## Verification

Automated tests will confirm:

- the Research contribution section renders before campaigns, lanes, glossary, and queue content;
- the Catalog ends with a Suggest a Bag launcher;
- each bag-detail page ends with Submit a Reddit Source and Correction or Media Removal launchers, but not Suggest a Bag;
- all launchers route through the existing contribution-dialog configuration and Cloudflare-backed endpoints;
- responsive styling covers the new layouts; and
- the existing site, Worker, validation, and deployment test suites still pass.
