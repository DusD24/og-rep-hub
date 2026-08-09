const assert = require("node:assert/strict");
const test = require("node:test");

let uiLogic;
try {
  uiLogic = require("../assets/ui-logic.js");
} catch (error) {
  uiLogic = null;
}

test("browser-independent UI behavior helpers are available", () => {
  assert.ok(uiLogic, "assets/ui-logic.js must expose the tested UI behavior");
});

test("receipt search joins relational aliases and requires every query token", () => {
  if (!uiLogic) return;
  const document = uiLogic.buildEvidenceSearchDocument({
    receipt: {
      id: "ev-hp-monogram-gm-comment",
      title: "HP Monogram Neverfull GM owner comment",
      author: "Winter-Pace9581",
      subreddit: "RealRepLadies",
      paraphrase: "The owner compared an authentic bag with the replica.",
      positive_observations: ["The two bags were difficult to distinguish."],
      negative_observations: [],
      source_type: "reddit_discussion",
      evidence_type: "auth_comparison",
    },
    collection: {
      brand: "Louis Vuitton",
      model: "Neverfull",
      aliases: ["NF"],
      category: "tote",
    },
    variants: [{
      name: "Neverfull GM Monogram",
      size: "GM",
      pattern: "Monogram",
      colorway: "Brown",
      material: "Coated canvas",
      hardware: "Gold-tone",
    }],
    sellers: [{ display_name: "Hyper Peter (HP)", aliases: ["HP", "HyperPeter", "Booker"] }],
    factories: [],
    sourceLabel: "Reddit discussion",
    evidenceLabel: "Authentic comparison",
  });

  assert.equal(uiLogic.matchesEvidenceSearch(document, "authentic lv neverfull hyperpeter"), true);
  assert.equal(uiLogic.matchesEvidenceSearch(document, "authentic lv neverfull gucci"), false);
});

test("meaningful filter values reject null-style placeholders", () => {
  if (!uiLogic) return;
  for (const value of [
    null,
    "",
    "unknown",
    "Unknown / undisclosed",
    "Unavailable",
    "Not stated in source",
    "not stated in selected sources",
    "not consistently stated in selected sources",
    "not documented in current public sources",
    "not documented yet",
  ])
    assert.equal(uiLogic.meaningfulValue(value), false, String(value));
  assert.equal(uiLogic.meaningfulValue("Coated canvas"), true);
});

test("dialog scroll restoration disables smooth scrolling until the next frame", () => {
  if (!uiLogic) return;
  const calls = [];
  const htmlClasses = new Set();
  const bodyClasses = new Set(["dialog-open"]);
  let nextFrame;
  const classList = (set, owner) => ({
    add(value) { set.add(value); calls.push(`${owner}:add:${value}`); },
    remove(value) { set.delete(value); calls.push(`${owner}:remove:${value}`); },
  });
  const bodyStyle = { position: "fixed", top: "-875px", left: "0", right: "0", width: "100%" };

  uiLogic.restoreLockedScroll({
    documentElement: { classList: classList(htmlClasses, "html") },
    body: { classList: classList(bodyClasses, "body"), style: bodyStyle },
    scrollTo(options) { calls.push(`scroll:${options.top}:${options.behavior}`); },
    requestAnimationFrame(callback) { nextFrame = callback; },
  }, 875);

  assert.deepEqual(calls.slice(0, 4), [
    "html:add:scroll-restoring",
    "body:remove:dialog-open",
    "scroll:875:auto",
    "html:remove:dialog-open",
  ]);
  assert.equal(htmlClasses.has("scroll-restoring"), true);
  assert.equal(bodyStyle.position, "");
  assert.equal(bodyStyle.top, "");
  nextFrame();
  assert.equal(htmlClasses.has("scroll-restoring"), false);
});
