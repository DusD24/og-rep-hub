const files = ["bag_families", "bags", "sellers", "factories", "offerings", "evidence", "contacts", "media", "outreach", "rankings", "research"];
const state = Object.create(null);
const primaryViews = ["bags", "sellers", "evidence", "research"];

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

const escapeHtml = (value = "") => String(value).replace(/[&<>'"]/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
}[char]));
const byId = rows => new Map(rows.map(row => [row.id, row]));
const label = value => String(value || "unknown").replaceAll("_", " ");
const statusLabel = value => STATUS_LABELS[value] || label(value);
const evidenceLabel = value => EVIDENCE_LABELS[value] || label(value);
const sourceLabel = value => label(value).replace(/^reddit /, "Reddit ");
const httpsUrl = value => /^https:\/\//.test(value || "") ? value : "#";
const daysOld = value => Math.floor((Date.now() - Date.parse(`${value}T00:00:00Z`)) / 86400000);
const isStale = value => value && daysOld(value) > 180;
const unique = values => [...new Set(values.filter(Boolean))];
const cleanList = values => unique((values || []).map(value => String(value).trim()).filter(Boolean));

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
    rankings: byId(state.rankings.rankings.map(row => ({ id: row.offering_id, ...row })))
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
  return (family.documented_variant_ids || []).map(id => state.maps.bags.get(id)).filter(Boolean);
}

function familyEvidence(family) {
  const variantIds = new Set((family.documented_variant_ids || []).filter(Boolean));
  return state.evidence.filter(item => (item.family_ids || []).includes(family.id) || (item.bag_ids || []).some(id => variantIds.has(id)));
}

function familyOfferings(family) {
  const variantIds = new Set((family.documented_variant_ids || []).filter(Boolean));
  return state.offerings.filter(item => item.family_id === family.id || variantIds.has(item.variant_id || item.bag_id));
}

function familyCoverage(family) {
  const evidence = familyEvidence(family);
  const authors = unique(evidence.map(item => item.author).filter(Boolean).map(author => author.toLowerCase()));
  const sourceCount = evidence.length || family.evidence_coverage?.source_count || 0;
  return {
    sourceCount,
    authorCount: authors.length || family.evidence_coverage?.independent_author_count || 0,
    subreddits: unique(evidence.map(item => item.subreddit).filter(Boolean)),
    evidenceTypes: unique(evidence.map(item => item.evidence_type).filter(Boolean)),
    imageReady: Boolean(family.tile_media_id && state.maps.media.has(family.tile_media_id))
  };
}

