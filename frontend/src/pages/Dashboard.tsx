import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ArrowRight, FileText, Plus, FolderOpen } from "lucide-react";
import { documentsQuery, errorMessage } from "../api/queries";
import { ErrorBox, Loading, formatDate } from "../components/shared";

export function Dashboard() {
  const documents = useQuery({
    ...documentsQuery,
    refetchInterval: (query) =>
      query.state.data?.some((item) => item.status === "processing")
        ? 2000
        : false,
  });
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">YOUR CONTRACT LIBRARY</span>
          <h1>My contracts.</h1>
          <p>Every analysis, with the evidence close at hand.</p>
        </div>
        <Link className="button" to="/app/upload">
          <Plus size={17} /> Analyze a contract
        </Link>
      </div>
      {documents.isPending ? (
        <Loading />
      ) : documents.isError ? (
        <ErrorBox message={errorMessage(documents.error)} />
      ) : documents.data.length === 0 ? (
        <div className="empty-state">
          <span className="empty-icon">
            <FolderOpen size={32} />
          </span>
          <h2>A clearer view starts here.</h2>
          <p>
            Upload an English or German rental contract or explore a synthetic
            sample.
            <br />
            Your analyses will appear in this library.
          </p>
          <Link className="button" to="/app/upload">
            Start your first analysis <ArrowRight size={17} />
          </Link>
        </div>
      ) : (
        <section className="document-list">
          <div className="list-header">
            <span>CONTRACT</span>
            <span>UPLOADED</span>
            <span>STATUS</span>
            <span />
          </div>
          {documents.data.map((document) => (
            <Link
              className="document-row"
              key={document.id}
              to={`/app/documents/${document.id}`}
            >
              <div>
                <span className="document-icon">
                  <FileText size={22} />
                </span>
                <strong>{document.filename}</strong>
              </div>
              <time>{formatDate(document.created_at)}</time>
              <span className={`status-tag ${document.status}`}>
                {document.status === "completed"
                  ? "Ready to review"
                  : document.status === "failed"
                    ? "Needs attention"
                    : "Processing"}
              </span>
              <ArrowRight size={18} />
            </Link>
          ))}
        </section>
      )}
      <div className="library-note">
        <span className="tiny-square" /> English and German residential rental
        contracts are supported. Bundled examples are synthetic.
      </div>
    </>
  );
}
