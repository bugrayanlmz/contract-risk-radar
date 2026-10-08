import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import type { HighlightFinding } from "../features/pdf/evidence";
import type { PdfTarget } from "../features/pdf/PdfViewer";
const PdfViewer = lazy(() =>
  import("../features/pdf/PdfViewer").then((module) => ({
    default: module.PdfViewer,
  })),
);
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  CalendarDays,
  Check,
  Download,
  FileText,
  Quote,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { retryDocument } from "../api/generated/sdk.gen";
import type {
  AiFindingResult,
  AnalysisResponse,
  ClauseResult,
} from "../api/generated/types.gen";
import { documentQuery, errorMessage, resultsQuery } from "../api/queries";
import { queryClient } from "../app/router";
import {
  ErrorBox,
  Loading,
  ScoreBadge,
  categoryName,
  formatDate,
} from "../components/shared";

const stages = [
  "queued",
  "extracting_text",
  "extracting_clauses",
  "verifying",
  "scoring",
  "reviewing_additional_risks",
  "saving",
] as const;
const stageLabels: Record<string, string> = {
  queued: "Waiting for the worker",
  extracting_text: "Reading the PDF text",
  extracting_clauses: "Extracting contract facts and clauses",
  verifying: "Checking the quoted evidence",
  scoring: "Applying risk rules and calculating dates",
  reviewing_additional_risks: "Reviewing additional conditions with AI",
  saving: "Saving your results",
};

function displayValue(value: unknown): string {
  if (value === null) return "Unknown";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object" && value && "amount" in value) {
    const currency =
      "currency" in value && typeof value.currency === "string"
        ? `${value.currency} `
        : "";
    const [whole, fraction = ""] = String(value.amount).split(".");
    const decimals = fraction.replace(/0+$/, "").padEnd(2, "0");
    return (
      currency + whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",") + "." + decimals
    );
  }
  return String(value);
}

export function Finding({ finding }: { finding: ClauseResult }) {
  const clause = finding.clause;
  return (
    <article className="finding-card">
      <div className="finding-heading">
        <div>
          <span
            className={`tiny-square severity-dot-${finding.score ?? "none"}`}
          />
          <h3>{categoryName(clause.category)}</h3>
          {finding.partial && (
            <span className="partial-tag">Incomplete inputs</span>
          )}
        </div>
        <ScoreBadge score={finding.score} />
      </div>
      <p className="finding-explanation">{clause.explanation}</p>
      <div
        className={`evidence-block ${finding.quote_verified ? "" : "unverified"}`}
      >
        <div className="evidence-label">
          <Quote size={14} /> CONTRACT EVIDENCE{" "}
          <span>
            {finding.quote_verified ? (
              <>
                <Check size={13} /> Text verified
              </>
            ) : (
              <>
                <AlertTriangle size={13} /> Unverified quote
              </>
            )}
          </span>
        </div>
        <blockquote>{clause.quote}</blockquote>
      </div>
      {finding.risk_factors.length > 0 && (
        <div className="risk-factors">
          <h4>What drives this score</h4>
          <ul>
            {finding.risk_factors.map((factor) => (
              <li key={factor.code}>{factor.explanation}</li>
            ))}
          </ul>
        </div>
      )}
      {finding.warnings.length > 0 && (
        <div className="finding-warnings">
          {finding.warnings.map((warning) => (
            <p key={warning}>
              <AlertTriangle size={13} />
              {warning}
            </p>
          ))}
        </div>
      )}
      <details className="attributes-details">
        <summary>View extracted facts</summary>
        <dl>
          {Object.entries(clause.attributes).map(([key, value]) => (
            <div key={key}>
              <dt>{categoryName(key)}</dt>
              <dd>{displayValue(value)}</dd>
            </div>
          ))}
        </dl>
      </details>
    </article>
  );
}

