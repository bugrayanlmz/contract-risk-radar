/** Same conservative normalization as backend/app/analysis/evidence.py.
 * Offsets refer to UTF-16 strings, which DOM Range and PDF.js also use. */
export type MappedText = {
  text: string;
  origins: { start: number; end: number }[];
};
const quotes: Record<string, string> = {
  "‘": "'",
  "’": "'",
  "‚": "'",
  "“": '"',
  "”": '"',
  "„": '"',
};
const whitespace = /[\s\u0085\u001c-\u001f]/u;

export function normalizeMapped(raw: string): MappedText {
  const chars: { value: string; start: number; end: number }[] = [];
  for (const part of new Intl.Segmenter(undefined, {
    granularity: "grapheme",
  }).segment(raw)) {
    const normalized = part.segment.normalize("NFKC");
    for (let offset = 0; offset < normalized.length; offset++) {
      const value = normalized[offset]!;
      chars.push({
        value: quotes[value] ?? value,
        start: part.index,
        end: part.index + part.segment.length,
      });
    }
  }
  const normalized = chars.map((char) => char.value).join("");
  const removed = new Set<number>();
  const hyphen =
    /([\p{L}\p{Nl}\p{No}])[-‐\u00ad][ \t]*\r?\n[ \t]*([\p{L}\p{Nl}\p{No}])/gu;
  for (const match of normalized.matchAll(hyphen)) {
    const start = match.index + match[1]!.length;
    const end = match.index + match[0].length - match[2]!.length;
    for (let offset = start; offset < end; offset++) removed.add(offset);
  }
  const output: typeof chars = [];
  for (const [offset, char] of chars.entries()) {
    if (removed.has(offset)) continue;
    if (whitespace.test(char.value)) {
      if (output.length === 0) continue;
      const previous = output.at(-1)!;
      if (previous.value === " ") previous.end = char.end;
      else output.push({ ...char, value: " " });
    } else output.push({ ...char });
  }
  if (output.at(-1)?.value === " ") output.pop();
  return {
    text: output.map((char) => char.value).join(""),
    origins: output.map(({ start, end }) => ({ start, end })),
  };
}

export const normalizeText = (text: string) => normalizeMapped(text).text;
export type TextPiece = { str: string; hasEOL: boolean };
export type Segment = {
  page: number;
  item: number;
  start: number;
  end: number;
};
export type PdfIndex = MappedText & { segments: Segment[] };
export type TextSpan = {
  page: number;
  item: number;
  start: number;
  end: number;
};
export type EvidenceMatch = {
  findingId: string;
  occurrence: number;
  spans: TextSpan[];
};
export type HighlightFinding = {
  id: string;
  quote: string;
  title: string;
  source: "rule" | "ai";
  score: number;
};

export function buildIndex(pages: TextPiece[][]): PdfIndex {
  let raw = "";
  const segments: Segment[] = [];
  pages.forEach((pieces, index) => {
    pieces.forEach((piece, item) => {
      const start = raw.length;
      raw += piece.str;
      segments.push({ page: index + 1, item, start, end: raw.length });
      if (piece.hasEOL) raw += "\n";
    });
    raw += "\n";
  });
  return { ...normalizeMapped(raw), segments };
}

export function locateEvidence(
  index: PdfIndex,
  findings: HighlightFinding[],
): EvidenceMatch[] {
  const result: EvidenceMatch[] = [];
  for (const finding of findings) {
    const quote = normalizeText(finding.quote);
    if (!quote) continue;
    let from = 0,
      occurrence = 0;
    for (;;) {
      const match = index.text.indexOf(quote, from);
      if (match === -1) break;
      const start = index.origins[match]!.start;
      const end = index.origins[match + quote.length - 1]!.end;
      const spans = index.segments
        .filter((segment) => segment.end > start && segment.start < end)
        .map((segment) => ({
          page: segment.page,
          item: segment.item,
          start: Math.max(start, segment.start) - segment.start,
          end: Math.min(end, segment.end) - segment.start,
        }));
      if (spans.length)
        result.push({ findingId: finding.id, occurrence: occurrence++, spans });
      from = match + 1; // Include overlapping exact occurrences.
    }
  }
  return result;
}
