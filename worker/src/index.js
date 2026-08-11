import evidence from "../../data/evidence.json" with { type: "json" };
import collections from "../../data/bag_families.json" with { type: "json" };
import bags from "../../data/bags.json" with { type: "json" };

const REQUEST_TYPES = {
  add_evidence: "Add supporting evidence",
  correct_facts: "Correct normalized facts",
  challenge_interpretation: "Challenge the interpretation",
  source_media_review: "Review or remove a source/image",
};
const CORRECTION_REQUEST_TYPES = {
  correct_source: "Correct a source or attribution",
  remove_media: "Remove or replace media",
  correct_reference: "Correct a variant, seller, or factory reference",
  broken_link: "Report a broken public link",
};
const EVIDENCE_HOSTS = new Set([
  "reddit.com", "www.reddit.com", "old.reddit.com", "new.reddit.com", "np.reddit.com", "redd.it",
  "i.redd.it", "v.redd.it", "preview.redd.it", "external-preview.redd.it", "packaged-media.redd.it",
  "redditmedia.com", "www.redditmedia.com",
  "imgur.com", "www.imgur.com", "i.imgur.com",
]);
const REDDIT_PAGE_HOSTS = new Set(["reddit.com", "www.reddit.com", "old.reddit.com", "new.reddit.com", "np.reddit.com"]);
const REDDIT_ONLY_HOSTS = new Set([...EVIDENCE_HOSTS].filter(host => !host.includes("imgur")));
const TRACKING_PARAMETERS = new Set(["share_id", "rdt", "ref", "ref_source"]);
const MAX_BODY_BYTES = 32_000;
const BAG_ROUTE_PATTERN = /^#?bag\/([\w-]+)$/;

export function buildCanonicalReceiptIndex({ evidence: evidenceRows, collections: collectionRows, bags: bagRows }) {
  const collectionById = new Map(collectionRows.map(item => [item.id, item]));
  const bagById = new Map(bagRows.map(item => [item.id, item]));
  return evidenceRows.map(item => {
    const variants = (item.bag_ids || []).map(id => bagById.get(id)).filter(Boolean);
    const collectionId = item.family_ids?.[0] || variants[0]?.family_id;
    const collection = collectionById.get(collectionId);
    return {
      id: item.id,
      title: item.title || "Community receipt",
      url: item.url,
      collection: collection ? `${collection.brand} ${collection.model}` : "Collection unavailable",
      variants: variants.map(variant => variant.name),
    };
  });
}

const canonicalReceipts = buildCanonicalReceiptIndex({ evidence, collections, bags });
const defaultCollectionIds = new Set(collections.map(item => item.id));

function corsOrigin(request, env) {
  const origin = request.headers.get("Origin") || "";
  return origin && origin === env.ALLOWED_ORIGIN ? origin : "";
}

function responseHeaders(origin = "") {
  const headers = new Headers({
    "Cache-Control": "no-store",
    "Content-Type": "application/json; charset=utf-8",
    "Vary": "Origin",
  });
  if (origin) headers.set("Access-Control-Allow-Origin", origin);
  return headers;
}

function json(value, status, origin = "") {
  return new Response(JSON.stringify(value), { status, headers: responseHeaders(origin) });
}

function failure(code, message, status, origin = "") {
  return json({ ok: false, code, message }, status, origin);
}

function normalizeEvidenceUrl(value, allowedHosts = EVIDENCE_HOSTS) {
  if (typeof value !== "string" || !value.trim() || value.length > 2048) return null;
  try {
    const url = new URL(value.trim());
    if (url.protocol !== "https:" || url.username || url.password || !allowedHosts.has(url.hostname.toLowerCase())) return null;
    const hostname = url.hostname.toLowerCase();
    if (REDDIT_PAGE_HOSTS.has(hostname)) url.hostname = "www.reddit.com";
    else if (hostname === "www.imgur.com") url.hostname = "imgur.com";
    url.hash = "";
    for (const key of [...url.searchParams.keys()])
      if (key.toLowerCase().startsWith("utm_") || TRACKING_PARAMETERS.has(key.toLowerCase())) url.searchParams.delete(key);
    url.searchParams.sort();
    return url.toString();
  } catch {
    return null;
  }
}

function normalizedComparisonUrl(value) {
  const normalized = normalizeEvidenceUrl(value);
  if (!normalized) return "";
  const url = new URL(normalized);
  url.search = "";
  url.pathname = url.pathname.replace(/\/+$/, "") || "/";
  return url.toString();
}