function ContractDetails({ result }: { result: AnalysisResponse }) {
  const facts = result.facts;
  return (
    <aside className="results-aside">
      <section className="panel facts-panel">
        <div className="section-heading">
          <h2>Contract at a glance</h2>
          <FileText size={18} />
        </div>
        <dl>
          {(
            [
              "monthly_rent",
              "deposit_amount",
              "start_date",
              "end_date",
            ] as const
          ).map((key) => {
            const value = facts[key];
            const proof = result.field_evidence[key];
            return (
              <div key={key}>
                <dt>{categoryName(key)}</dt>
                <dd>
                  {value === null
                    ? "Not stated"
                    : typeof value === "string"
                      ? formatDate(value)
                      : displayValue(value)}
                  {value !== null && (
                    <span
                      className={
                        proof?.verified ? "fact-verified" : "fact-unverified"
                      }
                    >
                      {proof?.verified
                        ? "Evidence verified"
                        : "Unverified candidate"}
                    </span>
                  )}
                </dd>
                {proof?.quote && (
                  <details className="fact-evidence">
                    <summary>See evidence</summary>
                    <blockquote>{proof.quote}</blockquote>
                  </details>
                )}
              </div>
            );
          })}
        </dl>
      </section>
      <section className="panel timeline-panel">
        <div className="section-heading">
          <h2>Important dates</h2>
          <CalendarDays size={18} />
        </div>
        {result.important_dates.length ? (
          <ol className="timeline">
            {result.important_dates.map((date) => (
              <li key={date.id}>
                <time>{formatDate(date.date)}</time>
                <strong>{categoryName(date.kind)}</strong>
                <p>{date.basis}</p>
              </li>
            ))}
          </ol>
        ) : (
          <p className="muted">No supported dates could be calculated.</p>
        )}
      </section>
      <div className="results-note">
        <ShieldCheck size={20} />
        <p>
          Verified evidence means the quoted text exists in the PDF. It does not
          certify the interpretation or legal effect.
        </p>
      </div>
      <p className="provenance">
        Language: {result.facts.language} · AI scale{" "}
        {result.ai_rubric_version ?? "not run"}
        <br />
        Rules {result.rules_version} · Prompt {result.prompt_version} · Schema{" "}
        {result.schema_version}
        <br />
        {result.provider} · {result.model}
      </p>
    </aside>
  );
}

function AiFindingCard({ finding }: { finding: AiFindingResult }) {
  return (
    <article className="finding-card ai-finding-card">
      <div className="finding-heading">
        <div>
          <span className="finding-source">AI assessment</span>
          <h3>{finding.title}</h3>
        </div>
        <ScoreBadge score={finding.score} />
      </div>
      {finding.related_category && (
        <p className="muted">
          Related to {categoryName(finding.related_category)}
        </p>
      )}
      <p className="finding-explanation">{finding.explanation}</p>
      <div
        className={`evidence-block ${finding.quote_verified ? "" : "unverified"}`}
      >
        <div className="evidence-label">
          <Quote size={14} /> CONTRACT EVIDENCE{" "}
          <span>
            {finding.quote_verified ? (
              <>
                <Check size={13} /> Text verified
              </>
            ) : (
              <>
                <AlertTriangle size={13} /> Unverified quote
              </>
            )}
          </span>
        </div>
        <blockquote>{finding.quote}</blockquote>
      </div>
      <div className="risk-factors">
        <h4>Model's reasoning</h4>
        <p>{finding.rationale}</p>
      </div>
      {!!finding.uncertainties.length && (
        <div className="finding-warnings">
          <h4>Uncertainties</h4>
          {finding.uncertainties.map((item) => (
            <p key={item}>{item}</p>
          ))}
        </div>
      )}
      {finding.warnings.map((warning) => (
        <p className="finding-warnings" key={warning}>
          <AlertTriangle size={13} /> {warning}
        </p>
      ))}
      {!finding.quote_verified && (
        <p className="muted">
          Unverified model candidate: {finding.model_score}/5. Excluded from the
          displayed score.
        </p>
      )}
    </article>
  );
}

