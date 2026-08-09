(function exposeUiLogic(root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.OGUiLogic = api;
}(typeof globalThis !== "undefined" ? globalThis : this, () => {
  const PLACEHOLDER_VALUE = /^(?:(?:unknown|none|n\/a|null|undefined|unavailable|undisclosed|tbd)(?:\b.*)?|still researching(?:\b.*)?|not (?:consistently )?(?:documented|stated|available|reported|specified|identified|confirmed)\b.*)$/i;

  function normalizeSearchText(value) {
    return String(value ?? "")
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/&/g, " and ")
      .replace(/[^a-z0-9]+/g, " ")
      .trim()
      .replace(/\s+/g, " ");
  }

  function meaningfulValue(value) {
    const normalized = String(value ?? "").trim();
    return Boolean(normalized) && !PLACEHOLDER_VALUE.test(normalized);
  }

  function flattenStrings(value) {
    if (Array.isArray(value)) return value.flatMap(flattenStrings);
    if (value && typeof value === "object") return Object.values(value).flatMap(flattenStrings);
    return meaningfulValue(value) ? [String(value)] : [];
  }

  function brandInitials(brand) {
    const words = normalizeSearchText(brand).split(" ").filter(Boolean);
    return words.length > 1 ? words.map(word => word[0]).join("") : "";
  }

  function buildEvidenceSearchDocument({ receipt, collection, variants = [], sellers = [], factories = [], sourceLabel = "", evidenceLabel = "" }) {
    const receiptFields = receipt ? [
      receipt.id, receipt.title, receipt.author, receipt.subreddit, receipt.paraphrase,
      receipt.positive_observations, receipt.negative_observations,
      receipt.source_type, receipt.evidence_type,
    ] : [];
    const collectionFields = collection ? [
      collection.brand, brandInitials(collection.brand), collection.model,
      collection.aliases, collection.category,
    ] : [];
    const variantFields = variants.flatMap(variant => [
      variant.name, variant.size, variant.pattern, variant.colorway,
      variant.material, variant.hardware,
    ]);
    const partyFields = [...sellers, ...factories].flatMap(party => [party.display_name, party.aliases]);
    const normalizedValues = flattenStrings([
      receiptFields, collectionFields, variantFields, partyFields, sourceLabel, evidenceLabel,
    ]).map(normalizeSearchText).filter(Boolean);
    const text = normalizedValues.join(" ");
    return { text, compact: text.replace(/\s+/g, "") };
  }

  function matchesEvidenceSearch(document, query) {
    const tokens = normalizeSearchText(query).split(" ").filter(Boolean);
    if (!tokens.length) return true;
    const text = typeof document === "string" ? normalizeSearchText(document) : document?.text || "";
    const compact = typeof document === "string" ? text.replace(/\s+/g, "") : document?.compact || text.replace(/\s+/g, "");
    return tokens.every(token => text.includes(token) || compact.includes(token.replace(/\s+/g, "")));
  }

  function restoreLockedScroll(environment, scrollPosition) {
    const { documentElement, body, scrollTo, requestAnimationFrame } = environment;
    documentElement.classList.add("scroll-restoring");
    body.classList.remove("dialog-open");
    if (body.style?.removeProperty) body.style.removeProperty("--dialog-scroll-offset");
    for (const property of ["position", "top", "right", "left", "width"])
      if (body.style) body.style[property] = "";
    scrollTo({ top: scrollPosition, behavior: "auto" });
    documentElement.classList.remove("dialog-open");
    requestAnimationFrame(() => documentElement.classList.remove("scroll-restoring"));
  }

  return {
    normalizeSearchText,
    meaningfulValue,
    buildEvidenceSearchDocument,
    matchesEvidenceSearch,
    restoreLockedScroll,
  };
}));
