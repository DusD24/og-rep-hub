const files = ["bag_families", "bags", "sellers", "factories", "offerings", "evidence", "contacts", "media", "outreach", "rankings", "research"];
const state = Object.create(null);
const primaryViews = ["bags", "sellers", "evidence", "research"];
const welcomeEvidenceIds = [
  "ev-hp-mm-durability",
  "ev-rll-chanel-classic-flap-187",
  "ev-rll-margaux-17",
  "ev-rt-flamenco-deerskin",
  "ev-rll-andiamos-medium",
  "ev-rll-lady-dior-auth"
];
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
const welcomeExitDuration = 1280;
let activeEvidenceContext = null;
let dialogOpener = null;
let dialogScrollPosition = 0;
let welcomeExitTimer = null;
let welcomeExitActive = false;
let ready = false;

const STATUS_LABELS = {
  seller_confirmed: "Seller reported",
  catalog_seen: "Catalog mention",
  historically_ordered: "Bought & reviewed",
  inferred: "Source inference",
  unavailable: "Unavailable in source",
  unknown: "Still researching",
  research_queue: "Research queue",
  published: "Published with receipts"
};
const EVIDENCE_LABELS = {
  auth_comparison: "Auth comparison",
  factory_comparison: "Factory comparison",
  in_hand_review: "In-hand review",
  long_term_wear: "Long-term wear",
  psp_qc: "PSP / QC",
  seller_context: "Seller context"
};

const escapeHtml = (value = "") => String(value).replace(/[&<>'"]/g, character => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
}[character]));
const byId = rows => new Map((rows || []).map(row => [row.id, row]));
const label = value => String(value || "unknown").replaceAll("_", " ");
const statusLabel = value => STATUS_LABELS[value] || label(value);
const evidenceLabel = value => EVIDENCE_LABELS[value] || label(value);
const sourceLabel = value => label(value).replace(/^reddit /, "Reddit ");
const httpsUrl = value => /^https:\/\//.test(value || "") ? value : "#";
const unique = values => [...new Set((values || []).filter(Boolean))];
const cleanList = values => unique((values || []).map(value => String(value).trim()).filter(Boolean));
const plural = (count, singular, pluralForm = `${singular}s`) => `${count} ${count === 1 ? singular : pluralForm}`;
const placeholderValue = value => /^(unknown|none|n\/a|not documented|not stated|not consistently stated|unavailable|still researching)/i.test(String(value || "").trim());
const meaningfulValues = values => cleanList(values).filter(value => !placeholderValue(value));

function resetWelcomeExit() {
  if (welcomeExitTimer !== null) window.clearTimeout(welcomeExitTimer);
  welcomeExitTimer = null;
  welcomeExitActive = false;
  document.body.classList.remove("welcome-transitioning");
  document.querySelector("#welcome")?.classList.remove("welcome-exiting");
  const cta = document.querySelector("[data-enter-site]");
  if (cta) cta.disabled = false;
  document.querySelectorAll(".app-shell").forEach(shell => { shell.inert = false; });
}

function setDisplayMode(mode) {
  resetWelcomeExit();
  document.body.classList.toggle("welcome-mode", mode === "welcome");
  document.body.classList.toggle("app-mode", mode === "app");
}

setDisplayMode(location.hash ? "app" : "welcome");

async function loadData() {
  const results = await Promise.all(files.map(async name => {
    const response = await fetch(`data/${name}.json`);
    if (!response.ok) throw new Error(`${name}: ${response.status}`);
    return [name, await response.json()];
  }));
  results.forEach(([name, value]) => { state[name] = value; });
  state.maps = {
    families: byId(state.bag_families),
    bags: byId(state.bags),
    sellers: byId(state.sellers),
    factories: byId(state.factories),
    evidence: byId(state.evidence),
    contacts: byId(state.contacts),
    media: byId(state.media),
    rankings: byId((state.rankings?.rankings || []).map(row => ({ id: row.offering_id, ...row })))
  };
}

function fillSelect(selector, values) {
  const select = document.querySelector(selector);
  if (!select) return;
  const first = select.firstElementChild;
  select.replaceChildren(first);
  unique(values).sort((a, b) => String(a).localeCompare(String(b))).forEach(value => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label(value);
    select.append(option);
  });
}

function familyVariants(family) {
  const ids = unique([
    ...(family.documented_variant_ids || []),
    ...(state.bags || []).filter(item => item.family_id === family.id).map(item => item.id)
  ]);
  return ids.map(id => state.maps.bags.get(id)).filter(Boolean);
}

function familyEvidence(family) {
  const variantIds = new Set(familyVariants(family).map(item => item.id));
  return state.evidence.filter(item => (item.family_ids || []).includes(family.id) || (item.bag_ids || []).some(id => variantIds.has(id)));
}

function familyOfferings(family) {
  const variantIds = new Set(familyVariants(family).map(item => item.id));
  return state.offerings.filter(item => item.family_id === family.id || variantIds.has(item.variant_id || item.bag_id));
}

function familyCoverage(family) {
  const evidence = familyEvidence(family);
  const authors = unique(evidence.map(item => item.author).filter(Boolean).map(author => author.toLowerCase()));
  return {
    sourceCount: evidence.length || family.evidence_coverage?.source_count || 0,
    authorCount: authors.length || family.evidence_coverage?.independent_author_count || 0,
    subreddits: unique(evidence.map(item => item.subreddit)),
    evidenceTypes: unique(evidence.map(item => item.evidence_type)),
    imageReady: Boolean(family.tile_media_id && state.maps.media.has(family.tile_media_id))
  };
}