function validOptionalText(value) {
  return value === undefined || (typeof value === "string" && value.length <= 2000);
}

async function readBoundedBody(request, maxBytes) {
  const declaredLength = Number(request.headers.get("Content-Length"));
  if (Number.isFinite(declaredLength) && declaredLength > maxBytes) return null;
  if (!request.body) return "";

  const reader = request.body.getReader();
  const decoder = new TextDecoder();
  let totalBytes = 0;
  let text = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) return text + decoder.decode();
    totalBytes += value.byteLength;
    if (totalBytes > maxBytes) {
      try { await reader.cancel(); }
      catch { /* The size limit still applies if cancellation races stream completion. */ }
      return null;
    }
    text += decoder.decode(value, { stream: true });
  }
}

function requiredText(value, min, max) {
  return typeof value === "string" && value.trim().length >= min && value.trim().length <= max;
}

function validateReceiptUpdate(payload, receiptById) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return { error: ["invalid_payload", "Submit a JSON object."] };
  if (typeof payload.website !== "string" || payload.website) return { error: ["invalid_submission", "The submission could not be accepted."] };
  const receipt = receiptById.get(payload.receiptId);
  if (!receipt) return { error: ["invalid_receipt", "That receipt is not in the current public index."] };
  if (!Object.hasOwn(REQUEST_TYPES, payload.requestType)) return { error: ["invalid_request_type", "Choose a supported request type."] };
  if (typeof payload.summary !== "string" || payload.summary.trim().length < 40 || payload.summary.trim().length > 4000)
    return { error: ["invalid_summary", "The requested change must be 40–4,000 characters."] };
  if (!Array.isArray(payload.evidenceUrls) || payload.evidenceUrls.length < 1 || payload.evidenceUrls.length > 5)
    return { error: ["invalid_evidence_urls", "Provide 1–5 new public evidence URLs."] };
  const normalizedUrls = [];
  for (const value of payload.evidenceUrls) {
    const normalized = normalizeEvidenceUrl(value);
    if (!normalized) return { error: ["invalid_evidence_url", "Evidence URLs must be HTTPS Reddit or Imgur links."] };
    if (normalizedComparisonUrl(normalized) === normalizedComparisonUrl(receipt.url))
      return { error: ["current_source_url", "Provide new evidence rather than the receipt's current source."] };
    if (!normalizedUrls.some(existing => normalizedComparisonUrl(existing) === normalizedComparisonUrl(normalized))) normalizedUrls.push(normalized);
  }
  if (!validOptionalText(payload.variantDetails) || !validOptionalText(payload.sellerFactoryDetails) || !validOptionalText(payload.limitations))
    return { error: ["invalid_optional_field", "Optional detail fields may contain at most 2,000 characters."] };
  if (payload.publicDataAcknowledgement !== true)
    return { error: ["acknowledgement_required", "Confirm that the issue will be public and contains no private information."] };
  if (typeof payload.turnstileToken !== "string" || !payload.turnstileToken || payload.turnstileToken.length > 2048)
    return { error: ["verification_required", "Complete the verification challenge."] };
  return {
    value: {
      receipt,
      requestType: payload.requestType,
      summary: payload.summary.trim(),
      evidenceUrls: normalizedUrls,
      variantDetails: String(payload.variantDetails || "").trim(),
      sellerFactoryDetails: String(payload.sellerFactoryDetails || "").trim(),
      limitations: String(payload.limitations || "").trim(),
      turnstileToken: payload.turnstileToken,
    },
  };
}

function quote(value, fallback = "Not provided.") {
  const text = String(value || "").trim();
  if (!text) return fallback;
  return text.split(/\r?\n/).map(line => `> ${line || " "}`).join("\n");
}

function buildReceiptUpdateIssue(validated) {
  const typeLabel = REQUEST_TYPES[validated.requestType];
  const labels = ["receipt-update", "research"];
  if (validated.requestType === "source_media_review") labels.push("source-review");
  const body = [
    "## Linked receipt",
    `- Receipt ID: \`${validated.receipt.id}\``,
    `- Title: ${validated.receipt.title}`,
    `- Collection: ${validated.receipt.collection}`,
    `- Exact variant(s): ${validated.receipt.variants.join("; ") || "Not recorded"}`,
    `- Current public source: <${validated.receipt.url}>`,
    "",
    "## Requested change",
    `- Type: ${typeLabel}`,
    "",
    quote(validated.summary),
    "",
    "## New public evidence",
    ...validated.evidenceUrls.map(url => `- <${url}>`),
    "",
    "## Variant details",
    quote(validated.variantDetails),
    "",
    "## Seller or factory details as reported",
    quote(validated.sellerFactoryDetails),
    "",
    "## Contradictions or limitations",
    quote(validated.limitations),
    "",
    "## Public-data acknowledgement",
    "The submitter confirmed that this request is public and contains no private or identifying information.",
    "",
    "_Submitted through the OG Rep Hub receipt-update form. All claims require human review against the linked public sources._",
  ].join("\n");
  return {
    title: `[Receipt update] ${validated.receipt.id} — ${typeLabel}`,
    body,
    labels,
  };
}

