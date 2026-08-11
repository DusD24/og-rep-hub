import assert from "node:assert/strict";
import test from "node:test";

let workerModule;
try {
  workerModule = await import("../src/index.js");
} catch {
  workerModule = null;
}

const RECEIPT = {
  id: "ev-hp-monogram-gm-comment",
  title: "HP Monogram Neverfull GM owner comment",
  url: "https://www.reddit.com/r/RealRepLadies/comments/current/source/",
  collection: "Louis Vuitton Neverfull",
  variants: ["Neverfull GM Monogram"],
};

const VALID_PAYLOAD = {
  receiptId: RECEIPT.id,
  requestType: "add_evidence",
  summary: "This public comparison adds a useful detail that should be attached to the normalized receipt.",
  evidenceUrls: ["https://www.reddit.com/r/RealRepLadies/comments/new/evidence/"],
  variantDetails: "Neverfull GM in brown Monogram.",
  sellerFactoryDetails: "Seller reported as Hyper Peter.",
  limitations: "The post is one owner's comparison.",
  publicDataAcknowledgement: true,
  website: "",
  turnstileToken: "turnstile-token",
};

function jsonResponse(value, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
}

function createHarness({ turnstile, github, rateLimit = true, collections } = {}) {
  const calls = [];
  const fetchImpl = async (input, init = {}) => {
    const url = String(input);
    calls.push({ url, init });
    if (url.includes("siteverify")) return jsonResponse(turnstile || { success: true, hostname: "dusd24.github.io", action: "receipt_update" });
    if (url.includes("api.github.com")) return github || jsonResponse({ number: 42, html_url: "https://github.com/DusD24/og-rep-hub/issues/42" }, 201);
    throw new Error(`Unexpected fetch: ${url}`);
  };
  const handler = workerModule.createWorker({
    canonicalReceipts: [RECEIPT],
    collectionIds: collections ? new Set(collections.map(item => item.id)) : undefined,
    fetchImpl,
  });
  const env = {
    ALLOWED_ORIGIN: "https://dusd24.github.io",
    ALLOWED_TURNSTILE_HOSTNAME: "dusd24.github.io",
    GITHUB_REPOSITORY: "DusD24/og-rep-hub",
    GITHUB_ISSUE_TOKEN: "github-token",
    TURNSTILE_SECRET_KEY: "turnstile-secret",
    BUILD_SHA: "abc123",
    SUBMISSION_RATE_LIMITER: { async limit() { return { success: rateLimit }; } },
  };
  return { handler, env, calls };
}