function renderWelcomeVoices() {
  const selected = welcomeEvidenceIds.map(id => state.maps.evidence.get(id)).filter(Boolean);
  const rows = (selected.length === welcomeEvidenceIds.length ? selected : [...state.evidence]
    .sort((a, b) => String(a.id).localeCompare(String(b.id))).slice(0, 6));
  const positions = [
    [-34, -18, -19, -20],
    [31, -27, 19, -26],
    [-25, 18, -20, 13],
    [27, 14, 20, 17],
    [-7, -32, -4, -35],
    [4, 27, 5, 31]
  ];
  document.querySelector("#welcome-voices").innerHTML = rows.map((item, index) => {
    const [x, y, mobileX, mobileY] = positions[index] || [0, 0, 0, 0];
    const lineY = 9 + (index * 14.5);
    return `<figure class="welcome-voice" style="--voice-index:${index};--voice-x:${x}vw;--voice-y:${y}vh;--voice-mobile-x:${mobileX}vw;--voice-mobile-y:${mobileY}vh;--voice-line-y:${lineY}vh;--voice-exit-delay:${index * .025}s"><p>${escapeHtml(item.paraphrase)}</p><figcaption>${item.author ? `u/${escapeHtml(item.author)} · ` : ""}${item.subreddit ? `r/${escapeHtml(item.subreddit)}` : escapeHtml(sourceLabel(item.source_type))}</figcaption></figure>`;
  }).join("");
}

function restartWelcomeAnimation() {
  resetWelcomeExit();
  const welcome = document.querySelector("#welcome");
  welcome.classList.remove("welcome-ready");
  void welcome.offsetWidth;
  welcome.classList.add("welcome-ready");
}

function enterCatalogFromWelcome() {
  if (!ready || welcomeExitActive) return;
  if (reducedMotion.matches) {
    navigate("bags");
    return;
  }
  const welcome = document.querySelector("#welcome");
  const cta = document.querySelector("[data-enter-site]");
  welcomeExitActive = true;
  activateView("bags");
  window.scrollTo({ top: 0, behavior: "auto" });
  document.querySelectorAll(".app-shell").forEach(shell => { shell.inert = true; });
  document.body.classList.add("welcome-transitioning");
  welcome.classList.add("welcome-exiting");
  if (cta) cta.disabled = true;
  welcomeExitTimer = window.setTimeout(() => {
    welcomeExitTimer = null;
    navigate("bags");
  }, welcomeExitDuration);
}

function renderSnapshot() {
  const published = state.bag_families.filter(item => item.publication_status === "published").length;
  const mediaReady = state.bag_families.filter(item => familyCoverage(item).imageReady).length;
  const stats = [
    [state.bag_families.length, "bag families"],
    [published, "published files"],
    [state.evidence.length, "reviews & receipts"],
    [mediaReady, "Reddit photos"]
  ];
  document.querySelector("#snapshot").innerHTML = stats.map(([value, name]) => `<div class="stat"><strong>${value}</strong><span>${escapeHtml(name)}</span></div>`).join("");
}

function familySearchText(family) {
  const variants = familyVariants(family);
  const evidence = familyEvidence(family);
  const reportedNames = evidence.flatMap(item => [
    ...(item.seller_ids || []).map(id => state.maps.sellers.get(id)?.display_name),
    ...(item.factory_ids || []).map(id => state.maps.factories.get(id)?.display_name)
  ]);
  return [
    family.brand, family.model, ...(family.aliases || []), family.category, family.summary,
    ...(family.documented_sizes || []), ...(family.documented_materials || []), ...(family.documented_hardware || []),
    ...variants.flatMap(item => [item.name, item.size, item.pattern, item.colorway, item.material, item.hardware]),
    ...evidence.flatMap(item => [item.author, item.subreddit, item.paraphrase, ...(item.positive_observations || []), ...(item.negative_observations || [])]),
    ...reportedNames
  ].filter(Boolean).join(" ").toLowerCase();
}

function familyMatches(family) {
  const query = document.querySelector("#bag-search").value.trim().toLowerCase();
  const brand = document.querySelector("#brand-filter").value;
  const type = document.querySelector("#type-filter").value;
  const size = document.querySelector("#size-filter").value;
  const material = document.querySelector("#material-filter").value;
  const evidenceType = document.querySelector("#evidence-type-filter").value;
  const variants = familyVariants(family);
  const evidence = familyEvidence(family);
  const sizes = unique([...(family.documented_sizes || []), ...variants.map(item => item.size)]);
  const materials = unique([...(family.documented_materials || []), ...variants.map(item => item.material)]);
  return (!query || familySearchText(family).includes(query))
    && (!brand || family.brand === brand)
    && (!type || family.category === type)
    && (!size || sizes.includes(size))
    && (!material || materials.includes(material))
    && (!evidenceType || evidence.some(item => item.evidence_type === evidenceType));
}

function familyBadges(family) {
  const coverage = familyCoverage(family);
  const badges = [];
  if (coverage.evidenceTypes.includes("in_hand_review")) badges.push("In-hand review");
  if (coverage.evidenceTypes.includes("auth_comparison")) badges.push("Auth comparison");
  if (coverage.evidenceTypes.includes("long_term_wear")) badges.push("Long-term wear");
  if (coverage.evidenceTypes.includes("psp_qc")) badges.push("PSP / QC");
  if (!coverage.imageReady || coverage.authorCount < 2 || coverage.sourceCount < 2) badges.push("Needs more receipts");
  return unique(badges);
}

function mediaImage(media, className = "") {
  if (!media?.path) return "";
  return `<img class="${escapeHtml(className)}" src="${escapeHtml(media.path)}" alt="${escapeHtml(media.alt || media.research_purpose || "Community evidence image")}" loading="lazy" onerror="this.hidden=true;this.parentElement.classList.add('media-unavailable')">`;
}

function renderFamilyTile(family, detail = false) {
  const media = state.maps.media.get(family.tile_media_id);
  if (!media) return `<div class="family-tile family-tile-empty" role="img" aria-label="No representative Reddit image is archived for ${escapeHtml(family.brand)} ${escapeHtml(family.model)}"><span class="tile-kicker">Media unavailable</span><strong>Reddit photo pending</strong><span>The family file remains transparent while a sourced image is archived.</span></div>`;
  return `<a class="bag-tile${detail ? " detail-tile" : ""}" href="${escapeHtml(httpsUrl(media.post_url || media.source_url))}" target="_blank" rel="noopener noreferrer" aria-label="Open Reddit source for ${escapeHtml(family.brand)} ${escapeHtml(family.model)} image">${mediaImage(media)}<span class="bag-tile-source">Reddit photo · ${escapeHtml(media.attribution || "source author")} <span aria-hidden="true">↗</span></span></a>`;
}