function validateSuggestBag(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return { error: ["invalid_payload", "Submit a JSON object."] };
  if (typeof payload.website !== "string" || payload.website) return { error: ["invalid_submission", "The submission could not be accepted."] };
  if (!requiredText(payload.brandModel, 1, 200)) return { error: ["invalid_brand_model", "Provide the brand and model, up to 200 characters."] };
  const publicUrl = normalizeEvidenceUrl(payload.publicUrl);
  if (!publicUrl) return { error: ["invalid_public_url", "The public source URL must be an HTTPS Reddit or Imgur link."] };
  if (!requiredText(payload.sourceSummary, 40, 4000))
    return { error: ["invalid_source_summary", "Describe what the source documents in 40–4,000 characters."] };
  if (payload.publicDataAcknowledgement !== true)
    return { error: ["acknowledgement_required", "Confirm that the issue will be public and contains no private information."] };
  if (typeof payload.turnstileToken !== "string" || !payload.turnstileToken || payload.turnstileToken.length > 2048)
    return { error: ["verification_required", "Complete the verification challenge."] };
  return {
    value: {
      brandModel: payload.brandModel.trim(),
      publicUrl,
      sourceSummary: payload.sourceSummary.trim(),
      turnstileToken: payload.turnstileToken,
    },
  };
}

function buildSuggestBagIssue(validated) {
  const body = [
    "## Suggested collection",
    `- Brand and model: ${validated.brandModel}`,
    "",
    "## Public source",
    `<${validated.publicUrl}>`,
    "",
    "## What does the source document?",
    quote(validated.sourceSummary),
    "",
    "## Public-data acknowledgement",
    "The submitter confirmed that this request is public and contains no private or identifying information.",
    "",
    "_Submitted through the OG Rep Hub bag-suggestion form. A suggestion is not a site-level conclusion about a seller, factory, authenticity, or outcome._",
  ].join("\n");
  return { title: `[Bag suggestion] ${validated.brandModel}`, body, labels: ["research", "bag-collection"] };
}

