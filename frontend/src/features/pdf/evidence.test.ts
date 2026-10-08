import { describe, expect, it } from "vitest";
import {
  buildIndex,
  locateEvidence,
  normalizeMapped,
  normalizeText,
  type HighlightFinding,
} from "./evidence";

const finding = (quote: string): HighlightFinding => ({
  id: "rule:1",
  quote,
  title: "Evidence",
  source: "rule",
  score: 3,
});
const page = (str: string, hasEOL = false) => [{ str, hasEOL }];
describe("Exact PDF evidence mapping", () => {
  it.each([
    [" „Miete“\n\t1.500,00 EUR ", '"Miete" 1.500,00 EUR'],
    ["‚Straße‘ und Über-\n wachung", "'Straße' und Überwachung"],
    ["ﬁnancial ＲＥＮＴ", "financial RENT"],
    ["Gru\u0308ße\u0085ab\u001cCD", "Grüße ab CD"],
    ["keep-hyphen and no-  break", "keep-hyphen and no- break"],
  ])(
    "normalizes %s without lowering case or changing German characters",
    (raw, expected) => {
      expect(normalizeText(raw)).toBe(expected);
      expect(normalizeMapped(raw).origins.length).toBe(expected.length);
    },
  );
  it("maps ligatures back to the original character", () => {
    const matches = locateEvidence(buildIndex([page("A ﬁnancial duty.")]), [
      finding("financial"),
    ]);
    expect(matches[0]!.spans).toEqual([
      { page: 1, item: 0, start: 2, end: 10 },
    ]);
  });
  it("finds every exact occurrence and preserves case", () => {
    const index = buildIndex([page("Miete Miete miete")]);
    const matches = locateEvidence(index, [finding("Miete")]);
    expect(matches).toHaveLength(2);
    expect(matches.map((item) => item.spans[0]!.start)).toEqual([0, 6]);
    expect(locateEvidence(index, [finding("MIETE")])).toHaveLength(0);
    expect(locateEvidence(index, [finding("Miete ... Miete")])).toHaveLength(0);
    expect(locateEvidence(index, [finding("")])).toHaveLength(0);
  });
  it("maps cross-line and cross-page hyphenated quotes", () => {
    const index = buildIndex([
      [
        { str: "Unbegrenzte Haf-", hasEOL: true },
        { str: "tung für", hasEOL: true },
      ],
      page("alle Schäden."),
    ]);
    const matches = locateEvidence(index, [
      finding("Unbegrenzte Haftung für alle Schäden."),
    ]);
    expect(matches).toHaveLength(1);
    expect(matches[0]!.spans.map((span) => span.page)).toEqual([1, 1, 2]);
    expect(matches[0]!.spans[0]!.start).toBe(0);
    expect(matches[0]!.spans[2]!.end).toBe(13);
  });
  it("allows the same evidence for different findings without inventing positions", () => {
    const item = finding("Tenant duty.");
    const matches = locateEvidence(buildIndex([page("Tenant duty.")]), [
      item,
      { ...item, id: "ai:2" },
    ]);
    expect(matches.map((match) => match.findingId)).toEqual(["rule:1", "ai:2"]);
    expect(
      locateEvidence(buildIndex([page("Tenant duty.")]), [
        finding("Landlord duty."),
      ]),
    ).toEqual([]);
  });
});