function submissionRequest(payload = VALID_PAYLOAD, origin = "https://dusd24.github.io", path = "/issues/receipt-update") {
  return new Request(`https://issues.example.test${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Origin: origin,
      "CF-Connecting-IP": "203.0.113.10",
    },
    body: JSON.stringify(payload),
  });
}

const VALID_SUGGEST_BAG_PAYLOAD = {
  brandModel: "Loewe Puzzle",
  publicUrl: "https://www.reddit.com/r/RepLadies/comments/new/puzzle-review/",
  sourceSummary: "This public review documents the exact size, hardware, and stitching of the Puzzle bag in detail.",
  publicDataAcknowledgement: true,
  website: "",
  turnstileToken: "turnstile-token",
};

const VALID_SUBMIT_SOURCE_PAYLOAD = {
  redditUrl: "https://www.reddit.com/r/RealRepLadies/comments/new/qc-post/",
  author: "u/example-author",
  subreddit: "r/RealRepLadies",
  publicationDate: "2026-08-01",
  evidenceDetails: "This QC post documents the exact variant, seller name, and hardware finish with clear photos.",
  publicDataAcknowledgement: true,
  website: "",
  turnstileToken: "turnstile-token",
};

const VALID_CORRECTION_PAYLOAD = {
  affectedUrl: "https://www.reddit.com/r/RealRepLadies/comments/current/source/",
  requestType: "correct_source",
  requestedChange: "The linked source misattributes this receipt to the wrong seller; the post credits a different seller entirely.",
  publicDataAcknowledgement: true,
  website: "",
  turnstileToken: "turnstile-token",
};

async function responseJson(response) {
  return { response, body: await response.json() };
}

test("Worker implementation is available", () => {
  assert.ok(workerModule, "worker/src/index.js must expose the tested Worker behavior");
});

test("canonical receipt index resolves collection and variant names", () => {
  if (!workerModule) return;
  const index = workerModule.buildCanonicalReceiptIndex({
    evidence: [{ id: "ev-1", title: "Receipt", url: "https://www.reddit.com/r/test/comments/1/post/", family_ids: ["collection-1"], bag_ids: ["bag-1"] }],
    collections: [{ id: "collection-1", brand: "Louis Vuitton", model: "Neverfull" }],
    bags: [{ id: "bag-1", name: "Neverfull GM Monogram" }],
  });
  assert.deepEqual(index, [{
    id: "ev-1",
    title: "Receipt",
    url: "https://www.reddit.com/r/test/comments/1/post/",
    collection: "Louis Vuitton Neverfull",
    variants: ["Neverfull GM Monogram"],
  }]);
});

test("valid submission creates a canonical public GitHub issue", async () => {
  if (!workerModule) return;
  const { handler, env, calls } = createHarness();
  const { response, body } = await responseJson(await handler.fetch(submissionRequest(), env));
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("Access-Control-Allow-Origin"), "https://dusd24.github.io");
  assert.equal(response.headers.get("Cache-Control"), "no-store");
  assert.deepEqual(body, { ok: true, issueNumber: 42, issueUrl: "https://github.com/DusD24/og-rep-hub/issues/42" });

  const turnstileCall = calls.find(call => call.url.includes("siteverify"));
  assert.deepEqual(JSON.parse(turnstileCall.init.body), {
    secret: "turnstile-secret",
    response: "turnstile-token",
    remoteip: "203.0.113.10",
  });
  const githubCall = calls.find(call => call.url.includes("api.github.com"));
  const issue = JSON.parse(githubCall.init.body);
  assert.equal(issue.title, "[Receipt update] ev-hp-monogram-gm-comment — Add supporting evidence");
  assert.deepEqual(issue.labels, ["receipt-update", "research"]);
  assert.match(issue.body, /Louis Vuitton Neverfull/);
  assert.match(issue.body, /Neverfull GM Monogram/);
  assert.match(issue.body, /https:\/\/www\.reddit\.com\/r\/RealRepLadies\/comments\/new\/evidence\//);
});

test("source and media review receives the source-review label", async () => {
  if (!workerModule) return;
  const { handler, env, calls } = createHarness();
  const payload = { ...VALID_PAYLOAD, requestType: "source_media_review" };
  const response = await handler.fetch(submissionRequest(payload), env);
  assert.equal(response.status, 200);
  const issue = JSON.parse(calls.find(call => call.url.includes("api.github.com")).init.body);
  assert.deepEqual(issue.labels, ["receipt-update", "research", "source-review"]);
});

test("submission validation rejects unsafe or incomplete evidence", async t => {
  if (!workerModule) return;
  const cases = [
    ["unknown receipt", { ...VALID_PAYLOAD, receiptId: "ev-missing" }, "invalid_receipt"],
    ["short summary", { ...VALID_PAYLOAD, summary: "Too short" }, "invalid_summary"],
    ["missing URLs", { ...VALID_PAYLOAD, evidenceUrls: [] }, "invalid_evidence_urls"],
    ["disallowed URL", { ...VALID_PAYLOAD, evidenceUrls: ["https://example.com/evidence"] }, "invalid_evidence_url"],
    ["spoofed Reddit host", { ...VALID_PAYLOAD, evidenceUrls: ["https://www.reddit.com.attacker.example/evidence"] }, "invalid_evidence_url"],
    ["current source URL", { ...VALID_PAYLOAD, evidenceUrls: [RECEIPT.url] }, "current_source_url"],
    ["current source alias", { ...VALID_PAYLOAD, evidenceUrls: ["https://old.reddit.com/r/RealRepLadies/comments/current/source/?utm_source=share"] }, "current_source_url"],
    ["unsupported request type", { ...VALID_PAYLOAD, requestType: "other" }, "invalid_request_type"],
    ["oversized optional field", { ...VALID_PAYLOAD, limitations: "x".repeat(2001) }, "invalid_optional_field"],
    ["missing acknowledgement", { ...VALID_PAYLOAD, publicDataAcknowledgement: false }, "acknowledgement_required"],
    ["honeypot", { ...VALID_PAYLOAD, website: "bot.example" }, "invalid_submission"],
  ];
  for (const [name, payload, code] of cases) await t.test(name, async () => {
    const { handler, env, calls } = createHarness();
    const { response, body } = await responseJson(await handler.fetch(submissionRequest(payload), env));
    assert.equal(response.status, 400);
    assert.equal(body.ok, false);
    assert.equal(body.code, code);
    assert.equal(calls.length, 0);
  });
});

test("duplicate allowed evidence URLs are normalized and deduplicated", async () => {
  if (!workerModule) return;
  const { handler, env, calls } = createHarness();
  const payload = { ...VALID_PAYLOAD, evidenceUrls: [
    "https://www.reddit.com/r/RealRepLadies/comments/new/evidence/#fragment",
    "https://old.reddit.com/r/RealRepLadies/comments/new/evidence/?utm_source=share",
  ] };
  const response = await handler.fetch(submissionRequest(payload), env);
  assert.equal(response.status, 200);
  const issue = JSON.parse(calls.find(call => call.url.includes("api.github.com")).init.body);
  assert.equal((issue.body.match(/comments\/new\/evidence\//g) || []).length, 1);
});

test("official Reddit media hosts are accepted", async t => {
  if (!workerModule) return;
  for (const host of ["v.redd.it", "external-preview.redd.it"]) await t.test(host, async () => {
    const { handler, env } = createHarness();
    const payload = { ...VALID_PAYLOAD, evidenceUrls: [`https://${host}/public-media-id`] };
    const response = await handler.fetch(submissionRequest(payload), env);
    assert.equal(response.status, 200);
  });
});