function validateSubmitSource(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return { error: ["invalid_payload", "Submit a JSON object."] };
  if (typeof payload.website !== "string" || payload.website) return { error: ["invalid_submission", "The submission could not be accepted."] };
  const redditUrl = normalizeEvidenceUrl(payload.redditUrl, REDDIT_ONLY_HOSTS);
  if (!redditUrl) return { error: ["invalid_reddit_url", "The Reddit post URL must be a public HTTPS reddit.com or redd.it link."] };
  if (!requiredText(payload.author, 1, 100)) return { error: ["invalid_author", "Provide the Reddit author, up to 100 characters."] };
  if (!requiredText(payload.subreddit, 1, 100)) return { error: ["invalid_subreddit", "Provide the subreddit, up to 100 characters."] };
  if (!requiredText(payload.publicationDate, 1, 100))
    return { error: ["invalid_publication_date", "Provide the publication date, up to 100 characters."] };
  if (!requiredText(payload.evidenceDetails, 40, 4000))
    return { error: ["invalid_evidence_details", "Describe the evidence in 40–4,000 characters."] };
  if (payload.publicDataAcknowledgement !== true)
    return { error: ["acknowledgement_required", "Confirm that the issue will be public and contains no private information."] };
  if (typeof payload.turnstileToken !== "string" || !payload.turnstileToken || payload.turnstileToken.length > 2048)
    return { error: ["verification_required", "Complete the verification challenge."] };
  return {
    value: {
      redditUrl,
      author: payload.author.trim().replace(/^u\//i, ""),
      subreddit: payload.subreddit.trim().replace(/^r\//i, ""),
      publicationDate: payload.publicationDate.trim(),
      evidenceDetails: payload.evidenceDetails.trim(),
      turnstileToken: payload.turnstileToken,
    },
  };
}

function buildSubmitSourceIssue(validated) {
  const body = [
    "## Reddit post",
    `<${validated.redditUrl}>`,
    "",
    "## Reddit author",
    `u/${validated.author}`,
    "",
    "## Subreddit",
    `r/${validated.subreddit}`,
    "",
    "## Publication date",
    validated.publicationDate,
    "",
    "## Evidence details",
    quote(validated.evidenceDetails),
    "",
    "## Public-data acknowledgement",
    "The submitter confirmed that this request is public and contains no private or identifying information.",
    "",
    "_Submitted through the OG Rep Hub source-submission form. Source adjectives and seller/factory mentions remain attributed to the post._",
  ].join("\n");
  return { title: `[Reddit source] u/${validated.author} on r/${validated.subreddit}`, body, labels: ["research", "source-review"] };
}

function validateAffectedUrl(value, collectionIds) {
  const routeMatch = typeof value === "string" ? value.trim().match(BAG_ROUTE_PATTERN) : null;
  if (routeMatch) {
    let familyId = routeMatch[1];
    try { familyId = decodeURIComponent(familyId); } catch { /* Use the raw segment if it is not percent-encoded. */ }
    return collectionIds.has(familyId) ? `#bag/${familyId}` : null;
  }
  return normalizeEvidenceUrl(value);
}

function validateCorrectionMediaRemoval(payload, collectionIds) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return { error: ["invalid_payload", "Submit a JSON object."] };
  if (typeof payload.website !== "string" || payload.website) return { error: ["invalid_submission", "The submission could not be accepted."] };
  const affectedUrl = validateAffectedUrl(payload.affectedUrl, collectionIds);
  if (!affectedUrl)
    return { error: ["invalid_affected_url", "Provide a public HTTPS Reddit or Imgur link, or a #bag/... collection route."] };
  if (!Object.hasOwn(CORRECTION_REQUEST_TYPES, payload.requestType)) return { error: ["invalid_request_type", "Choose a supported request type."] };
  if (!requiredText(payload.requestedChange, 40, 4000))
    return { error: ["invalid_requested_change", "Describe the requested change in 40–4,000 characters."] };
  if (payload.publicDataAcknowledgement !== true)
    return { error: ["acknowledgement_required", "Confirm that the issue will be public and contains no private information."] };
  if (typeof payload.turnstileToken !== "string" || !payload.turnstileToken || payload.turnstileToken.length > 2048)
    return { error: ["verification_required", "Complete the verification challenge."] };
  return {
    value: {
      affectedUrl,
      requestType: payload.requestType,
      requestedChange: payload.requestedChange.trim(),
      turnstileToken: payload.turnstileToken,
    },
  };
}

function buildCorrectionMediaRemovalIssue(validated) {
  const typeLabel = CORRECTION_REQUEST_TYPES[validated.requestType];
  const body = [
    "## Affected URL or collection route",
    validated.affectedUrl.startsWith("#") ? validated.affectedUrl : `<${validated.affectedUrl}>`,
    "",
    "## Requested change",
    `- Type: ${typeLabel}`,
    "",
    quote(validated.requestedChange),
    "",
    "## Public-data acknowledgement",
    "The submitter confirmed that this request is public and contains no private or identifying information.",
    "",
    "_Submitted through the OG Rep Hub correction and media-removal form._",
  ].join("\n");
  return { title: `[Correction or media] ${typeLabel}`, body, labels: ["triage", "source-review"] };
}

async function verifyTurnstile(validated, request, env, fetchImpl, expectedAction) {
  const response = await fetchImpl("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      secret: env.TURNSTILE_SECRET_KEY,
      response: validated.turnstileToken,
      remoteip: request.headers.get("CF-Connecting-IP") || "",
    }),
  });
  if (!response.ok) return false;
  const result = await response.json().catch(() => null);
  return Boolean(result?.success && result.hostname === env.ALLOWED_TURNSTILE_HOSTNAME && result.action === expectedAction);
}