function renderFamilyCard(family) {
  const coverage = familyCoverage(family);
  const badges = familyBadges(family);
  return `<article class="card family-card" data-family-id="${escapeHtml(family.id)}">
    ${renderFamilyTile(family)}
    <div class="card-body"><div class="tags"><span class="tag">${escapeHtml(family.brand)}</span><span class="tag">${escapeHtml(label(family.category))}</span></div>
    <h3><a href="#bag/${encodeURIComponent(family.id)}" data-route>${escapeHtml(family.model)}</a></h3>
    <p class="family-summary clamped-text">${escapeHtml(family.summary)}</p>
    <div class="badge-row">${badges.map(badge => `<span class="badge">${escapeHtml(badge)}</span>`).join("")}</div>
    <p class="metadata">${plural(coverage.sourceCount, "receipt")} · ${plural(coverage.authorCount, "author")} · ${escapeHtml(statusLabel(family.publication_status))}</p>
    <a class="card-action" href="#bag/${encodeURIComponent(family.id)}" data-route>Open family file <span aria-hidden="true">→</span></a></div>
  </article>`;
}

function renderBags() {
  const rows = state.bag_families.filter(familyMatches);
  const sort = document.querySelector("#bag-sort").value;
  rows.sort((a, b) => {
    const coverageA = familyCoverage(a);
    const coverageB = familyCoverage(b);
    if (sort === "recently_updated") return String(b.last_updated).localeCompare(String(a.last_updated)) || a.model.localeCompare(b.model);
    if (sort === "az") return `${a.brand} ${a.model}`.localeCompare(`${b.brand} ${b.model}`);
    return coverageB.sourceCount - coverageA.sourceCount || coverageB.authorCount - coverageA.authorCount || a.model.localeCompare(b.model);
  });
  document.querySelector("#bag-results").innerHTML = rows.length ? rows.map(renderFamilyCard).join("") : '<p class="empty">No bag families match these filters. Try clearing one filter.</p>';
}

function renderSellers() {
  document.querySelector("#seller-results").innerHTML = state.sellers.length ? state.sellers.map(seller => {
    const contacts = state.contacts.filter(item => item.seller_id === seller.id);
    const offers = state.offerings.filter(item => item.seller_id === seller.id);
    const evidenceCount = state.evidence.filter(item => (item.seller_ids || []).includes(seller.id)).length;
    const hasMore = Boolean(seller.confidence_note || contacts.length || offers.length || evidenceCount);
    return `<article class="compact-card directory-card"><div class="tags"><span class="tag">Seller</span>${seller.community_contact_status === "community_listed" ? '<span class="tag accent-tag">Community-listed</span>' : ""}</div><h3>${escapeHtml(seller.display_name)}</h3><p class="metadata">${plural(evidenceCount, "receipt")} · checked ${escapeHtml(seller.last_verified || "date unavailable")}</p><p class="clamped-text">${escapeHtml(seller.confidence_note || "Names remain tied to linked public evidence.")}</p><div class="card-spacer"></div>${hasMore ? `<button class="card-action dialog-trigger" type="button" data-dialog-kind="seller" data-dialog-id="${escapeHtml(seller.id)}">Read more</button>` : ""}</article>`;
  }).join("") : '<p class="empty">No named seller has cleared the public-source checks yet.</p>';

  document.querySelector("#factory-results").innerHTML = state.factories.length ? state.factories.map(factory => {
    const evidence = state.evidence.filter(item => (item.factory_ids || []).includes(factory.id));
    return `<article class="compact-card directory-card"><div class="tags"><span class="tag">Factory / batch</span></div><h3>${escapeHtml(factory.display_name)}</h3><p class="metadata">${plural(evidence.length, "receipt")} · as reported</p><p class="clamped-text">${escapeHtml(factory.notes || "No broader consistency claim is made.")}</p><div class="card-spacer"></div>${factory.notes || evidence.length ? `<button class="card-action dialog-trigger" type="button" data-dialog-kind="factory" data-dialog-id="${escapeHtml(factory.id)}">Read more</button>` : ""}</article>`;
  }).join("") : '<p class="empty">No factory names are currently documented.</p>';
}

function renderMedia(item) {
  const rows = (item.media_ids || []).map(id => state.maps.media.get(id)).filter(Boolean);
  if (!rows.length) return '<p class="media-fallback">No selected media archived. Use the public source for original context.</p>';
  return `<div class="evidence-media">${rows.map(media => `<figure>${mediaImage(media)}<figcaption>${escapeHtml(media.attribution || "Source author")}${media.capture_date ? ` · ${escapeHtml(media.capture_date)}` : ""}</figcaption></figure>`).join("")}</div>`;
}