function renderSnapshot() {
  const published = state.bag_families.filter(item => item.publication_status === "published").length;
  const mediaReady = state.bag_families.filter(item => familyCoverage(item).imageReady).length;
  const stats = [
    [state.bag_families.length, "bag families"],
    [published, "published with receipts"],
    [state.evidence.length, "reviews & receipts"],
    [mediaReady, "Reddit tiles"],
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
  const types = evidence.map(item => item.evidence_type);
  return (!query || familySearchText(family).includes(query))
    && (!brand || family.brand === brand)
    && (!type || family.category === type)
    && (!size || sizes.includes(size))
    && (!material || materials.includes(material))
    && (!evidenceType || types.includes(evidenceType));
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

function renderFamilyTile(family, detail = false) {
  const media = state.maps.media.get(family.tile_media_id);
  if (!media) {
    const candidate = family.candidate_tile;
    const candidateLink = candidate?.post_url ? `<a href="${escapeHtml(httpsUrl(candidate.post_url))}" target="_blank" rel="noopener noreferrer">Review candidate post ↗</a>` : "";
    return `<div class="family-tile family-tile-empty" role="img" aria-label="No representative Reddit image has been archived for ${escapeHtml(family.brand)} ${escapeHtml(family.model)}"><span class="tile-kicker">Reddit tile pending</span><strong>Do not publish yet</strong><span>${candidate ? "A candidate post is logged; archive and hash the user image before publication." : "Waiting for a public, user-posted image with provenance."}</span>${candidateLink}</div>`;
  }
  return `<a class="bag-tile${detail ? " detail-tile" : ""}" href="${escapeHtml(httpsUrl(media.post_url || media.source_url))}" target="_blank" rel="noopener noreferrer" aria-label="Open Reddit source for ${escapeHtml(family.brand)} ${escapeHtml(family.model)} image"><img src="${escapeHtml(media.path)}" alt="${escapeHtml(media.alt)}" loading="lazy" onerror="this.closest('.bag-tile').classList.add('missing')"><span class="bag-tile-source">Reddit photo · ${escapeHtml(media.attribution)} ↗</span></a>`;
}

function renderFamilyCard(family) {
  const coverage = familyCoverage(family);
  const badges = familyBadges(family);
  const status = family.publication_status === "published" ? "Published with receipts" : "Research queue · not published";
  return `<article class="card family-card" data-family-id="${escapeHtml(family.id)}">
    ${renderFamilyTile(family)}
    <div class="card-top"><div class="tags"><span class="tag">${escapeHtml(family.brand)}</span><span class="tag">${escapeHtml(label(family.category))}</span></div><span class="status-pill ${family.publication_status === "published" ? "published" : "pending"}">${escapeHtml(status)}</span></div>
    <h3><a href="#bag/${escapeHtml(family.id)}" data-family-route="${escapeHtml(family.id)}">${escapeHtml(family.model)}</a></h3>
    <p class="family-brand">${escapeHtml(family.brand)} · ${escapeHtml(family.category)}</p>
    <p class="family-summary">${escapeHtml(family.summary)}</p>
    <div class="badge-row">${badges.map(badge => `<span class="badge">${escapeHtml(badge)}</span>`).join("")}</div>
    <p class="metadata"><span>${coverage.sourceCount} source${coverage.sourceCount === 1 ? "" : "s"}</span><span>•</span><span>${coverage.authorCount} author${coverage.authorCount === 1 ? "" : "s"}</span><span>•</span><span>${escapeHtml(statusLabel(family.publication_status))}</span></p>
    <p><a class="arrow-link" href="#bag/${escapeHtml(family.id)}" data-family-route="${escapeHtml(family.id)}">Open family file →</a></p>
  </article>`;
}

function renderBags() {
  let rows = state.bag_families.filter(familyMatches);
  const sort = document.querySelector("#bag-sort").value;
  rows.sort((a, b) => {
    const coverageA = familyCoverage(a);
    const coverageB = familyCoverage(b);
    if (sort === "recently_updated") return String(b.last_updated).localeCompare(String(a.last_updated)) || a.model.localeCompare(b.model);
    if (sort === "az") return `${a.brand} ${a.model}`.localeCompare(`${b.brand} ${b.model}`);
    return coverageB.sourceCount - coverageA.sourceCount || coverageB.authorCount - coverageA.authorCount || a.model.localeCompare(b.model);
  });
  const container = document.querySelector("#bag-results");
  container.innerHTML = rows.length ? rows.map(renderFamilyCard).join("") : '<p class="empty">No bag families match these filters. Try clearing one filter or search the research queue.</p>';
}

function renderReportedList(ids, map, empty = "Nothing named in the current sources.") {
  const names = unique(ids.map(id => map.get(id)?.display_name).filter(Boolean));
  return names.length ? `<ul>${names.map(name => `<li>${escapeHtml(name)} <span class="fineprint">as reported</span></li>`).join("")}</ul>` : `<span class="fineprint">${escapeHtml(empty)}</span>`;
}

function renderSellers() {
  const sellerContainer = document.querySelector("#seller-results");
  sellerContainer.innerHTML = state.sellers.length ? state.sellers.map(seller => {
    const contacts = state.contacts.filter(item => item.seller_id === seller.id);
    const offers = state.offerings.filter(item => item.seller_id === seller.id);
    const evidenceCount = state.evidence.filter(item => (item.seller_ids || []).includes(seller.id)).length;
    const links = contacts.length ? contacts.map(contact => `<div><a class="contact-link" href="${escapeHtml(httpsUrl(contact.link_url || contact.public_source_url))}" target="_blank" rel="noopener noreferrer">${escapeHtml(sourceLabel(contact.channel))}: ${escapeHtml(contact.value)} ↗</a><a class="contact-source" href="${escapeHtml(httpsUrl(contact.public_source_url))}" target="_blank" rel="noopener noreferrer">${escapeHtml(contact.source_label || "Public source")} ↗</a></div>`).join("") : seller.community_contact_status === "removed_from_community_wiki" ? '<span class="fineprint">No public contact imported; the source notes removal.</span>' : '<span class="fineprint">No public contact channel verified.</span>';
    const communityNote = seller.community_contact_status === "community_listed"
      ? '<p class="fineprint">Community-listed contact; verify the public source before use.</p>'
      : seller.community_contact_status === "removed_from_community_wiki"
        ? '<p class="fineprint">Community source status: removed; no contact is imported.</p>'
        : "";
    return `<article class="seller-row"><div><h3>${escapeHtml(seller.display_name)}</h3><p class="metadata">${evidenceCount} source${evidenceCount === 1 ? "" : "s"} · checked ${escapeHtml(seller.last_verified)}</p><p class="fineprint">${escapeHtml(seller.confidence_note || "Names remain tied to the linked public evidence.")}</p></div><div><strong>${offers.length}</strong> exact-variant offering${offers.length === 1 ? "" : "s"}<p class="fineprint">Status and metrics stay tied to the reported variant and source.</p></div><div>${links}${communityNote}</div></article>`;
  }).join("") : '<p class="empty">No named seller has cleared the public-source checks yet.</p>';

  const factoryContainer = document.querySelector("#factory-results");
  factoryContainer.innerHTML = state.factories.length ? state.factories.map(factory => {
    const evidence = state.evidence.filter(item => (item.factory_ids || []).includes(factory.id));
    const variantNames = unique(evidence.flatMap(item => (item.bag_ids || []).map(id => state.maps.bags.get(id)?.name)).filter(Boolean));
    return `<article class="factory-row"><div><h3>${escapeHtml(factory.display_name)}</h3><p class="metadata">${evidence.length} source${evidence.length === 1 ? "" : "s"} · as reported</p></div><p class="fineprint">${escapeHtml(factory.notes)}</p><div>${variantNames.length ? `<strong>Reported on</strong><p>${variantNames.map(escapeHtml).join("<br>")}</p>` : '<span class="fineprint">No exact bag variant named.</span>'}</div></article>`;
  }).join("") : '<p class="empty">No factory names are currently documented.</p>';
}

function renderMedia(item) {
  const rows = (item.media_ids || []).map(id => state.maps.media.get(id)).filter(Boolean);
  if (!rows.length) return '<p class="media-fallback">No selected media archived. Use the public source for original context.</p>';
  return `<div class="evidence-media">${rows.map(media => `<figure><img src="${escapeHtml(media.path)}" alt="${escapeHtml(media.alt || media.research_purpose)}" loading="lazy" onerror="this.closest('figure').classList.add('missing')"><figcaption>${escapeHtml(media.attribution)} · ${escapeHtml(media.capture_date)}</figcaption></figure>`).join("")}</div>`;
}

function list(items = []) {
  const rows = cleanList(items);
  return rows.length ? `<ul>${rows.map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : '<span class="fineprint">None recorded.</span>';
}

function evidenceFamilyId(item) {
  if (item.family_ids?.length) return item.family_ids[0];
  return state.bag_families.find(family => (item.bag_ids || []).some(id => (family.documented_variant_ids || []).includes(id)))?.id;
}

function renderEvidenceItem(item, compact = false) {
  const familyId = evidenceFamilyId(item);
  return `<article class="evidence-item${compact ? " compact" : ""}" data-evidence-id="${escapeHtml(item.id)}">
    <div class="source-line"><span class="tag">${escapeHtml(sourceLabel(item.source_type))}</span><span class="tag accent-tag">${escapeHtml(evidenceLabel(item.evidence_type))}</span><span class="tag">${item.exact_product_match ? "exact variant" : "related evidence"}</span>${item.author ? `<span class="tag">u/${escapeHtml(item.author)}</span>` : ""}</div>
    <h3>${escapeHtml(item.title || item.paraphrase.slice(0, 65))}</h3>
    <p>${escapeHtml(item.paraphrase)}</p>
    <div class="observations"><div><h4>Useful signal</h4>${list(item.positive_observations)}</div><div><h4>Limits / open questions</h4>${list(item.negative_observations)}</div></div>
    ${compact ? "" : renderMedia(item)}
    <p class="metadata">Published ${escapeHtml(item.publication_date)} · Accessed ${escapeHtml(item.access_date)}${item.subreddit ? ` · r/${escapeHtml(item.subreddit)}` : ""}</p>
    <p class="link-row"><a href="${escapeHtml(httpsUrl(item.url))}" target="_blank" rel="noopener noreferrer">Open public source ↗</a>${familyId ? ` <a href="#bag/${escapeHtml(familyId)}" data-family-route="${escapeHtml(familyId)}">Open family file →</a>` : ""}</p>
  </article>`;
}

function renderEvidence() {
  const query = document.querySelector("#evidence-search").value.trim().toLowerCase();
  const source = document.querySelector("#source-filter").value;
  const evidenceType = document.querySelector("#evidence-type-detail-filter").value;
  const match = document.querySelector("#match-filter").value;
  const rows = state.evidence.filter(item => {
    const haystack = [item.id, item.author, item.subreddit, item.title, item.paraphrase, item.evidence_type, ...(item.positive_observations || []), ...(item.negative_observations || [])].join(" ").toLowerCase();
    return (!query || haystack.includes(query)) && (!source || item.source_type === source) && (!evidenceType || item.evidence_type === evidenceType) && (!match || String(item.exact_product_match) === match);
  }).sort((a, b) => String(b.publication_date).localeCompare(String(a.publication_date)));
  const container = document.querySelector("#evidence-results");
  container.innerHTML = rows.length ? rows.map(item => renderEvidenceItem(item)).join("") : '<p class="empty">No reviews or receipts match these filters.</p>';
}

function renderVariantMedia(family) {
  const rows = familyVariants(family).map(variant => {
    const media = state.maps.media.get(variant.tile_media_id);
    return media ? { variant, media } : null;
  }).filter(Boolean);
  if (!rows.length) return '<p class="media-fallback">No variant media is archived yet. A family tile cannot be published until a suitable Reddit image is documented.</p>';
  return `<div class="variant-media-grid">${rows.map(({variant, media}) => `<figure><a href="${escapeHtml(httpsUrl(media.post_url || media.source_url))}" target="_blank" rel="noopener noreferrer"><img src="${escapeHtml(media.path)}" alt="${escapeHtml(media.alt)}" loading="lazy" onerror="this.closest('a').classList.add('missing')"></a><figcaption><strong>${escapeHtml(variant.name)}</strong><br>${escapeHtml(media.attribution)} · Reddit source ↗</figcaption></figure>`).join("")}</div>`;
}

function renderVariantRows(family) {
  const variants = familyVariants(family);
  if (!variants.length) return '<p class="empty compact-empty">No source-documented variants yet. Add a public source through the contribution path.</p>';
  return `<div class="variant-list">${variants.map(variant => {
    const evidenceCount = state.evidence.filter(item => (item.bag_ids || []).includes(variant.id)).length;
    return `<article class="variant-row"><div><h4>${escapeHtml(variant.name)}</h4><p class="metadata">${escapeHtml(variant.size)} · ${escapeHtml(variant.pattern)} · ${escapeHtml(variant.colorway)}</p></div><div><span class="fineprint">Material</span><p>${escapeHtml(variant.material || "Not documented")}</p></div><div><span class="fineprint">Hardware</span><p>${escapeHtml(variant.hardware || "Not documented")}</p></div><div><span class="fineprint">Receipts</span><p>${evidenceCount}</p></div></article>`;
  }).join("")}</div>`;
}

function renderReportedParties(family) {
  const evidence = familyEvidence(family);
  const sellerIds = unique(evidence.flatMap(item => item.seller_ids || []));
  const factoryIds = unique(evidence.flatMap(item => item.factory_ids || []));
  const offerings = familyOfferings(family);
  return `<div class="party-grid"><div><h4>Sellers</h4>${renderReportedList(sellerIds, state.maps.sellers)}<p class="fineprint">Names are attributed to the linked public sources.</p></div><div><h4>Factories / batches</h4>${renderReportedList(factoryIds, state.maps.factories)}<p class="fineprint">“Unknown / undisclosed” means no named factory was supported.</p></div><div><h4>Exact-variant offerings</h4>${offerings.length ? `<ul>${offerings.map(offering => `<li>${escapeHtml(state.maps.sellers.get(offering.seller_id)?.display_name || "Seller not named")} · ${escapeHtml(state.maps.bags.get(offering.variant_id || offering.bag_id)?.name || "Variant not named")} · ${escapeHtml(statusLabel(offering.status))}</li>`).join("")}</ul>` : '<span class="fineprint">No seller offering is linked to this family yet.</span>'}</div></div>`;
}

function renderDetailScores(family) {
  const rows = familyOfferings(family).map(offering => {
    const ranking = state.maps.rankings.get(offering.id);
    if (!ranking || ranking.rank_status !== "ranked") return null;
    return `<article class="signal-row"><div><strong>${escapeHtml(state.maps.sellers.get(offering.seller_id)?.display_name || "Seller")}</strong><span>${escapeHtml(state.maps.bags.get(offering.variant_id || offering.bag_id)?.name || "Exact variant")}</span></div><div class="score-inline"><strong>${escapeHtml(String(ranking.recommendation_score))}</strong><span>Community signal</span></div><p class="fineprint">Numerical detail shown only when the current evidence gates are satisfied.</p></article>`;
  }).filter(Boolean);
  return rows.length ? `<div class="signal-list">${rows.join("")}</div>` : '<p class="media-fallback">No numerical Community signal is shown yet. The current evidence does not satisfy the detail-level gates.</p>';
}

function renderBagDetail(familyId) {
  const family = state.maps.families.get(familyId);
  const container = document.querySelector("#bag-detail-content");
  if (!family) {
    container.innerHTML = '<p class="empty">That bag family could not be found. Return to Bags and choose a family file.</p>';
    return;
  }
  const coverage = familyCoverage(family);
  const evidence = familyEvidence(family);
  const sizes = family.documented_sizes?.length ? family.documented_sizes : familyVariants(family).map(item => item.size);
  const materials = family.documented_materials?.length ? family.documented_materials : familyVariants(family).map(item => item.material);
  const hardware = family.documented_hardware?.length ? family.documented_hardware : familyVariants(family).map(item => item.hardware);
  const qcPoints = cleanList(evidence.flatMap(item => item.negative_observations || []));
  const statusCopy = family.publication_status === "published"
    ? "This family has a Reddit tile and the original campaign evidence is available below."
    : "This family is in the research queue and is not published as a sourced catalog entry until the author and image requirements are met.";
  container.innerHTML = `<a class="back-link" href="#bags" data-view-link="bags">← Back to Bags</a>
    <div class="detail-hero">
      <div>${renderFamilyTile(family, true)}</div>
      <div><p class="eyebrow">${escapeHtml(family.brand)} · ${escapeHtml(label(family.category))}</p><h1 id="bag-detail-title">${escapeHtml(family.model)}</h1><p class="detail-summary">${escapeHtml(family.summary)}</p><div class="badge-row">${familyBadges(family).map(badge => `<span class="badge">${escapeHtml(badge)}</span>`).join("")}</div><p class="status-note ${family.publication_status === "published" ? "published" : "pending"}">${escapeHtml(statusCopy)}</p><p class="metadata">Updated ${escapeHtml(family.last_updated)} · ${coverage.sourceCount} source${coverage.sourceCount === 1 ? "" : "s"} · ${coverage.authorCount} independent author${coverage.authorCount === 1 ? "" : "s"}</p></div>
    </div>
    <div class="detail-grid">
      <section class="detail-panel"><p class="eyebrow">Source-documented details</p><h2>What the receipts describe</h2><div class="fact-grid"><div><h4>Sizes</h4>${list(sizes)}</div><div><h4>Materials</h4>${list(materials)}</div><div><h4>Hardware</h4>${list(hardware)}</div><div><h4>Subreddits</h4>${list(coverage.subreddits.map(value => `r/${value}`))}</div></div></section>
      <section class="detail-panel"><p class="eyebrow">Variant file</p><h2>Exact variants</h2>${renderVariantRows(family)}</section>
      <section class="detail-panel"><p class="eyebrow">As reported</p><h2>Sellers &amp; factories</h2>${renderReportedParties(family)}</section>
      <section class="detail-panel"><p class="eyebrow">Variant / evidence media</p><h2>Reddit images</h2>${renderVariantMedia(family)}</section>
      <section class="detail-panel"><p class="eyebrow">Detail-only scoring</p><h2>Community signal</h2>${renderDetailScores(family)}</section>
      <section class="detail-panel"><p class="eyebrow">Open questions</p><h2>QC points &amp; research gaps</h2>${list([...qcPoints, ...(family.research_gaps || [])])}</section>
    </div>
    <section class="detail-panel detail-evidence"><div class="section-heading"><div><p class="eyebrow">Linked source trail</p><h2>Reviews &amp; receipts</h2></div><a class="arrow-link" href="#evidence" data-view-link="evidence">See reviews &amp; receipts →</a></div>${evidence.length ? `<div class="evidence-list">${evidence.map(item => renderEvidenceItem(item, true)).join("")}</div>` : '<p class="empty">No family-linked public sources yet.</p>'}</section>`;
}

function renderResearch() {
  const campaigns = state.research.campaigns || [];
  const lanes = state.research.research_lanes || [];
  const queue = state.outreach.queue || [];
  const forms = [
    ["Suggest a Bag", "Add a family candidate with public source URLs and no private contact details.", "suggest-a-bag.yml"],
    ["Submit a Reddit Source", "Add a review, PSP/QC post, auth comparison, or in-hand receipt with provenance.", "submit-reddit-source.yml"],
    ["Correction or Media Removal", "Flag a source, attribution, image, or research note for review.", "correction-or-media-removal.yml"]
  ];
  const glossary = state.research.glossary || [];
  const glossarySource = state.research.glossary_source_url ? `<p class="scope-note">Definitions are adapted from the <a href="${escapeHtml(httpsUrl(state.research.glossary_source_url))}" target="_blank" rel="noopener noreferrer">r/RepTherapy glossary ↗</a>.</p>` : "";
  const scanLogs = state.research.scan_log || [];
  const scanMarkup = scanLogs.length ? `<section class="research-panel scan-panel"><div class="section-heading"><div><p class="eyebrow">Latest scan</p><h2>r/RepLadiesWorld leads</h2></div><p class="scope-note">Leads stay separate from normalized evidence until the post, author, bag family, and limits are checked.</p></div>${scanLogs.map(scan => `<p class="metadata">Checked ${escapeHtml(scan.checked_at)} · <a href="${escapeHtml(httpsUrl(scan.source_url))}" target="_blank" rel="noopener noreferrer">Open subreddit ↗</a></p><div class="scan-list">${(scan.candidate_sources || []).map(item => `<article class="scan-row"><div><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.status || "candidate")}</span></div><p>${escapeHtml(item.note)}</p><p class="link-row"><a href="${escapeHtml(httpsUrl(item.url))}" target="_blank" rel="noopener noreferrer">Open public post ↗</a></p></article>`).join("")}</div>${(scan.exclusions || []).map(note => `<p class="fineprint">${escapeHtml(note)}</p>`).join("")}`).join("")}</section>` : "";
  document.querySelector("#research-results").innerHTML = `<div class="research-grid"><section class="research-panel"><p class="eyebrow">Dated campaigns</p><h2>How this corpus grew</h2><div class="campaign-list">${campaigns.map(campaign => `<article class="campaign-row"><div><h3>${escapeHtml(campaign.name)}</h3><p class="metadata">${escapeHtml(campaign.status)}${campaign.started_at ? ` · started ${escapeHtml(campaign.started_at)}` : ""}${campaign.completed_at ? ` · completed ${escapeHtml(campaign.completed_at)}` : ""}</p></div><p>${escapeHtml(campaign.scope)}</p></article>`).join("")}</div><div class="lane-list"><h3>Independent research lanes</h3>${lanes.map(lane => `<div class="lane-row"><strong>r/${escapeHtml(lane.subreddit_focus)}</strong><span>${escapeHtml(lane.status)} · ${escapeHtml(String(lane.families_checked || 0))} ${lane.families_checked === 1 ? "family" : "families"} checked</span><p>${escapeHtml(lane.scope)}</p><p class="fineprint">${escapeHtml(lane.status_note || "")}</p></div>`).join("")}</div></section><section class="research-panel"><p class="eyebrow">First-use notes</p><h2>Rep vocabulary</h2>${glossarySource}<dl class="glossary">${glossary.map(item => `<div><dt>${escapeHtml(item.term)}</dt><dd>${escapeHtml(item.definition)}</dd></div>`).join("")}</dl></section></div>${scanMarkup}
    <section class="research-panel gap-panel"><div class="section-heading"><div><p class="eyebrow">Contribution queue</p><h2>Help Fill the Gaps</h2></div><p class="scope-note">Every submission needs a public URL. Do not include private messages, payment details, addresses, or unverified contact information.</p></div>${queue.length ? `<div class="queue-table-wrap"><table class="queue-table"><thead><tr><th>Priority</th><th>Family</th><th>Exact ask</th><th>Status</th></tr></thead><tbody>${queue.map(item => { const family = state.maps.bags.get(item.bag_id)?.family_id ? state.maps.families.get(state.maps.bags.get(item.bag_id).family_id) : null; return `<tr><td>${escapeHtml(item.priority)}</td><td>${escapeHtml(family?.model || "Family gap")}</td><td>${escapeHtml(item.question)}</td><td>${escapeHtml(label(item.status))}</td></tr>`; }).join("")}</tbody></table></div>` : '<p class="empty">No open research questions are queued.</p>'}</section>
    <section class="research-panel form-panel"><p class="eyebrow">Public contribution paths</p><h2>Bring a receipt</h2><div class="form-link-grid">${forms.map(([title, description, template]) => `<a class="form-link" href="https://github.com/DusD24/og-rep-hub/issues/new?template=${encodeURIComponent(template)}" target="_blank" rel="noopener noreferrer"><strong>${escapeHtml(title)} ↗</strong><span>${escapeHtml(description)}</span></a>`).join("")}</div></section>`;
}

function activateView(id) {
  document.querySelectorAll(".view").forEach(view => view.classList.toggle("active", view.id === id));
  const navId = id === "bag-detail" ? "bags" : id;
  document.querySelectorAll(".view-nav button").forEach(button => button.classList.toggle("active", button.dataset.view === navId));
}

function openFamily(familyId, updateUrl = true) {
  renderBagDetail(familyId);
  activateView("bag-detail");
  if (updateUrl) history.replaceState(null, "", `#bag/${encodeURIComponent(familyId)}`);
  if (updateUrl) document.querySelector("main").scrollIntoView({behavior: "smooth"});
}