test("malformed requests and strict body limits return structured errors", async t => {
  if (!workerModule) return;
  const { handler, env } = createHarness();
  const baseHeaders = { Origin: env.ALLOWED_ORIGIN, "CF-Connecting-IP": "203.0.113.10" };
  const cases = [
    ["content type", new Request("https://issues.example.test/issues/receipt-update", {
      method: "POST", headers: { ...baseHeaders, "Content-Type": "text/plain" }, body: "{}",
    }), 415, "invalid_content_type"],
    ["invalid JSON", new Request("https://issues.example.test/issues/receipt-update", {
      method: "POST", headers: { ...baseHeaders, "Content-Type": "application/json" }, body: "{",
    }), 400, "invalid_json"],
    ["oversized body", new Request("https://issues.example.test/issues/receipt-update", {
      method: "POST", headers: { ...baseHeaders, "Content-Type": "application/json" }, body: `{"padding":"${"x".repeat(32_100)}"}`,
    }), 413, "payload_too_large"],
  ];
  for (const [name, request, status, code] of cases) await t.test(name, async () => {
    const result = await responseJson(await handler.fetch(request, env));
    assert.equal(result.response.status, status);
    assert.equal(result.body.code, code);
  });
});

test("oversized chunked bodies are rejected before the full stream is buffered", async () => {
  if (!workerModule) return;
  const { handler, env } = createHarness();
  const chunk = new TextEncoder().encode("x".repeat(1024));
  let pulls = 0;
  let cancelled = false;
  const body = new ReadableStream({
    pull(controller) {
      pulls += 1;
      if (pulls > 100) return controller.close();
      controller.enqueue(chunk);
    },
    cancel() { cancelled = true; },
  });
  const request = new Request("https://issues.example.test/issues/receipt-update", {
    method: "POST",
    headers: {
      Origin: env.ALLOWED_ORIGIN,
      "Content-Type": "application/json",
      "CF-Connecting-IP": "203.0.113.10",
    },
    body,
    duplex: "half",
  });

  const result = await responseJson(await handler.fetch(request, env));

  assert.equal(result.response.status, 413);
  assert.equal(result.body.code, "payload_too_large");
  assert.equal(cancelled, true);
  assert.ok(pulls < 100, `expected early rejection, read ${pulls} chunks`);
});

test("Turnstile hostname and action are enforced", async t => {
  if (!workerModule) return;
  for (const [name, turnstile] of [
    ["failed token", { success: false, "error-codes": ["invalid-input-response"] }],
    ["wrong hostname", { success: true, hostname: "attacker.example", action: "receipt_update" }],
    ["wrong action", { success: true, hostname: "dusd24.github.io", action: "other" }],
  ]) await t.test(name, async () => {
    const { handler, env } = createHarness({ turnstile });
    const { response, body } = await responseJson(await handler.fetch(submissionRequest(), env));
    assert.equal(response.status, 403);
    assert.equal(body.code, "verification_failed");
  });
});

test("rate limits, forbidden origins, and GitHub failures return structured errors", async t => {
  if (!workerModule) return;
  await t.test("rate limit", async () => {
    const { handler, env } = createHarness({ rateLimit: false });
    const { response, body } = await responseJson(await handler.fetch(submissionRequest(), env));
    assert.equal(response.status, 429);
    assert.equal(body.code, "rate_limited");
  });
  await t.test("forbidden origin", async () => {
    const { handler, env } = createHarness();
    const { response, body } = await responseJson(await handler.fetch(submissionRequest(VALID_PAYLOAD, "https://attacker.example"), env));
    assert.equal(response.status, 403);
    assert.equal(body.code, "origin_forbidden");
  });
  await t.test("GitHub failure", async () => {
    const { handler, env } = createHarness({ github: jsonResponse({ message: "Bad gateway" }, 503) });
    const { response, body } = await responseJson(await handler.fetch(submissionRequest(), env));
    assert.equal(response.status, 502);
    assert.equal(body.code, "github_error");
  });
});