function list(items = [], className = "") {
  const rows = cleanList(items);
  return rows.length ? `<ul class="${escapeHtml(className)}">${rows.map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : '<span class="fineprint">None recorded.</span>';
}

function evidenceFamilyId(item) {
  if (item.family_ids?.length) return item.family_ids[0];
  return state.bag_families.find(family => (item.bag_ids || []).some(id => familyVariants(family).some(variant => variant.id === id)))?.id;
}

function receiptHasMore(item) {
  return Boolean((item.positive_observations || []).length || (item.negative_observations || []).length || (item.media_ids || []).length || item.url);
}

function renderReceiptCard(item) {
  return `<article class="compact-card receipt-card" data-evidence-id="${escapeHtml(item.id)}"><div class="source-line"><span class="tag">${escapeHtml(evidenceLabel(item.evidence_type))}</span><span class="tag">${item.exact_product_match ? "Exact" : "Related"}</span></div><h3>${escapeHtml(item.title || item.paraphrase.slice(0, 65))}</h3><p class="clamped-text">${escapeHtml(item.paraphrase)}</p><p class="metadata">${escapeHtml(item.publication_date || "Date unavailable")}${item.author ? ` · u/${escapeHtml(item.author)}` : ""}${item.subreddit ? ` · r/${escapeHtml(item.subreddit)}` : ""}</p><div class="card-spacer"></div>${receiptHasMore(item) ? `<button class="card-action dialog-trigger" type="button" data-dialog-kind="evidence" data-dialog-id="${escapeHtml(item.id)}">Read full receipt</button>` : `<a class="card-action" href="${escapeHtml(httpsUrl(item.url))}" target="_blank" rel="noopener noreferrer">Open public source <span aria-hidden="true">↗</span></a>`}</article>`;
}

function evidenceContextRows() {
  if (!activeEvidenceContext) return state.evidence;
  if (activeEvidenceContext.kind === "family") {
    const family = state.maps.families.get(activeEvidenceContext.id);
    return family ? familyEvidence(family) : [];
  }
  return state.evidence.filter(item => (item.bag_ids || []).includes(activeEvidenceContext.id));
}

function evidenceContextLabel() {
  if (!activeEvidenceContext) return "";
  if (activeEvidenceContext.kind === "family") {
    const family = state.maps.families.get(activeEvidenceContext.id);
    return family ? `${family.brand} ${family.model}` : "Unknown family";
  }
  return state.maps.bags.get(activeEvidenceContext.id)?.name || "Unknown variant";
}

function renderEvidence() {
  const query = document.querySelector("#evidence-search").value.trim().toLowerCase();
  const source = document.querySelector("#source-filter").value;
  const evidenceType = document.querySelector("#evidence-type-detail-filter").value;
  const match = document.querySelector("#match-filter").value;
  const rows = evidenceContextRows().filter(item => {
    const haystack = [item.id, item.author, item.subreddit, item.title, item.paraphrase, item.evidence_type, ...(item.positive_observations || []), ...(item.negative_observations || [])].join(" ").toLowerCase();
    return (!query || haystack.includes(query)) && (!source || item.source_type === source) && (!evidenceType || item.evidence_type === evidenceType) && (!match || String(item.exact_product_match) === match);
  }).sort((a, b) => String(b.publication_date).localeCompare(String(a.publication_date)) || String(a.id).localeCompare(String(b.id)));
  const chip = document.querySelector("#evidence-context");
  chip.hidden = !activeEvidenceContext;
  chip.innerHTML = activeEvidenceContext ? `<span><strong>${rows.length}</strong> ${rows.length === 1 ? "receipt" : "receipts"} for ${escapeHtml(evidenceContextLabel())}</span><button type="button" data-clear-evidence>Clear <span class="visually-hidden">receipt context</span></button>` : "";
  document.querySelector("#evidence-results").innerHTML = rows.length ? rows.map(renderReceiptCard).join("") : '<p class="empty">No reviews or receipts match these filters.</p>';
}

function variantMedia(variant) {
  const direct = state.maps.media.get(variant.tile_media_id);
  if (direct) return direct;
  const evidence = state.evidence.find(item => (item.bag_ids || []).includes(variant.id) && (item.media_ids || []).some(id => state.maps.media.has(id)));
  return evidence ? state.maps.media.get(evidence.media_ids.find(id => state.maps.media.has(id))) : null;
}

function renderVariantCards(family) {
  const variants = familyVariants(family);
  if (!variants.length) return '<p class="empty compact-empty">No source-documented exact variants yet.</p>';
  return `<div class="variant-grid">${variants.map(variant => {
    const evidenceCount = state.evidence.filter(item => (item.bag_ids || []).includes(variant.id)).length;
    const media = variantMedia(variant);
    return `<article class="variant-card">${media ? `<div class="variant-thumb">${mediaImage(media)}</div>` : '<div class="variant-thumb variant-thumb-empty" aria-hidden="true"><span>Photo pending</span></div>'}<div class="variant-card-copy"><p class="eyebrow">Exact variant</p><h3>${escapeHtml(variant.name)}</h3><dl><div><dt>Size</dt><dd>${escapeHtml(variant.size || "Unresolved")}</dd></div><div><dt>Pattern</dt><dd>${escapeHtml(variant.pattern || "Unresolved")}</dd></div><div><dt>Colorway</dt><dd>${escapeHtml(variant.colorway || "Unresolved")}</dd></div></dl>${evidenceCount ? `<a class="receipt-count" href="#evidence?variant=${encodeURIComponent(variant.id)}" data-route>${plural(evidenceCount, "receipt")} <span aria-hidden="true">→</span></a>` : '<span class="receipt-count zero">0 receipts</span>'}</div></article>`;
  }).join("")}</div>`;
}

function reportedPartyNames(family, type) {
  const map = type === "seller" ? state.maps.sellers : state.maps.factories;
  const key = type === "seller" ? "seller_ids" : "factory_ids";
  return unique(familyEvidence(family).flatMap(item => item[key] || []).map(id => map.get(id)?.display_name)).filter(name => name && !placeholderValue(name));
}

function factBlock(title, values) {
  const rows = meaningfulValues(values);
  return rows.length ? `<div><dt>${escapeHtml(title)}</dt><dd>${rows.map(escapeHtml).join(" · ")}</dd></div>` : "";
}

function renderBagDetail(familyId) {
  const family = state.maps.families.get(familyId);
  const container = document.querySelector("#bag-detail-content");
  if (!family) {
    container.innerHTML = '<p class="empty">That bag family could not be found. <a href="#bags" data-route>Return to Bags</a>.</p>';
    return;
  }
  const coverage = familyCoverage(family);
  const evidence = familyEvidence(family).sort((a, b) => String(b.publication_date).localeCompare(String(a.publication_date)) || String(a.id).localeCompare(String(b.id)));
  const newest = evidence.slice(0, 6);
  const variants = familyVariants(family);
  const qcNotes = cleanList([...evidence.flatMap(item => item.negative_observations || []), ...(family.research_gaps || [])]);
  const hasCommunitySignal = familyOfferings(family).some(offering => {
    const ranking = state.maps.rankings.get(offering.id);
    return ranking?.rank_status === "ranked" && ranking.recommendation_score != null;
  });
  const facts = [
    factBlock("Sizes", family.documented_sizes?.length ? family.documented_sizes : variants.map(item => item.size)),
    factBlock("Materials", family.documented_materials?.length ? family.documented_materials : variants.map(item => item.material)),
    factBlock("Hardware", family.documented_hardware?.length ? family.documented_hardware : variants.map(item => item.hardware)),
    factBlock("Sellers as reported", reportedPartyNames(family, "seller")),
    factBlock("Factories / batches as reported", reportedPartyNames(family, "factory")),
    factBlock("Subreddits", coverage.subreddits.map(value => `r/${value}`))
  ].join("");
  container.innerHTML = `<a class="back-link" href="#bags" data-route>← Back to Bags</a>
    <div class="family-hero"><div>${renderFamilyTile(family, true)}</div><div><p class="eyebrow">${escapeHtml(family.brand)} · ${escapeHtml(label(family.category))}</p><h1 id="bag-detail-title" tabindex="-1">${escapeHtml(family.model)}</h1><p class="detail-summary">${escapeHtml(family.summary)}</p><div class="badge-row">${familyBadges(family).map(badge => `<span class="badge">${escapeHtml(badge)}</span>`).join("")}</div><p class="metadata">Updated ${escapeHtml(family.last_updated)} · ${plural(coverage.sourceCount, "receipt")} · ${plural(coverage.authorCount, "independent author")}</p></div></div>
    <section class="family-section family-receipts" aria-labelledby="family-receipts-title"><div class="subsection-heading"><div><p class="eyebrow">Newest source trail</p><h2 id="family-receipts-title">Reviews &amp; receipts</h2></div><a class="card-action" href="#evidence?family=${encodeURIComponent(family.id)}" data-route><span class="visually-hidden">See reviews &amp; receipts: </span>View all ${evidence.length} receipts <span aria-hidden="true">→</span></a></div>${newest.length ? `<div class="receipt-grid">${newest.map(renderReceiptCard).join("")}</div>` : '<p class="empty">No family-linked public sources yet.</p>'}</section>
    <section class="family-section variants-section" aria-labelledby="variants-title"><div class="subsection-heading"><div><p class="eyebrow">Source-documented identities</p><h2 id="variants-title">Exact Variants</h2></div><p>${plural(variants.length, "variant")}</p></div>${renderVariantCards(family)}</section>
    <div class="support-grid"><section class="support-card"><p class="eyebrow">Useful family facts</p><h2>At a glance</h2>${facts ? `<dl class="at-a-glance">${facts}</dl>` : '<p class="fineprint">No non-placeholder family facts are available yet.</p>'}</section><section class="support-card"><p class="eyebrow">QC &amp; open questions</p><h2>Research notes</h2>${qcNotes.length ? list(qcNotes.slice(0, 3), "research-note-preview") : '<p class="fineprint">No research gaps are recorded.</p>'}${qcNotes.length > 3 ? `<button class="card-action dialog-trigger" type="button" data-dialog-kind="notes" data-dialog-id="${escapeHtml(family.id)}">Read all ${qcNotes.length}</button>` : ""}<p class="signal-status"><strong>${hasCommunitySignal ? "Community signal available in the underlying research." : "Community signal unavailable."}</strong> ${hasCommunitySignal ? "Open the linked receipts to review the qualifying evidence." : "Current evidence does not meet the detail-level scoring gates."}</p></section></div>`;
}

function renderResearch() {
  const campaigns = state.research.campaigns || [];
  const lanes = state.research.research_lanes || [];
  const queue = state.outreach.queue || [];
  const glossary = state.research.glossary || [];
  const scanLogs = state.research.scan_log || [];
  const leads = scanLogs.flatMap(scan => (scan.candidate_sources || []).map(item => ({ ...item, scan_id: scan.id, checked_at: scan.checked_at, source_url: scan.source_url })));
  const forms = [
    ["Suggest a Bag", "Add a family candidate with public source URLs and no private contact details.", "suggest-a-bag.yml"],
    ["Submit a Reddit Source", "Add a review, PSP/QC post, auth comparison, or in-hand receipt with provenance.", "submit-reddit-source.yml"],
    ["Correction or Media Removal", "Flag a source, attribution, image, or research note for review.", "correction-or-media-removal.yml"]
  ];
  const campaignMarkup = campaigns.map(item => `<article class="compact-card research-card"><p class="eyebrow">${escapeHtml(label(item.status))}</p><h3>${escapeHtml(item.name)}</h3><p class="clamped-text">${escapeHtml(item.scope)}</p><div class="card-spacer"></div><button class="card-action dialog-trigger" type="button" data-dialog-kind="campaign" data-dialog-id="${escapeHtml(item.id)}">Read more</button></article>`).join("");
  const laneMarkup = lanes.map(item => `<article class="compact-card research-card"><p class="eyebrow">Independent lane</p><h3>r/${escapeHtml(item.subreddit_focus)}</h3><p class="metadata">${escapeHtml(label(item.status))} · ${plural(item.families_checked || 0, "family", "families")} checked</p><p class="clamped-text">${escapeHtml(item.scope)}</p><div class="card-spacer"></div><button class="card-action dialog-trigger" type="button" data-dialog-kind="lane" data-dialog-id="${escapeHtml(item.id)}">Read more</button></article>`).join("");
  const leadMarkup = leads.map(item => `<article class="compact-card research-card"><p class="eyebrow">${escapeHtml(evidenceLabel(item.evidence_type))}</p><h3>${escapeHtml(item.title)}</h3><p class="clamped-text">${escapeHtml(item.note)}</p><div class="card-spacer"></div><button class="card-action dialog-trigger" type="button" data-dialog-kind="scan" data-dialog-id="${escapeHtml(item.url)}">Read more</button></article>`).join("");
  const glossarySource = state.research.glossary_source_url ? `<p class="scope-note">Adapted from the <a href="${escapeHtml(httpsUrl(state.research.glossary_source_url))}" target="_blank" rel="noopener noreferrer">r/RepTherapy glossary <span aria-hidden="true">↗</span></a>.</p>` : "";
  document.querySelector("#research-results").innerHTML = `<section class="research-section"><div class="subsection-heading"><div><p class="eyebrow">Dated campaigns</p><h2>How this corpus grew</h2></div></div><div class="auto-grid">${campaignMarkup}</div></section>
    <section class="research-section"><div class="subsection-heading"><div><p class="eyebrow">Independent scans</p><h2>Research lanes</h2></div></div><div class="auto-grid">${laneMarkup}</div></section>
    ${leads.length ? `<section class="research-section"><div class="subsection-heading"><div><p class="eyebrow">Latest scan</p><h2>r/RepLadiesWorld leads</h2></div><p>Leads stay separate until normalized.</p></div><div class="auto-grid">${leadMarkup}</div></section>` : ""}
    <section class="research-section glossary-section"><div class="subsection-heading"><div><p class="eyebrow">First-use notes</p><h2>Rep vocabulary</h2></div>${glossarySource}</div><dl class="glossary-grid">${glossary.map(item => `<div><dt>${escapeHtml(item.term)}</dt><dd>${escapeHtml(item.definition)}</dd></div>`).join("")}</dl></section>
    <section class="research-section queue-section"><div class="subsection-heading"><div><p class="eyebrow">Contribution queue</p><h2>Help Fill the Gaps</h2></div><p>Every submission needs a public URL and no private details.</p></div>${queue.length ? `<div class="queue-table-wrap"><table class="queue-table"><thead><tr><th>Priority</th><th>Family</th><th>Exact ask</th><th>Status</th></tr></thead><tbody>${queue.map(item => { const bag = state.maps.bags.get(item.bag_id); const family = bag ? state.maps.families.get(bag.family_id) : null; return `<tr><td>${escapeHtml(item.priority)}</td><td>${escapeHtml(family?.model || "Family gap")}</td><td>${escapeHtml(item.question)}</td><td>${escapeHtml(label(item.status))}</td></tr>`; }).join("")}</tbody></table></div>` : '<p class="empty">No open research questions are queued.</p>'}</section>
    <section class="research-section contribution-section"><p class="eyebrow">Public contribution paths</p><h2>Bring a receipt</h2><div class="contribution-grid">${forms.map(([title, description, template]) => `<a class="contribution-card" href="https://github.com/DusD24/og-rep-hub/issues/new?template=${encodeURIComponent(template)}" target="_blank" rel="noopener noreferrer"><strong>${escapeHtml(title)} <span aria-hidden="true">↗</span></strong><span>${escapeHtml(description)}</span></a>`).join("")}</div></section>`;
}

function sellerDialog(seller) {
  const contacts = state.contacts.filter(item => item.seller_id === seller.id);
  const offers = state.offerings.filter(item => item.seller_id === seller.id);
  const evidence = state.evidence.filter(item => (item.seller_ids || []).includes(seller.id));
  const contactMarkup = contacts.length ? `<div class="dialog-section"><h3>Community-listed contacts</h3>${contacts.map(contact => `<p><a class="contact-link" href="${escapeHtml(httpsUrl(contact.link_url || contact.public_source_url))}" target="_blank" rel="noopener noreferrer">${escapeHtml(sourceLabel(contact.channel))}: ${escapeHtml(contact.value)} <span aria-hidden="true">↗</span></a><br><a class="contact-source" href="${escapeHtml(httpsUrl(contact.public_source_url))}" target="_blank" rel="noopener noreferrer">${escapeHtml(contact.source_label || "Public contact source")} <span aria-hidden="true">↗</span></a></p>`).join("")}<p class="fineprint">Community-listed; verify the public source before use.</p></div>` : '<p class="media-fallback">No public contact channel is verified. Community-listed status is not current availability.</p>';
  const offeringMarkup = offers.length ? `<div class="dialog-section"><h3>Exact-variant offerings as reported</h3>${list(offers.map(offering => `${state.maps.bags.get(offering.variant_id || offering.bag_id)?.name || "Variant not named"} · ${statusLabel(offering.status)}`))}</div>` : "";
  return { kicker: "Seller as reported", title: seller.display_name, body: `<p>${escapeHtml(seller.confidence_note || "Names remain tied to the linked public evidence.")}</p><p class="metadata">${plural(evidence.length, "receipt")} · checked ${escapeHtml(seller.last_verified || "date unavailable")}</p>${contactMarkup}${offeringMarkup}` };
}

function factoryDialog(factory) {
  const evidence = state.evidence.filter(item => (item.factory_ids || []).includes(factory.id));
  const variants = unique(evidence.flatMap(item => (item.bag_ids || []).map(id => state.maps.bags.get(id)?.name)));
  return { kicker: "Factory / batch as reported", title: factory.display_name, body: `<p>${escapeHtml(factory.notes || "No broader consistency claim is made.")}</p>${variants.length ? `<div class="dialog-section"><h3>Reported on</h3>${list(variants)}</div>` : ""}${evidence.length ? `<div class="dialog-section"><h3>Linked receipts</h3>${list(evidence.map(item => item.title || item.paraphrase))}</div>` : '<p class="media-fallback">No exact bag variant is named.</p>'}` };
}

function evidenceDialog(item) {
  const familyId = evidenceFamilyId(item);
  return { kicker: `${sourceLabel(item.source_type)} · ${evidenceLabel(item.evidence_type)}`, title: item.title || "Community receipt", body: `<p class="receipt-paraphrase">${escapeHtml(item.paraphrase)}</p><div class="observations"><section><h3>Useful signal</h3>${list(item.positive_observations)}</section><section><h3>Limits / open questions</h3>${list(item.negative_observations)}</section></div>${renderMedia(item)}<p class="metadata">Published ${escapeHtml(item.publication_date || "date unavailable")} · Accessed ${escapeHtml(item.access_date || "date unavailable")}${item.author ? ` · u/${escapeHtml(item.author)}` : ""}${item.subreddit ? ` · r/${escapeHtml(item.subreddit)}` : ""}</p><p class="dialog-actions"><a class="card-action" href="${escapeHtml(httpsUrl(item.url))}" target="_blank" rel="noopener noreferrer">Open public source <span aria-hidden="true">↗</span></a>${familyId ? `<a class="card-action secondary" href="#bag/${encodeURIComponent(familyId)}" data-route>Open family file <span aria-hidden="true">→</span></a>` : ""}</p>` };
}

function researchDialog(kind, id) {
  if (kind === "campaign") {
    const item = (state.research.campaigns || []).find(row => row.id === id);
    return item && { kicker: "Research campaign", title: item.name, body: `<p>${escapeHtml(item.scope)}</p><p class="metadata">${escapeHtml(label(item.status))}${item.started_at ? ` · started ${escapeHtml(item.started_at)}` : ""}${item.completed_at ? ` · completed ${escapeHtml(item.completed_at)}` : ""}</p>` };
  }
  if (kind === "lane") {
    const item = (state.research.research_lanes || []).find(row => row.id === id);
    return item && { kicker: "Independent research lane", title: `r/${item.subreddit_focus}`, body: `<p>${escapeHtml(item.scope)}</p><p>${escapeHtml(item.status_note || "")}</p><p class="metadata">${escapeHtml(label(item.status))} · ${plural(item.families_checked || 0, "family", "families")} checked</p>` };
  }
  const scans = state.research.scan_log || [];
  const item = scans.flatMap(scan => (scan.candidate_sources || []).map(row => ({ ...row, checked_at: scan.checked_at, source_url: scan.source_url }))).find(row => row.url === id);
  return item && { kicker: `${evidenceLabel(item.evidence_type)} · ${label(item.status)}`, title: item.title, body: `<p>${escapeHtml(item.note)}</p><p class="metadata">Scan checked ${escapeHtml(item.checked_at || "date unavailable")}${item.author ? ` · u/${escapeHtml(item.author)}` : ""}</p><p class="dialog-actions"><a class="card-action" href="${escapeHtml(httpsUrl(item.url))}" target="_blank" rel="noopener noreferrer">Open public post <span aria-hidden="true">↗</span></a></p>` };
}

function notesDialog(family) {
  const notes = cleanList([...familyEvidence(family).flatMap(item => item.negative_observations || []), ...(family.research_gaps || [])]);
  return { kicker: "QC & research gaps", title: `${family.brand} ${family.model}`, body: list(notes, "dialog-note-list") };
}

function dialogContent(kind, id) {
  if (kind === "evidence") return evidenceDialog(state.maps.evidence.get(id));
  if (kind === "seller") return sellerDialog(state.maps.sellers.get(id));
  if (kind === "factory") return factoryDialog(state.maps.factories.get(id));
  if (kind === "notes") return notesDialog(state.maps.families.get(id));
  return researchDialog(kind, id);
}

function openDialog(opener) {
  const content = dialogContent(opener.dataset.dialogKind, opener.dataset.dialogId);
  if (!content) return;
  dialogOpener = opener;
  dialogScrollPosition = window.scrollY;
  document.querySelector("#dialog-kicker").textContent = content.kicker;
  document.querySelector("#dialog-title").textContent = content.title;
  document.querySelector("#dialog-body").innerHTML = content.body;
  document.body.style.setProperty("--dialog-scroll-offset", `-${dialogScrollPosition}px`);
  document.documentElement.classList.add("dialog-open");
  document.body.classList.add("dialog-open");
  document.querySelector("#content-dialog").showModal();
}

function closeDialog() {
  const dialog = document.querySelector("#content-dialog");
  if (dialog.open) dialog.close();
}

function resetEvidenceControls() {
  ["evidence-search", "source-filter", "evidence-type-detail-filter", "match-filter"].forEach(id => { document.querySelector(`#${id}`).value = ""; });
}

