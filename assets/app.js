const files = ["bags", "sellers", "factories", "offerings", "evidence", "contacts", "media", "outreach", "rankings", "research"];
const state = Object.create(null);

const escapeHtml = (value = "") => String(value).replace(/[&<>'"]/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
}[char]));
const byId = (rows) => new Map(rows.map(row => [row.id, row]));
const label = value => String(value || "unknown").replaceAll("_", " ");
const sourceLabel = value => label(value).replace(/^reddit /, "Reddit ");
const safeUrl = value => /^https:\/\//.test(value || "") ? value : "#";
const daysOld = value => Math.floor((Date.now() - Date.parse(`${value}T00:00:00Z`)) / 86400000);
const isStale = value => value && daysOld(value) > 180;

async function loadData() {
  const results = await Promise.all(files.map(async name => {
    const response = await fetch(`data/${name}.json`);
    if (!response.ok) throw new Error(`${name}: ${response.status}`);
    return [name, await response.json()];
  }));
  results.forEach(([name, value]) => { state[name] = value; });
  state.maps = {
    bags: byId(state.bags), sellers: byId(state.sellers), factories: byId(state.factories),
    evidence: byId(state.evidence), contacts: byId(state.contacts), rankings: byId(state.rankings.rankings.map(row => ({ id: row.offering_id, ...row })))
  };
}

function fillSelect(id, values) {
  const select = document.querySelector(id);
  [...new Set(values.filter(Boolean))].sort().forEach(value => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label(value);
    select.append(option);
  });
}

function renderSnapshot() {
  const ranked = state.rankings.rankings.filter(item => item.rank_status === "ranked").length;
  const stats = [[state.bags.length, "tracked variants"], [state.sellers.length, "sellers"], [state.evidence.length, "public sources"], [ranked, "ranked offers"]];
  document.querySelector("#snapshot").innerHTML = stats.map(([value, name]) => `<div class="stat"><strong>${value}</strong><span>${name}</span></div>`).join("");
}

function catalogRows() {
  const rows = state.offerings.map(offering => ({
    offering,
    bag: state.maps.bags.get(offering.bag_id),
    seller: state.maps.sellers.get(offering.seller_id),
    factory: state.maps.factories.get(offering.factory_id),
    ranking: state.maps.rankings.get(offering.id)
  }));
  state.bags.filter(bag => ["primary", "secondary-priority"].includes(bag.priority) && !state.offerings.some(offering => offering.bag_id === bag.id)).forEach(bag => rows.push({
    offering: {id: `target-${bag.id}`, bag_id: bag.id, status: "unknown", last_verified: state.research.access_date, evidence_ids: []},
    bag,
    seller: {display_name: "No verified seller"},
    factory: {display_name: "Unknown / unresolved"},
    ranking: {rank_status: "unranked", reason: "Exact target remains open: no source proved this size/colorway with a named seller and factory."},
    placeholder: true
  }));
  return rows;
}

