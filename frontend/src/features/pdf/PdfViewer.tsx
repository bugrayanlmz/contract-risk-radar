import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Document, Page, pdfjs } from "react-pdf";
import type { PDFDocumentProxy } from "pdfjs-dist";
import { downloadDocument } from "../../api/generated/sdk.gen";
import { Loading } from "../../components/shared";
import {
  buildIndex,
  locateEvidence,
  type EvidenceMatch,
  type HighlightFinding,
  type TextPiece,
} from "./evidence";
import "react-pdf/dist/Page/TextLayer.css";

pdfjs.GlobalWorkerOptions.workerSrc = "/pdfjs/pdf.worker.min.mjs";
const options = {
  cMapUrl: "/pdfjs/cmaps/",
  cMapPacked: true,
  standardFontDataUrl: "/pdfjs/standard_fonts/",
  wasmUrl: "/pdfjs/wasm/",
  isEvalSupported: false,
};
type Rect = {
  left: number;
  top: number;
  width: number;
  height: number;
  ids: string[];
};
type PageInfo = { width: number; height: number; pieces: TextPiece[] };
export type PdfTarget = { findingId: string; sequence: number } | null;

function MarkedPage({
  pageNumber,
  info,
  width,
  root,
  matches,
  selected,
  findings,
  onSelect,
  onMissing,
}: {
  pageNumber: number;
  info: PageInfo;
  width: number;
  root: HTMLElement | null;
  matches: EvidenceMatch[];
  selected: string | null;
  findings: HighlightFinding[];
  onSelect: (ids: string[], element: HTMLElement) => void;
  onMissing: (ids: string[]) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(pageNumber === 1);
  const [rects, setRects] = useState<Rect[]>([]);
  const scale = width / info.width;
  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => setVisible(entry!.isIntersecting),
      { root, rootMargin: "100% 0px" },
    );
    if (container.current) observer.observe(container.current);
    return () => observer.disconnect();
  }, [root]);
  const measure = useCallback(() => {
    const element = container.current;
    if (!element) return;
    const box = element.getBoundingClientRect();
    if (box.width === 0 || box.height === 0) return;
    const divs = Array.from(
      element.querySelectorAll<HTMLSpanElement>(
        '.textLayer span[role="presentation"]',
      ),
    );
    if (!divs.length) return;
    const byItem: (HTMLSpanElement | null)[] = [];
    let divIndex = 0;
    info.pieces.forEach((piece) => {
      byItem.push(piece.str ? (divs[divIndex++] ?? null) : null);
    });
    const next: Rect[] = [],
      missing = new Set<string>();
    for (const match of matches) {
      const spans = match.spans.filter((span) => span.page === pageNumber);
      if (!spans.length) continue;
      const fragmentRects: Rect[] = [];
      let valid = true;
      for (const span of spans) {
        const div = byItem[span.item];
        const text = div?.firstChild;
        if (
          !div ||
          !text ||
          text.nodeType !== Node.TEXT_NODE ||
          div.textContent !== info.pieces[span.item]?.str
        ) {
          valid = false;
          break;
        }
        const range = document.createRange();
        range.setStart(text, span.start);
        range.setEnd(text, span.end);
        for (const rect of range.getClientRects()) {
          if (rect.width > 0 && rect.height > 0)
            fragmentRects.push({
              left: rect.left - box.left,
              top: rect.top - box.top,
              width: rect.width,
              height: rect.height,
              ids: [match.findingId],
            });
        }
      }
      if (!valid || !fragmentRects.length) {
        missing.add(match.findingId);
        continue;
      }
      next.push(...fragmentRects);
    }
    // Overlapping passages expose all associated findings in a small chooser.
    const grouped: Rect[] = [];
    for (const rect of next) {
      const overlap = grouped.find(
        (other) =>
          Math.min(other.left + other.width, rect.left + rect.width) -
            Math.max(other.left, rect.left) >
            0.5 &&
          Math.min(other.top + other.height, rect.top + rect.height) -
            Math.max(other.top, rect.top) >
            0.5,
      );
      if (overlap) {
        const right = Math.max(
            overlap.left + overlap.width,
            rect.left + rect.width,
          ),
          bottom = Math.max(
            overlap.top + overlap.height,
            rect.top + rect.height,
          );
        overlap.left = Math.min(overlap.left, rect.left);
        overlap.top = Math.min(overlap.top, rect.top);
        overlap.width = right - overlap.left;
        overlap.height = bottom - overlap.top;
        overlap.ids = [...new Set([...overlap.ids, ...rect.ids])];
      } else grouped.push({ ...rect });
    }
    setRects(grouped);
    if (missing.size) onMissing([...missing]);
  }, [info, matches, onMissing, pageNumber]);
  useEffect(() => {
    if (!visible) {
      setRects([]);
      return;
    }
    const observer = new ResizeObserver(() => requestAnimationFrame(measure));
    if (container.current) observer.observe(container.current);
    return () => observer.disconnect();
  }, [visible, measure, width]);
  return (
    <div
      ref={container}
      className="pdf-page"
      data-page={pageNumber}
      style={{ width, height: info.height * scale }}
    >
      {visible ? (
        <Page
          pageNumber={pageNumber}
          width={width}
          renderAnnotationLayer={false}
          suspense={false}
          devicePixelRatio={Math.min(window.devicePixelRatio || 1, 2)}
          onRenderTextLayerSuccess={measure}
          onRenderTextLayerError={() =>
            onMissing(
              matches
                .filter((match) =>
                  match.spans.some((span) => span.page === pageNumber),
                )
                .map((match) => match.findingId),
            )
          }
          loading={<Loading label={`Rendering page ${pageNumber}…`} />}
          error={
            <p className="pdf-page-error">
              Page {pageNumber} could not be rendered.
            </p>
          }
        />
      ) : (
        <span className="pdf-placeholder">Page {pageNumber}</span>
      )}
      <div className="pdf-marks">
        {rects.map((rect, index) => {
          const items = rect.ids
            .map((id) => findings.find((finding) => finding.id === id)!)
            .filter(Boolean);
          const label = items
            .map(
              (item) =>
                `${item.source === "rule" ? "Rule finding" : "AI finding"}: ${item.title}`,
            )
            .join("; ");
          return (
            <button
              key={index}
              type="button"
              className={`pdf-mark ${rect.ids.includes(selected ?? "") ? "selected" : ""} risk-${Math.max(...items.map((item) => item.score))}`}
              style={{
                left: rect.left,
                top: rect.top,
                width: rect.width,
                height: rect.height,
              }}
              data-finding-ids={rect.ids.join(" ")}
              aria-label={label}
              aria-pressed={rect.ids.includes(selected ?? "")}
              title={label}
              onClick={(event) => onSelect(rect.ids, event.currentTarget)}
            />
          );
        })}
      </div>
      <span className="pdf-page-number">{pageNumber}</span>
    </div>
  );
}