function parseRoute() {
  const raw = location.hash.slice(1);
  if (!raw) return { kind: "welcome" };
  const queryIndex = raw.indexOf("?");
  const rawPath = queryIndex === -1 ? raw : raw.slice(0, queryIndex);
  const query = queryIndex === -1 ? "" : raw.slice(queryIndex + 1);
  let path;
  try { path = decodeURIComponent(rawPath); } catch { path = rawPath; }
  if (path.startsWith("bag/")) return { kind: "view", view: "bag-detail", familyId: path.slice(4) };
  if (path === "evidence") {
    const params = new URLSearchParams(query);
    if (params.get("family")) return { kind: "view", view: "evidence", context: { kind: "family", id: params.get("family") } };
    if (params.get("variant")) return { kind: "view", view: "evidence", context: { kind: "variant", id: params.get("variant") } };
  }
  return { kind: "view", view: primaryViews.includes(path) ? path : "bags" };
}

function activateView(viewId) {
  document.querySelectorAll(".view").forEach(view => view.classList.toggle("active", view.id === viewId));
  const navView = viewId === "bag-detail" ? "bags" : viewId;
  document.querySelectorAll("[data-view-nav]").forEach(link => {
    const current = link.dataset.viewNav === navView;
    link.classList.toggle("active", current);
    if (current) link.setAttribute("aria-current", "page"); else link.removeAttribute("aria-current");
  });
}