test("bag suggestion creates a public GitHub issue with the right labels", async () => {
  if (!workerModule) return;
  const { handler, env, calls } = createHarness({ turnstile: { success: true, hostname: "dusd24.github.io", action: "suggest_bag" } });
  const request = submissionRequest(VALID_SUGGEST_BAG_PAYLOAD, "https://dusd24.github.io", "/issues/suggest-bag");
  const { response, body } = await responseJson(await handler.fetch(request, env));
  assert.equal(response.status, 200);
  assert.deepEqual(body, { ok: true, issueNumber: 42, issueUrl: "https://github.com/DusD24/og-rep-hub/issues/42" });
  const issue = JSON.parse(calls.find(call => call.url.includes("api.github.com")).init.body);
  assert.equal(issue.title, "[Bag suggestion] Loewe Puzzle");
  assert.deepEqual(issue.labels, ["research", "bag-collection"]);
  assert.match(issue.body, /Loewe Puzzle/);
});

test("bag suggestion validation rejects unsafe or incomplete submissions", async t => {
  if (!workerModule) return;
  const cases = [
    ["missing brand/model", { ...VALID_SUGGEST_BAG_PAYLOAD, brandModel: "" }, "invalid_brand_model"],
    ["disallowed URL host", { ...VALID_SUGGEST_BAG_PAYLOAD, publicUrl: "https://example.com/post" }, "invalid_public_url"],
    ["short summary", { ...VALID_SUGGEST_BAG_PAYLOAD, sourceSummary: "Too short" }, "invalid_source_summary"],
    ["missing acknowledgement", { ...VALID_SUGGEST_BAG_PAYLOAD, publicDataAcknowledgement: false }, "acknowledgement_required"],
    ["honeypot", { ...VALID_SUGGEST_BAG_PAYLOAD, website: "bot.example" }, "invalid_submission"],
  ];
  for (const [name, payload, code] of cases) await t.test(name, async () => {
    const { handler, env, calls } = createHarness();
    const { response, body } = await responseJson(await handler.fetch(submissionRequest(payload, "https://dusd24.github.io", "/issues/suggest-bag"), env));
    assert.equal(response.status, 400);
    assert.equal(body.code, code);
    assert.equal(calls.length, 0);
  });
});

test("Reddit source submission creates a public GitHub issue with the right labels", async () => {
  if (!workerModule) return;
  const { handler, env, calls } = createHarness({ turnstile: { success: true, hostname: "dusd24.github.io", action: "submit_source" } });
  const request = submissionRequest(VALID_SUBMIT_SOURCE_PAYLOAD, "https://dusd24.github.io", "/issues/submit-source");
  const { response, body } = await responseJson(await handler.fetch(request, env));
  assert.equal(response.status, 200);
  assert.deepEqual(body, { ok: true, issueNumber: 42, issueUrl: "https://github.com/DusD24/og-rep-hub/issues/42" });
  const issue = JSON.parse(calls.find(call => call.url.includes("api.github.com")).init.body);
  assert.equal(issue.title, "[Reddit source] u/example-author on r/RealRepLadies");
  assert.deepEqual(issue.labels, ["research", "source-review"]);
  assert.match(issue.body, /RealRepLadies/);
});

test("Reddit source validation rejects unsafe or incomplete submissions", async t => {
  if (!workerModule) return;
  const cases = [
    ["imgur host rejected", { ...VALID_SUBMIT_SOURCE_PAYLOAD, redditUrl: "https://imgur.com/abc123" }, "invalid_reddit_url"],
    ["disallowed URL host", { ...VALID_SUBMIT_SOURCE_PAYLOAD, redditUrl: "https://example.com/post" }, "invalid_reddit_url"],
    ["missing author", { ...VALID_SUBMIT_SOURCE_PAYLOAD, author: "" }, "invalid_author"],
    ["missing subreddit", { ...VALID_SUBMIT_SOURCE_PAYLOAD, subreddit: "" }, "invalid_subreddit"],
    ["missing publication date", { ...VALID_SUBMIT_SOURCE_PAYLOAD, publicationDate: "" }, "invalid_publication_date"],
    ["short evidence details", { ...VALID_SUBMIT_SOURCE_PAYLOAD, evidenceDetails: "Too short" }, "invalid_evidence_details"],
  ];
  for (const [name, payload, code] of cases) await t.test(name, async () => {
    const { handler, env, calls } = createHarness();
    const { response, body } = await responseJson(await handler.fetch(submissionRequest(payload, "https://dusd24.github.io", "/issues/submit-source"), env));
    assert.equal(response.status, 400);
    assert.equal(body.code, code);
    assert.equal(calls.length, 0);
  });
});