function showView(id, updateUrl = true) {
  if (id === "bag-detail") return;
  activateView(primaryViews.includes(id) ? id : "bags");
  if (updateUrl) history.replaceState(null, "", `#${primaryViews.includes(id) ? id : "bags"}`);
  if (updateUrl) document.querySelector("main").scrollIntoView({behavior: "smooth"});
}

function routeHash() {
  const hash = decodeURIComponent(location.hash.slice(1));
  if (hash.startsWith("bag/")) return openFamily(hash.slice(4), false);
  if (primaryViews.includes(hash)) {
    showView(hash, false);
    if (hash === "bags") window.setTimeout(() => window.scrollTo({top: 0, behavior: "auto"}), 0);
    return;
  }
  showView("bags", false);
}

function bindControls() {
  document.querySelectorAll(".view-nav button").forEach(button => button.addEventListener("click", () => showView(button.dataset.view)));
  document.querySelectorAll("[data-view-link]").forEach(link => link.addEventListener("click", event => {
    event.preventDefault();
    showView(link.dataset.viewLink);
  }));
  ["bag-search", "brand-filter", "type-filter", "size-filter", "material-filter", "evidence-type-filter", "bag-sort"].forEach(id => {
    document.querySelector(`#${id}`).addEventListener("input", renderBags);
    document.querySelector(`#${id}`).addEventListener("change", renderBags);
  });
  ["evidence-search", "source-filter", "evidence-type-detail-filter", "match-filter"].forEach(id => {
    document.querySelector(`#${id}`).addEventListener("input", renderEvidence);
    document.querySelector(`#${id}`).addEventListener("change", renderEvidence);
  });
  document.body.addEventListener("click", event => {
    const familyLink = event.target.closest("[data-family-route]");
    if (familyLink) {
      event.preventDefault();
      openFamily(familyLink.dataset.familyRoute);
    }
  });
  window.addEventListener("hashchange", routeHash);
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

window.addEventListener("load", () => {
  if (location.hash === "#bags") window.setTimeout(() => window.scrollTo({top: 0, behavior: "auto"}), 50);
});

async function init() {
  try {
    await loadData();
    fillFilters();
    renderSnapshot();
    renderBags();
    renderSellers();
    renderEvidence();
    renderResearch();
    bindControls();
    routeHash();
  } catch (error) {
    document.querySelector("main").innerHTML = `<p class="empty">The research data could not load. ${escapeHtml(error.message)} Run this site through the local server rather than opening the file directly.</p>`;
  }
}

init();