function transitionView(update) {
  if (!reducedMotion.matches && document.startViewTransition) {
    try {
      return document.startViewTransition(update).updateCallbackDone.catch(error => {
        if (error?.name === "AbortError" || error?.name === "InvalidStateError") return;
        throw error;
      });
    } catch (error) {
      if (error?.name !== "AbortError" && error?.name !== "InvalidStateError") return Promise.reject(error);
      update();
      return Promise.resolve();
    }
  }
  update();
  return Promise.resolve();
}

function focusAndScroll(route, focus, scroll) {
  window.requestAnimationFrame(() => {
    if (scroll) window.scrollTo({ top: 0, behavior: reducedMotion.matches ? "auto" : "smooth" });
    if (!focus) return;
    const target = route.kind === "welcome" ? document.querySelector("#welcome-title") : route.view === "bag-detail" ? document.querySelector("#bag-detail-title") : document.querySelector(`#${route.view}-title`);
    target?.focus({ preventScroll: true });
  });
}

function routeCurrent({ focus = false, scroll = false } = {}) {
  const route = parseRoute();
  if (!ready && route.kind !== "welcome") return;
  if (route.kind === "welcome") {
    activeEvidenceContext = null;
    transitionView(() => {
      setDisplayMode("welcome");
      restartWelcomeAnimation();
    }).then(() => focusAndScroll(route, focus, true));
    return;
  }
  transitionView(() => {
    setDisplayMode("app");
    if (route.view === "bag-detail") {
      activeEvidenceContext = null;
      renderBagDetail(route.familyId);
    } else if (route.view === "evidence") {
      const oldKey = activeEvidenceContext ? `${activeEvidenceContext.kind}:${activeEvidenceContext.id}` : "";
      const newKey = route.context ? `${route.context.kind}:${route.context.id}` : "";
      if (oldKey !== newKey) resetEvidenceControls();
      activeEvidenceContext = route.context || null;
      renderEvidence();
    } else {
      activeEvidenceContext = null;
    }
    activateView(route.view);
  }).then(() => focusAndScroll(route, focus, scroll));
}

