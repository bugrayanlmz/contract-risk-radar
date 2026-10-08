import { useRef, useState, type DragEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  FileText,
  UploadCloud,
  X,
  ShieldCheck,
} from "lucide-react";
import { downloadSample, uploadDocument } from "../api/generated/sdk.gen";
import { capabilitiesQuery, errorMessage, samplesQuery } from "../api/queries";
import { queryClient } from "../app/router";
import { ErrorBox, Loading } from "../components/shared";
import { useUploadStore } from "../stores/upload";

export function Upload() {
  const {
    file,
    confirmed,
    documentKind,
    setDocumentKind,
    setFile,
    setConfirmed,
    reset,
  } = useUploadStore();
  const [selectionError, setSelectionError] = useState("");
  const [busySample, setBusySample] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const capabilities = useQuery(capabilitiesQuery);
  const samples = useQuery(samplesQuery);
  const upload = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("Choose a PDF first.");
      return (
        await uploadDocument({
          body: {
            file,
            document_kind: documentKind,
            analysis_consent_confirmed: confirmed,
          },
        })
      ).data!;
    },
    onSuccess: (document) => {
      reset();
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
      navigate(`/app/documents/${document.id}`);
    },
  });
  function choose(candidate?: File) {
    setSelectionError("");
    if (!candidate) return;
    if (!candidate.name.toLowerCase().endsWith(".pdf")) {
      setSelectionError("Choose a PDF file.");
      return;
    }
    if (candidate.size > 10 * 1024 * 1024) {
      setSelectionError("Choose a PDF no larger than 10 MiB.");
      return;
    }
    setFile(candidate);
  }
  function drop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    choose(event.dataTransfer.files[0]);
  }
  async function selectSample(id: string) {
    setBusySample(id);
    setSelectionError("");
    try {
      const result = await downloadSample({
        path: { sample_id: id },
        parseAs: "blob",
      });
      const blob = result.data as Blob;
      setDocumentKind("synthetic");
      setFile(new File([blob], `${id}.pdf`, { type: "application/pdf" }));
    } catch (error) {
      setSelectionError(errorMessage(error));
    } finally {
      setBusySample(null);
    }
  }
  return (
    <>
      <Link className="back-link" to="/app">
        <ArrowLeft size={15} /> My contracts
      </Link>
      <div className="page-heading">
        <div>
          <span className="eyebrow">A LITTLE CONTEXT GOES A LONG WAY</span>
          <h1>Let’s read the fine print.</h1>
          <p>Upload an English or German residential rental contract.</p>
        </div>
      </div>
      <div className="upload-grid">
        <section className="panel">
          <div className="panel-heading">
            <span className="step-number">01</span>
            <div>
              <h2>Choose your contract</h2>
              <p>Text-based PDF · Up to 10 MiB · Up to 30 pages</p>
            </div>
          </div>
          <input
            ref={input}
            className="visually-hidden"
            aria-label="Contract PDF"
            type="file"
            accept="application/pdf,.pdf"
            onChange={(event) => choose(event.target.files?.[0])}
          />
          <button
            className={`drop-zone ${dragging ? "dragging" : ""}`}
            onClick={() => input.current?.click()}
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={drop}
          >
            <span className="upload-icon">
              <UploadCloud size={27} />
            </span>
            <strong>Drop your PDF here</strong>
            <span>or click to browse files</span>
            <small>
              Scanned documents and encrypted PDFs are not supported.
            </small>
          </button>
          {file && (
            <div className="selected-file">
              <FileText size={23} />
              <div>
                <strong>{file.name}</strong>
                <span>{(file.size / 1024).toFixed(1)} KiB · PDF document</span>
              </div>
              <button
                className="icon-button"
                aria-label="Remove selected file"
                onClick={() => setFile(null)}
              >
                <X size={17} />
              </button>
            </div>
          )}
          <fieldset className="document-kind">
            <legend>Document type</legend>
            <label>
              <input
                type="radio"
                name="document-kind"
                checked={documentKind === "synthetic"}
                onChange={() => setDocumentKind("synthetic")}
              />{" "}
              Synthetic example
            </label>
            {capabilities.data?.real_documents_allowed && (
              <label>
                <input
                  type="radio"
                  name="document-kind"
                  checked={documentKind === "real"}
                  onChange={() => setDocumentKind("real")}
                />{" "}
                Real contract (local development)
              </label>
            )}
          </fieldset>
          {capabilities.isError && (
            <ErrorBox message={errorMessage(capabilities.error)} />
          )}
          <label className="confirmation">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(event) => setConfirmed(event.target.checked)}
            />
            <span>
              I am authorized to upload this{" "}
              {documentKind === "synthetic" ? "synthetic " : ""}English or
              German residential rental contract and consent to its text being
              sent to the configured AI provider.
              {documentKind === "synthetic" &&
                " It contains no real personal information."}
            </span>
          </label>
          {selectionError && <ErrorBox message={selectionError} />}
          {upload.isError && <ErrorBox message={errorMessage(upload.error)} />}
          <button
            className="button full"
            disabled={
              !file ||
              !confirmed ||
              !capabilities.data ||
              (documentKind === "real" &&
                !capabilities.data.real_documents_allowed) ||
              upload.isPending ||
              busySample !== null
            }
            onClick={() => upload.mutate()}
          >
            {upload.isPending ? "Uploading…" : "Analyze contract"}
            <ArrowRight size={18} />
          </button>
          <p className="privacy-note">
            <ShieldCheck size={14} /> Contract text is sent to the configured
            analysis provider.
          </p>
        </section>
        <aside className="sample-panel">
          <span className="eyebrow">JUST EXPLORING?</span>
          <h2>Start with a sample.</h2>
          <p>Synthetic agreements showing how the analysis works.</p>
          {samples.isPending ? (
            <Loading />
          ) : samples.isError ? (
            <ErrorBox message={errorMessage(samples.error)} />
          ) : (
            samples.data.map((sample) => (
              <button
                className="sample-card"
                key={sample.id}
                disabled={busySample !== null || upload.isPending}
                onClick={() => void selectSample(sample.id)}
              >
                <span className="document-icon">
                  <FileText size={19} />
                </span>
                <div>
                  <strong>{sample.name}</strong>
                  <p>{sample.description}</p>
                </div>
                <ArrowRight size={16} />
              </button>
            ))
          )}
          <div className="sample-footnote">
            <span className="tiny-square" /> Risk scores follow documented
            heuristics and are not jurisdiction-specific legal assessments.
          </div>
        </aside>
      </div>
    </>
  );
}