function renderCatalog() {
  const query = document.querySelector("#catalog-search").value.trim().toLowerCase();
  const size = document.querySelector("#size-filter").value;
  const color = document.querySelector("#color-filter").value;
  const status = document.querySelector("#status-filter").value;
  const sort = document.querySelector("#catalog-sort").value;
  let rows = catalogRows().filter(({offering, bag, seller, factory}) => {
    const haystack = [bag?.name, bag?.size, bag?.pattern, bag?.colorway, seller?.display_name, factory?.display_name, offering.status].join(" ").toLowerCase();
    return (!query || haystack.includes(query)) && (!size || bag?.size === size) && (!color || bag?.colorway === color) && (!status || offering.status === status);
  });
  rows.sort((a, b) => {
    if (sort === "verified") return b.offering.last_verified.localeCompare(a.offering.last_verified);
    if (sort === "seller") return a.seller.display_name.localeCompare(b.seller.display_name);
    return (b.ranking?.recommendation_score ?? -1) - (a.ranking?.recommendation_score ?? -1);
  });

  const container = document.querySelector("#catalog-results");
  if (!rows.length) {
    container.innerHTML = '<p class="empty">No candidates match these filters. Evidence-poor discoveries may still appear once their exact variant is resolved.</p>';
    return;
  }
  container.innerHTML = rows.map(({offering, bag, seller, factory, ranking, placeholder}) => {
    const unranked = ranking?.rank_status !== "ranked";
    const sourceCount = offering.evidence_ids.length;
    const score = value => value == null ? "—" : value.toFixed(1);
    return `<article class="card">
      <div class="card-top"><div class="tags"><span class="tag">${escapeHtml(bag.size)}</span><span class="tag">${escapeHtml(bag.colorway)}</span><span class="tag">${escapeHtml(label(offering.status))}</span></div><span class="tier ${unranked ? "unranked" : ""}">${escapeHtml(ranking?.tier || "Unranked")}</span></div>
      <h3>${escapeHtml(seller.display_name)} × ${escapeHtml(bag.name)}</h3>
      <p class="factory">Factory/batch: <strong>${escapeHtml(factory.display_name)}</strong></p>
      <div class="score-row"><div class="score"><strong>${score(ranking?.recommendation_score)}</strong><span>recommendation</span></div><div class="score"><strong>${score(ranking?.bag_confidence)}</strong><span>bag confidence</span></div><div class="score"><strong>${score(ranking?.seller_reliability)}</strong><span>seller reliability</span></div></div>
      <p class="metadata"><span>${sourceCount} evidence record${sourceCount === 1 ? "" : "s"}</span><span>•</span><span>Verified ${escapeHtml(offering.last_verified)}</span>${offering.price ? `<span>•</span><span>${escapeHtml(offering.price.display)}</span>` : ""}</p>
      ${isStale(offering.last_verified) ? '<p class="warning">Verification is more than 180 days old. Treat availability as stale.</p>' : ""}
      ${unranked ? `<p class="warning">${escapeHtml(ranking?.reason || "Insufficient evidence for a numerical ranking.")}</p>` : ""}
      ${placeholder ? '<p class="fineprint">Related unresolved candidates appear under the Eden / unknown filters.</p>' : `<p><a href="#evidence" data-open-evidence="${escapeHtml(offering.id)}">Inspect evidence trail →</a></p>`}
    </article>`;
  }).join("");
}

function renderSellers() {
  const container = document.querySelector("#seller-results");
  if (!state.sellers.length) { container.innerHTML = '<p class="empty">No named seller has cleared the evidence and public-contact provenance checks yet.</p>'; return; }
  container.innerHTML = state.sellers.map(seller => {
    const contacts = state.contacts.filter(item => item.seller_id === seller.id);
    const offers = state.offerings.filter(item => item.seller_id === seller.id);
    const links = contacts.length ? contacts.map(contact => `<a class="contact-link" href="${escapeHtml(safeUrl(contact.link_url || contact.public_source_url))}" target="_blank" rel="noopener noreferrer">${escapeHtml(sourceLabel(contact.channel))}: ${escapeHtml(contact.value)} ↗</a>`).join("") : '<span class="fineprint">No public contact channel verified.</span>';
    return `<article class="seller-row"><div><h3>${escapeHtml(seller.display_name)}</h3><p class="metadata">Verified ${escapeHtml(seller.last_verified)}</p></div><div><strong>${offers.length}</strong> tracked offering${offers.length === 1 ? "" : "s"}<p class="fineprint">Seller score is evidence-based and variant quality is scored separately.</p></div><div>${links}</div></article>`;
  }).join("");
}

function renderEvidence() {
  const query = document.querySelector("#evidence-search").value.trim().toLowerCase();
  const source = document.querySelector("#source-filter").value;
  const match = document.querySelector("#match-filter").value;
  let rows = state.evidence.filter(item => {
    const haystack = [item.id, item.author, item.subreddit, item.paraphrase, ...(item.positive_observations || []), ...(item.negative_observations || [])].join(" ").toLowerCase();
    return (!query || haystack.includes(query)) && (!source || item.source_type === source) && (!match || String(item.exact_product_match) === match);
  }).sort((a, b) => b.publication_date.localeCompare(a.publication_date));
  const container = document.querySelector("#evidence-results");
  if (!rows.length) { container.innerHTML = '<p class="empty">No evidence matches these filters.</p>'; return; }
  container.innerHTML = rows.map(item => `<article class="evidence-item" data-evidence-id="${escapeHtml(item.id)}">
    <div class="source-line"><span class="tag">${escapeHtml(sourceLabel(item.source_type))}</span><span class="tag">${item.exact_product_match ? "exact variant" : "related evidence"}</span>${item.author ? `<span class="tag">u/${escapeHtml(item.author)}</span>` : ""}</div>
    <h3>${escapeHtml(item.title || item.paraphrase.slice(0, 65))}</h3>
    <p>${escapeHtml(item.paraphrase)}</p>
    <div class="observations"><div><h4>Positive / useful</h4>${list(item.positive_observations)}</div><div><h4>Negative / limits</h4>${list(item.negative_observations)}</div></div>
    ${renderMedia(item)}
    <p class="metadata">Published ${escapeHtml(item.publication_date)} • Accessed ${escapeHtml(item.access_date)}${item.subreddit ? ` • r/${escapeHtml(item.subreddit)}` : ""}</p>
    <p><a href="${escapeHtml(safeUrl(item.url))}" target="_blank" rel="noopener noreferrer">Open public source ↗</a></p>
  </article>`).join("");
}