function navigate(hash, { replace = false } = {}) {
  const cleanHash = String(hash || "").replace(/^#/, "");
  const url = cleanHash ? `#${cleanHash}` : `${location.pathname}${location.search}`;
  history[replace ? "replaceState" : "pushState"](null, "", url);
  routeCurrent({ focus: true, scroll: true });
}

function bindControls() {
  ["bag-search", "brand-filter", "type-filter", "size-filter", "material-filter", "evidence-type-filter", "bag-sort"].forEach(id => {
    document.querySelector(`#${id}`).addEventListener("input", renderBags);
    document.querySelector(`#${id}`).addEventListener("change", renderBags);
  });
  ["evidence-search", "source-filter", "evidence-type-detail-filter", "match-filter"].forEach(id => {
    document.querySelector(`#${id}`).addEventListener("input", renderEvidence);
    document.querySelector(`#${id}`).addEventListener("change", renderEvidence);
  });
  document.body.addEventListener("click", event => {
    const close = event.target.closest("[data-dialog-close]");
    if (close) return closeDialog();
    const dialogTrigger = event.target.closest(".dialog-trigger");
    if (dialogTrigger) return openDialog(dialogTrigger);
    if (event.target.closest("[data-enter-site]")) return enterCatalogFromWelcome();
    if (event.target.closest("[data-welcome-route]")) {
      event.preventDefault();
      closeDialog();
      return navigate("");
    }
    if (event.target.closest("[data-clear-evidence]")) {
      resetEvidenceControls();
      activeEvidenceContext = null;
      return navigate("evidence");
    }
    const routeLink = event.target.closest("[data-route]");
    if (routeLink) {
      event.preventDefault();
      closeDialog();
      return navigate(routeLink.getAttribute("href"));
    }
  });
  const dialog = document.querySelector("#content-dialog");
  dialog.addEventListener("click", event => { if (event.target === dialog) closeDialog(); });
  dialog.addEventListener("keydown", event => {
    if (event.key === "Escape" && dialog.open) {
      event.preventDefault();
      closeDialog();
    }
  });
  dialog.addEventListener("close", () => {
    document.documentElement.classList.remove("dialog-open");
    document.body.classList.remove("dialog-open");
    document.body.style.removeProperty("--dialog-scroll-offset");
    window.scrollTo({ top: dialogScrollPosition, behavior: "auto" });
    const target = dialogOpener;
    dialogOpener = null;
    if (target?.isConnected) target.focus();
  });
  let routeQueued = false;
  const queueRoute = () => {
    if (routeQueued) return;
    routeQueued = true;
    queueMicrotask(() => {
      routeQueued = false;
      routeCurrent({ focus: true, scroll: true });
    });
  };
  window.addEventListener("popstate", queueRoute);
  window.addEventListener("hashchange", queueRoute);
  reducedMotion.addEventListener?.("change", () => document.documentElement.classList.toggle("reduced-motion", reducedMotion.matches));
}

function fillFilters() {
  fillSelect("#brand-filter", state.bag_families.map(item => item.brand));
  fillSelect("#type-filter", state.bag_families.map(item => item.category));
  fillSelect("#size-filter", state.bag_families.flatMap(item => [...(item.documented_sizes || []), ...familyVariants(item).map(variant => variant.size)]));
  fillSelect("#material-filter", state.bag_families.flatMap(item => [...(item.documented_materials || []), ...familyVariants(item).map(variant => variant.material)]));
  fillSelect("#evidence-type-filter", state.evidence.map(item => item.evidence_type));
  fillSelect("#source-filter", state.evidence.map(item => item.source_type));
  fillSelect("#evidence-type-detail-filter", state.evidence.map(item => item.evidence_type));
}

async function init() {
  try {
    await loadData();
    fillFilters();
    renderWelcomeVoices();
    renderSnapshot();
    renderBags();
    renderSellers();
    renderEvidence();
    renderResearch();
    bindControls();
    ready = true;
    routeCurrent();
  } catch (error) {
    setDisplayMode("app");
    document.querySelector("#main-content").innerHTML = `<p class="empty">The research data could not load. ${escapeHtml(error.message)} Run this site through the local server rather than opening the file directly.</p>`;
  }
}

init();