async function createGithubIssue(issue, env, fetchImpl) {
  if (!/^[-\w.]+\/[-\w.]+$/.test(env.GITHUB_REPOSITORY || "")) return null;
  const response = await fetchImpl(`https://api.github.com/repos/${env.GITHUB_REPOSITORY}/issues`, {
    method: "POST",
    headers: {
      "Accept": "application/vnd.github+json",
      "Authorization": `Bearer ${env.GITHUB_ISSUE_TOKEN}`,
      "Content-Type": "application/json",
      "User-Agent": "og-rep-hub-issue-intake",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    body: JSON.stringify(issue),
  });
  if (!response.ok) return null;
  const result = await response.json().catch(() => null);
  return Number.isInteger(result?.number) && typeof result?.html_url === "string" ? result : null;
}

export function createWorker({
  canonicalReceipts: receiptRows = canonicalReceipts,
  collectionIds: collectionIdRows = defaultCollectionIds,
  fetchImpl = fetch,
} = {}) {
  const receiptById = new Map(receiptRows.map(item => [item.id, item]));
  const routes = {
    "receipt-update": {
      turnstileAction: "receipt_update",
      validate: payload => validateReceiptUpdate(payload, receiptById),
      buildIssue: buildReceiptUpdateIssue,
    },
    "suggest-bag": {
      turnstileAction: "suggest_bag",
      validate: validateSuggestBag,
      buildIssue: buildSuggestBagIssue,
    },
    "submit-source": {
      turnstileAction: "submit_source",
      validate: validateSubmitSource,
      buildIssue: buildSubmitSourceIssue,
    },
    "correction-media-removal": {
      turnstileAction: "correction_media_removal",
      validate: payload => validateCorrectionMediaRemoval(payload, collectionIdRows),
      buildIssue: buildCorrectionMediaRemovalIssue,
    },
  };
  return {
    async fetch(request, env) {
      const url = new URL(request.url);
      const origin = corsOrigin(request, env);

      if (url.pathname === "/health" && request.method === "GET")
        return json({ ok: true, buildSha: env.BUILD_SHA || "unknown" }, 200, origin);

      const routeMatch = url.pathname.match(/^\/issues\/([\w-]+)$/);
      const routeName = routeMatch?.[1];
      const route = routeName ? routes[routeName] : undefined;
      if (!route) return failure("not_found", "Route not found.", 404, origin);

      if (request.method === "OPTIONS") {
        if (!origin) return failure("origin_forbidden", "This origin cannot submit this request.", 403);
        const headers = responseHeaders(origin);
        headers.set("Access-Control-Allow-Methods", "POST, OPTIONS");
        headers.set("Access-Control-Allow-Headers", "Content-Type");
        headers.set("Access-Control-Max-Age", "86400");
        headers.delete("Content-Type");
        return new Response(null, { status: 204, headers });
      }
      if (request.method !== "POST") return failure("method_not_allowed", "Use POST for this route.", 405, origin);
      if (!origin) return failure("origin_forbidden", "This origin cannot submit this request.", 403);
      if (!request.headers.get("Content-Type")?.toLowerCase().startsWith("application/json"))
        return failure("invalid_content_type", "Submit JSON with the application/json content type.", 415, origin);

      const rawBody = await readBoundedBody(request, MAX_BODY_BYTES);
      if (rawBody === null)
        return failure("payload_too_large", "The submission is too large.", 413, origin);
      let payload;
      try { payload = JSON.parse(rawBody); }
      catch { return failure("invalid_json", "The submission is not valid JSON.", 400, origin); }

      const validation = route.validate(payload);
      if (validation.error) return failure(validation.error[0], validation.error[1], 400, origin);
      if (!env.SUBMISSION_RATE_LIMITER?.limit || !env.TURNSTILE_SECRET_KEY || !env.GITHUB_ISSUE_TOKEN)
        return failure("service_unavailable", "The submission service is not fully configured.", 503, origin);

      const rateKey = `${request.headers.get("CF-Connecting-IP") || "unknown"}:${routeName}`;
      const rate = await env.SUBMISSION_RATE_LIMITER.limit({ key: rateKey });
      if (!rate.success) return failure("rate_limited", "Too many requests were submitted. Try again in a minute.", 429, origin);

      let verified = false;
      try { verified = await verifyTurnstile(validation.value, request, env, fetchImpl, route.turnstileAction); }
      catch { verified = false; }
      if (!verified) return failure("verification_failed", "Verification failed or expired. Complete it again.", 403, origin);

      let issue;
      try { issue = await createGithubIssue(route.buildIssue(validation.value), env, fetchImpl); }
      catch { issue = null; }
      if (!issue) return failure("github_error", "GitHub could not create the request. Try again later.", 502, origin);
      return json({ ok: true, issueNumber: issue.number, issueUrl: issue.html_url }, 200, origin);
    },
  };
}

const productionWorker = createWorker();
export default productionWorker;