test("correction/media-removal creates a public GitHub issue with the right labels", async () => {
  if (!workerModule) return;
  const { handler, env, calls } = createHarness({ turnstile: { success: true, hostname: "dusd24.github.io", action: "correction_media_removal" } });
  const request = submissionRequest(VALID_CORRECTION_PAYLOAD, "https://dusd24.github.io", "/issues/correction-media-removal");
  const { response, body } = await responseJson(await handler.fetch(request, env));
  assert.equal(response.status, 200);
  assert.deepEqual(body, { ok: true, issueNumber: 42, issueUrl: "https://github.com/DusD24/og-rep-hub/issues/42" });
  const issue = JSON.parse(calls.find(call => call.url.includes("api.github.com")).init.body);
  assert.equal(issue.title, "[Correction or media] Correct a source or attribution");
  assert.deepEqual(issue.labels, ["triage", "source-review"]);
});

test("correction/media-removal accepts a valid internal collection route", async () => {
  if (!workerModule) return;
  const { handler, env, calls } = createHarness({
    collections: [{ id: "collection-1" }],
    turnstile: { success: true, hostname: "dusd24.github.io", action: "correction_media_removal" },
  });
  const payload = { ...VALID_CORRECTION_PAYLOAD, affectedUrl: "#bag/collection-1" };
  const request = submissionRequest(payload, "https://dusd24.github.io", "/issues/correction-media-removal");
  const { response } = await responseJson(await handler.fetch(request, env));
  assert.equal(response.status, 200);
  const issue = JSON.parse(calls.find(call => call.url.includes("api.github.com")).init.body);
  assert.match(issue.body, /#bag\/collection-1/);
});

test("correction/media-removal validation rejects unsafe or incomplete submissions", async t => {
  if (!workerModule) return;
  const cases = [
    ["disallowed URL host", { ...VALID_CORRECTION_PAYLOAD, affectedUrl: "https://example.com/post" }, "invalid_affected_url"],
    ["unknown collection route", { ...VALID_CORRECTION_PAYLOAD, affectedUrl: "#bag/unknown-collection" }, "invalid_affected_url"],
    ["unsupported request type", { ...VALID_CORRECTION_PAYLOAD, requestType: "other" }, "invalid_request_type"],
    ["short requested change", { ...VALID_CORRECTION_PAYLOAD, requestedChange: "Too short" }, "invalid_requested_change"],
    ["missing acknowledgement", { ...VALID_CORRECTION_PAYLOAD, publicDataAcknowledgement: false }, "acknowledgement_required"],
  ];
  for (const [name, payload, code] of cases) await t.test(name, async () => {
    const { handler, env, calls } = createHarness();
    const { response, body } = await responseJson(await handler.fetch(submissionRequest(payload, "https://dusd24.github.io", "/issues/correction-media-removal"), env));
    assert.equal(response.status, 400);
    assert.equal(body.code, code);
    assert.equal(calls.length, 0);
  });
});

test("unknown submission routes return not_found", async () => {
  if (!workerModule) return;
  const { handler, env } = createHarness();
  const request = submissionRequest(VALID_PAYLOAD, "https://dusd24.github.io", "/issues/unknown-type");
  const { response, body } = await responseJson(await handler.fetch(request, env));
  assert.equal(response.status, 404);
  assert.equal(body.code, "not_found");
});

test("health and preflight expose only the production origin", async () => {
  if (!workerModule) return;
  const { handler, env } = createHarness();
  const health = await responseJson(await handler.fetch(new Request("https://issues.example.test/health", { headers: { Origin: env.ALLOWED_ORIGIN } }), env));
  assert.equal(health.response.status, 200);
  assert.deepEqual(health.body, { ok: true, buildSha: "abc123" });
  const options = await handler.fetch(new Request("https://issues.example.test/issues/receipt-update", { method: "OPTIONS", headers: { Origin: env.ALLOWED_ORIGIN } }), env);
  assert.equal(options.status, 204);
  assert.equal(options.headers.get("Access-Control-Allow-Origin"), env.ALLOWED_ORIGIN);
});