function Results({ result }: { result: AnalysisResponse }) {
  const [selected, setSelected] = useState<string | null>(null);
  const [selectionSequence, setSelectionSequence] = useState(0);
  const [tab, setTab] = useState<"findings" | "details">("findings");
  const [mobileTab, setMobileTab] = useState<"pdf" | "findings">("findings");
  const [locations, setLocations] = useState<string[]>([]);
  const [locationsReady, setLocationsReady] = useState(false);
  const [target, setTarget] = useState<PdfTarget>(null);
  const panel = useRef<HTMLDivElement>(null);
  const highlights = useMemo<HighlightFinding[]>(
    () => [
      ...result.clauses
        .filter(
          (item) =>
            item.quote_verified && item.score !== null && item.score >= 2,
        )
        .map((item) => ({
          id: `rule:${item.id}`,
          quote: item.clause.quote,
          title: categoryName(item.clause.category),
          source: "rule" as const,
          score: item.score!,
        })),
      ...result.ai_findings
        .filter(
          (item) =>
            item.quote_verified && item.score !== null && item.score >= 2,
        )
        .map((item) => ({
          id: `ai:${item.id}`,
          quote: item.quote,
          title: item.title,
          source: "ai" as const,
          score: item.score!,
        })),
    ],
    [result],
  );
  useEffect(() => {
    if (!selected || tab !== "findings" || mobileTab !== "findings") return;
    requestAnimationFrame(() => {
      const card = document.getElementById(`finding-${selected}`);
      if (card && panel.current) {
        panel.current.scrollTo({
          top:
            panel.current.scrollTop +
            card.getBoundingClientRect().top -
            panel.current.getBoundingClientRect().top -
            12,
          behavior: "instant",
        });
        card.focus({ preventScroll: true });
      }
    });
  }, [selected, tab, mobileTab, selectionSequence]);
  const choose = (id: string) => {
    setTarget(null);
    setSelectionSequence((value) => value + 1);
    setSelected(id);
    setTab("findings");
    setMobileTab("findings");
  };
  const view = (id: string) => {
    setSelected(id);
    setMobileTab("pdf");
    setTarget({ findingId: id, sequence: (target?.sequence ?? 0) + 1 });
  };
  function navigation(id: string) {
    if (!highlights.some((item) => item.id === id)) return null;
    return locations.includes(id) ? (
      <button className="view-pdf-button" onClick={() => view(id)}>
        <FileText size={14} /> View in PDF
      </button>
    ) : (
      <span className="pdf-location-note">
        {locationsReady ? "PDF location unavailable" : "Locating in PDF…"}
      </span>
    );
  }
  const scores = [
    {
      label: "Rule-based risk",
      score: result.overall_score,
      description:
        "Highest verified score from the seven documented rule categories.",
    },
    {
      label: "Additional AI assessment",
      score: result.ai_overall_score,
      description:
        result.ai_review_status === "not_run"
          ? "Not run for this older analysis. Upload again to request an AI review."
          : "Highest verified model score for additional conditions. Subjective assessment.",
    },
  ];
  return (
    <>
      <div className="hybrid-scores">
        {scores.map((item) => (
          <section className="results-summary" key={item.label}>
            <div className={`overall-score severity-${item.score ?? "none"}`}>
              <span>{item.score ?? "—"}</span>
              <small>{item.score === null ? "Unavailable" : "out of 5"}</small>
            </div>
            <div>
              <h2>{item.label}</h2>
              <p>{item.description}</p>
            </div>
          </section>
        ))}
      </div>
      <p className="score-context">
        These scores are separate. Missing evidence and conditions not found do
        not imply low risk.
      </p>
      {result.warnings.length > 0 && (
        <details className="analysis-warnings">
          <summary>
            <AlertTriangle size={17} /> Evidence and calculation limitations{" "}
            <span>{result.warnings.length}</span>
          </summary>
          <ul>
            {result.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </details>
      )}
      <div
        className="mobile-result-tabs"
        role="tablist"
        aria-label="Results view"
      >
        <button
          role="tab"
          aria-selected={mobileTab === "pdf"}
          onClick={() => setMobileTab("pdf")}
        >
          PDF
        </button>
        <button
          role="tab"
          aria-selected={mobileTab === "findings"}
          onClick={() => setMobileTab("findings")}
        >
          Findings
        </button>
      </div>
      <div className={`analysis-workspace mobile-${mobileTab}`}>
        <div className="pdf-panel">
          <Suspense fallback={<Loading label="Loading PDF viewer…" />}>
            <PdfViewer
              documentId={result.document_id}
              findings={highlights}
              selected={selected}
              target={target}
              active={
                mobileTab === "pdf" ||
                window.matchMedia("(min-width: 801px)").matches
              }
              onSelect={choose}
              onLocations={(ids, finished) => {
                setLocations(ids);
                setLocationsReady(finished);
              }}
            />
          </Suspense>
        </div>
        <section className="findings-panel">
          <div
            className="findings-tabs"
            role="tablist"
            aria-label="Analysis sections"
          >
            <button
              role="tab"
              aria-selected={tab === "findings"}
              onClick={() => setTab("findings")}
            >
              Findings{" "}
              <span>{result.clauses.length + result.ai_findings.length}</span>
            </button>
            <button
              role="tab"
              aria-selected={tab === "details"}
              onClick={() => setTab("details")}
            >
              Contract details
            </button>
          </div>
          <div ref={panel} className="findings-scroll">
            {tab === "details" ? (
              <ContractDetails result={result} />
            ) : (
              <>
                <h2 className="findings-group-title">Rule-based findings</h2>
                {result.clauses.length ? (
                  [...result.clauses]
                    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
                    .map((finding) => {
                      const id = `rule:${finding.id}`;
                      return (
                        <div
                          className={`finding-slot ${selected === id ? "selected" : ""}`}
                          id={`finding-${id}`}
                          key={id}
                          tabIndex={-1}
                          aria-label={`${categoryName(finding.clause.category)} rule finding${selected === id ? ", selected" : ""}`}
                        >
                          {selected === id && (
                            <span className="selection-label">
                              Selected finding
                            </span>
                          )}
                          <Finding finding={finding} />
                          <div className="finding-navigation">
                            <span className="finding-source">Rule-based</span>
                            {navigation(id)}
                          </div>
                        </div>
                      );
                    })
                ) : (
                  <p>
                    No clauses were extracted. This does not establish that
                    risky terms are absent.
                  </p>
                )}
                {!!result.categories_not_found.length && (
                  <div className="not-found-categories">
                    <h3>Not found in the extraction</h3>
                    <p>Absence is not a safety assessment.</p>
                    <div>
                      {result.categories_not_found.map((category) => (
                        <span key={category}>{categoryName(category)}</span>
                      ))}
                    </div>
                  </div>
                )}
                <h2 className="findings-group-title">
                  Additional AI assessment
                </h2>
                <p className="muted">
                  Model judgments about conditions beyond the scoring rules.
                  Quotes retain the contract's original language.
                </p>
                {result.ai_review_status === "not_run" ? (
                  <p>Additional AI review was not run for this analysis.</p>
                ) : result.ai_findings.length ? (
                  [...result.ai_findings]
                    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
                    .map((finding) => {
                      const id = `ai:${finding.id}`;
                      return (
                        <div
                          className={`finding-slot ${selected === id ? "selected" : ""}`}
                          id={`finding-${id}`}
                          key={id}
                          tabIndex={-1}
                          aria-label={`${finding.title} AI finding${selected === id ? ", selected" : ""}`}
                        >
                          {selected === id && (
                            <span className="selection-label">
                              Selected finding
                            </span>
                          )}
                          <AiFindingCard finding={finding} />
                          <div className="finding-navigation">
                            <span className="finding-source">
                              AI assessment
                            </span>
                            {navigation(id)}
                          </div>
                        </div>
                      );
                    })
                ) : (
                  <p>
                    No additional issues were identified. This does not
                    establish that the contract is safe.
                  </p>
                )}
              </>
            )}
          </div>
        </section>
      </div>
    </>
  );
}

export function DocumentPage() {
  const { id = "" } = useParams();
  const document = useQuery(documentQuery(id));
  const results = useQuery({
    ...resultsQuery(id),
    enabled: document.data?.status === "completed",
  });
  const retry = useMutation({
    mutationFn: async () =>
      (await retryDocument({ path: { document_id: id } })).data!,
    onSuccess: (data) => {
      queryClient.setQueryData(["document", id], data);
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });
  return (
    <>
      <Link className="back-link" to="/app">
        <ArrowLeft size={15} /> My contracts
      </Link>
      {document.isPending ? (
        <Loading />
      ) : document.isError ? (
        <>
          <ErrorBox message={errorMessage(document.error)} />
          <button
            className="button secondary"
            onClick={() => void document.refetch()}
          >
            Try again
          </button>
        </>
      ) : (
        <>
          <div className="page-heading document-heading">
            <div>
              <span className="eyebrow">CONTRACT ANALYSIS</span>
              <h1>{document.data.filename}</h1>
              <p>Uploaded {formatDate(document.data.created_at)}</p>
            </div>
            <a
              className="button secondary small"
              href={`/api/documents/${id}/file`}
            >
              <Download size={16} /> Download PDF
            </a>
          </div>
          {document.data.status === "processing" ? (
            <section className="processing-card">
              <div className="radar-loader">
                <span />
                <ShieldCheck size={35} />
              </div>
              <span className="eyebrow">A CLEARER PICTURE IS ON ITS WAY</span>
              <h2>
                {stageLabels[document.data.stage] ?? "Analyzing your contract"}
              </h2>
              <p>
                You can leave this page and return from your contract library.
                <br />
                Results appear here when the analysis is complete.
              </p>
              <ol className="processing-steps">
                {stages.map((stage, index) => {
                  const current = stages.indexOf(
                    document.data.stage as (typeof stages)[number],
                  );
                  return (
                    <li
                      className={
                        index < current
                          ? "done"
                          : index === current
                            ? "current"
                            : ""
                      }
                      key={stage}
                    >
                      <span>
                        {index < current ? <Check size={13} /> : index + 1}
                      </span>
                      {stageLabels[stage]}
                    </li>
                  );
                })}
              </ol>
            </section>
          ) : document.data.status === "failed" ? (
            <section className="failure-card">
              <AlertTriangle size={35} />
              <h2>We couldn’t complete this analysis.</h2>
              <p>{document.data.error_message}</p>
              {retry.isError && (
                <ErrorBox message={errorMessage(retry.error)} />
              )}
              {document.data.retryable ? (
                <button
                  className="button"
                  disabled={retry.isPending}
                  onClick={() => retry.mutate()}
                >
                  <RefreshCw size={17} />
                  {retry.isPending ? "Retrying…" : "Retry analysis"}
                </button>
              ) : (
                <Link className="button" to="/app/upload">
                  Upload another contract
                </Link>
              )}
            </section>
          ) : results.isPending ? (
            <Loading label="Loading your findings…" />
          ) : results.isError ? (
            <>
              <ErrorBox message={errorMessage(results.error)} />
              <button
                className="button secondary"
                onClick={() => void results.refetch()}
              >
                Try again
              </button>
            </>
          ) : (
            <Results key={results.data.document_id} result={results.data} />
          )}
        </>
      )}
    </>
  );
}