export function PdfViewer({
  documentId,
  findings,
  selected,
  target,
  active,
  onSelect,
  onLocations,
}: {
  documentId: string;
  findings: HighlightFinding[];
  selected: string | null;
  target: PdfTarget;
  active: boolean;
  onSelect: (id: string) => void;
  onLocations: (ids: string[], finished: boolean) => void;
}) {
  const download = useQuery({
    queryKey: ["pdf", documentId],
    queryFn: async () => {
      const result = await downloadDocument({
        path: { document_id: documentId },
        parseAs: "blob",
      });
      return result.data!.arrayBuffer();
    },
    retry: false,
    gcTime: 0,
  });
  // PDF.js transfers its input to the worker. Copy the in-memory query data first.
  const file = useMemo(
    () =>
      download.data
        ? { data: new Uint8Array(download.data.slice(0)) }
        : undefined,
    [download.data],
  );
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [pages, setPages] = useState<PageInfo[]>([]);
  const [matches, setMatches] = useState<EvidenceMatch[]>([]);
  const [error, setError] = useState(false);
  const [indexing, setIndexing] = useState(true);
  const [containerWidth, setContainerWidth] = useState(600);
  const [zoom, setZoom] = useState(1);
  const [page, setPage] = useState(1);
  const [pageInput, setPageInput] = useState("1");
  const [chooser, setChooser] = useState<{
    ids: string[];
    left: number;
    top: number;
  } | null>(null);
  const scroll = useRef<HTMLDivElement>(null);
  const locations = useRef<string[]>([]);
  const locationsCallback = useRef(onLocations);
  locationsCallback.current = onLocations;
  const missing = useCallback((ids: string[]) => {
    const next = locations.current.filter((id) => !ids.includes(id));
    if (next.length === locations.current.length) return;
    locations.current = next;
    locationsCallback.current(next, true);
  }, []);
  useEffect(() => {
    if (!scroll.current) return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry!.contentRect.width > 0)
        setContainerWidth(entry!.contentRect.width);
    });
    observer.observe(scroll.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!pdf) return;
    let cancelled = false;
    void (async () => {
      try {
        const result: PageInfo[] = [];
        for (let number = 1; number <= pdf.numPages; number++) {
          const page = await pdf.getPage(number);
          const content = await page.getTextContent();
          const viewport = page.getViewport({ scale: 1 });
          result.push({
            width: viewport.width,
            height: viewport.height,
            pieces: content.items
              .filter((item): item is typeof item & TextPiece => "str" in item)
              .map((item) => ({ str: item.str, hasEOL: item.hasEOL })),
          });
          if (cancelled) return;
        }
        setPages(result);
        const located = locateEvidence(
          buildIndex(result.map((item) => item.pieces)),
          findings,
        );
        setMatches(located);
        locations.current = [...new Set(located.map((item) => item.findingId))];
        locationsCallback.current(locations.current, true);
        setIndexing(false);
      } catch {
        if (!cancelled) {
          setIndexing(false);
          setError(true);
          locationsCallback.current([], true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [pdf, findings]);
  useEffect(() => {
    if (download.isError || error) locationsCallback.current([], true);
  }, [download.isError, error]);
  const jump = useCallback(
    (number: number) => {
      if (number < 1 || number > pages.length) return;
      setPage(number);
      setPageInput(String(number));
      const element = scroll.current?.querySelector<HTMLElement>(
        `[data-page="${number}"]`,
      );
      if (element && scroll.current)
        scroll.current.scrollTo({
          top:
            scroll.current.scrollTop +
            element.getBoundingClientRect().top -
            scroll.current.getBoundingClientRect().top -
            16,
          behavior: "instant",
        });
    },
    [pages.length],
  );
  useEffect(() => {
    if (!target || !active || !scroll.current) return;
    const match = matches.find((item) => item.findingId === target.findingId);
    if (!match) return;
    const root = scroll.current;
    const number = match.spans[0]!.page;
    // A distant page first mounts its text layer. Wait for exact rectangles,
    // then bring the actual passage (rather than just its page) into view.
    const bringPassageIntoView = () => {
      const buttons = root
        .querySelector(`[data-page="${number}"]`)
        ?.querySelectorAll<HTMLElement>(".pdf-mark");
      const mark = Array.from(buttons ?? []).find((element) =>
        element.dataset.findingIds?.split(" ").includes(target.findingId),
      );
      if (!mark || !mark.getBoundingClientRect().width) return;
      root.scrollTo({
        top:
          root.scrollTop +
          mark.getBoundingClientRect().top -
          root.getBoundingClientRect().top -
          36,
        behavior: "instant",
      });
      observer.disconnect();
    };
    const observer = new MutationObserver(bringPassageIntoView);
    observer.observe(root, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["style"],
    });
    const frame = requestAnimationFrame(() => {
      jump(number);
      bringPassageIntoView();
    });
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [target, matches, jump, active, containerWidth]);
  const select = (ids: string[], element: HTMLElement) => {
    if (ids.length === 1) {
      setChooser(null);
      onSelect(ids[0]!);
    } else {
      const rect = element.getBoundingClientRect();
      setChooser({
        ids,
        left: Math.max(8, Math.min(rect.left, window.innerWidth - 288)),
        top: Math.max(8, Math.min(rect.bottom + 8, window.innerHeight - 200)),
      });
    }
  };
  const onScroll = () => {
    const viewport = scroll.current?.getBoundingClientRect();
    if (!viewport) return;
    const visible = Array.from(
      scroll.current!.querySelectorAll<HTMLElement>("[data-page]"),
    ).find(
      (element) => element.getBoundingClientRect().bottom > viewport.top + 40,
    );
    if (visible) {
      const number = Number(visible.dataset.page);
      setPage(number);
      setPageInput(String(number));
    }
  };
  return (
    <section className="pdf-viewer" aria-label="Uploaded PDF">
      <div className="pdf-toolbar">
        <form
          onSubmit={(event) => {
            event.preventDefault();
            jump(Number(pageInput));
          }}
        >
          <button
            type="button"
            aria-label="Previous PDF page"
            disabled={page <= 1}
            onClick={() => jump(page - 1)}
          >
            ‹
          </button>
          <label>
            Page{" "}
            <input
              aria-label="PDF page number"
              type="number"
              min={1}
              max={pages.length || 1}
              value={pageInput}
              onChange={(event) => setPageInput(event.target.value)}
            />
          </label>
          <span> / {pages.length || "—"}</span>
          <button type="submit" aria-label="Go to PDF page">
            Go
          </button>
          <button
            type="button"
            aria-label="Next PDF page"
            disabled={page >= pages.length}
            onClick={() => jump(page + 1)}
          >
            ›
          </button>
        </form>
        <div className="pdf-zoom">
          <button
            aria-label="Zoom out"
            disabled={zoom <= 0.6}
            onClick={() => setZoom((value) => Math.max(0.6, value - 0.2))}
          >
            −
          </button>
          <span>{Math.round(zoom * 100)}%</span>
          <button
            aria-label="Zoom in"
            disabled={zoom >= 2.4}
            onClick={() => setZoom((value) => Math.min(2.4, value + 0.2))}
          >
            +
          </button>
          <button onClick={() => setZoom(1)}>Fit width</button>
        </div>
      </div>
      <p className="pdf-help">
        Select a highlighted passage to see its finding.{" "}
        {indexing && !error && !download.isError && "Locating evidence…"}
      </p>
      <div ref={scroll} className="pdf-scroll" onScroll={onScroll}>
        {download.isError || error ? (
          <div className="pdf-error" role="status">
            <h3>PDF preview unavailable</h3>
            <p>
              Your findings are still available. Download the source PDF to view
              it.
            </p>
            <a href={`/api/documents/${documentId}/file`}>Download PDF</a>
          </div>
        ) : download.isPending ? (
          <Loading label="Loading PDF…" />
        ) : (
          <Document
            file={file}
            options={options}
            suspense={false}
            onLoadSuccess={setPdf}
            onLoadError={() => setError(true)}
            onSourceError={() => setError(true)}
            loading={<Loading label="Opening PDF…" />}
            error={<p>PDF preview unavailable.</p>}
          >
            {pages.map((info, index) => (
              <MarkedPage
                key={index}
                pageNumber={index + 1}
                info={info}
                width={Math.max(220, containerWidth - 32) * zoom}
                root={scroll.current}
                matches={matches}
                selected={selected}
                findings={findings}
                onSelect={select}
                onMissing={missing}
              />
            ))}
          </Document>
        )}
      </div>
      {chooser && (
        <div
          className="pdf-choice"
          role="dialog"
          aria-label="Choose finding"
          style={{ left: chooser.left, top: chooser.top }}
          onKeyDown={(event) => {
            if (event.key === "Escape") setChooser(null);
          }}
        >
          <strong>This passage has multiple findings</strong>
          {chooser.ids.map((id, index) => {
            const item = findings.find((finding) => finding.id === id)!;
            return (
              <button
                key={id}
                autoFocus={index === 0}
                onClick={() => {
                  onSelect(id);
                  setChooser(null);
                }}
              >
                {item.source === "rule" ? "Rule" : "AI"} · {item.title}
              </button>
            );
          })}
          <button onClick={() => setChooser(null)}>Close</button>
        </div>
      )}
    </section>
  );
}