function renderMedia(item) {
  const rows = (item.media_ids || []).map(id => state.media.find(media => media.id === id)).filter(Boolean);
  if (!rows.length) return '<p class="media-fallback">No selected media archived. Use the public source for original context.</p>';
  return `<div class="evidence-media">${rows.map(media => `<figure><img src="${escapeHtml(media.path)}" alt="${escapeHtml(media.alt || media.research_purpose)}" loading="lazy" onerror="this.closest('figure').classList.add('missing')"><figcaption>${escapeHtml(media.attribution)}</figcaption></figure>`).join("")}</div>`;
}

function list(items = []) {
  return items.length ? `<ul>${items.map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : '<span class="fineprint">None recorded.</span>';
}

function renderOutreach() {
  const queue = state.outreach.queue;
  const queueHtml = queue.length ? `<table class="queue-table"><thead><tr><th>Priority</th><th>Seller</th><th>Exact ask</th><th>Status</th></tr></thead><tbody>${queue.map(item => `<tr><td>${escapeHtml(item.priority)}</td><td>${escapeHtml(state.maps.sellers.get(item.seller_id)?.display_name)}</td><td>${escapeHtml(item.question)}</td><td>${escapeHtml(label(item.status))}</td></tr>`).join("")}</tbody></table>` : '<p class="empty">No seller currently has both a public contact and a sufficiently specific target question.</p>';
  document.querySelector("#outreach-results").innerHTML = `${queueHtml}<div class="drafts">${state.outreach.drafts.map(item => `<article class="draft"><h3>${escapeHtml(item.title)}</h3><pre>${escapeHtml(item.body)}</pre></article>`).join("")}</div>`;
}

function bindControls() {
  document.querySelectorAll(".view-nav button").forEach(button => button.addEventListener("click", () => showView(button.dataset.view)));
  ["catalog-search", "size-filter", "color-filter", "status-filter", "catalog-sort"].forEach(id => document.querySelector(`#${id}`).addEventListener("input", renderCatalog));
  ["evidence-search", "source-filter", "match-filter"].forEach(id => document.querySelector(`#${id}`).addEventListener("input", renderEvidence));
  document.body.addEventListener("click", event => {
    const link = event.target.closest("[data-open-evidence]");
    if (!link) return;
    const ids = state.offerings.find(item => item.id === link.dataset.openEvidence)?.evidence_ids || [];
    document.querySelector("#evidence-search").value = ids.length === 1 ? ids[0] : "";
    showView("evidence");
  });
}

function showView(id) {
  document.querySelectorAll(".view").forEach(view => view.classList.toggle("active", view.id === id));
  document.querySelectorAll(".view-nav button").forEach(button => button.classList.toggle("active", button.dataset.view === id));
  history.replaceState(null, "", `#${id}`);
  document.querySelector("main").scrollIntoView({behavior: "smooth"});
}

async function init() {
  try {
    await loadData();
    fillSelect("#size-filter", state.bags.map(item => item.size));
    fillSelect("#color-filter", state.bags.map(item => item.colorway));
    fillSelect("#status-filter", state.offerings.map(item => item.status));
    fillSelect("#source-filter", state.evidence.map(item => item.source_type));
    renderSnapshot(); renderCatalog(); renderSellers(); renderEvidence(); renderOutreach(); bindControls();
    if (["catalog", "sellers", "evidence", "outreach"].includes(location.hash.slice(1))) showView(location.hash.slice(1));
  } catch (error) {
    document.querySelector("main").innerHTML = `<p class="empty">The catalog data could not load. ${escapeHtml(error.message)} Run this site through the local server rather than opening the file directly.</p>`;
  }
}

init();
