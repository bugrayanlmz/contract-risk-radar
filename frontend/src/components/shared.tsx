import { AlertCircle, ArrowUpRight, Radar } from "lucide-react";
import { Link } from "react-router-dom";

export const DISCLAIMER = "Contract analysis demo. Not legal advice.";

export function Logo() {
  return (
    <Link className="logo" to="/">
      <span className="logo-icon">
        <Radar size={23} />
      </span>
      <span>
        Contract Risk <strong>Radar</strong>
      </span>
    </Link>
  );
}

export function Footer() {
  return (
    <footer className="footer">
      <span>{DISCLAIMER}</span>
      <span>
        Built for clarity <ArrowUpRight size={13} />
      </span>
    </footer>
  );
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="error-box" role="alert">
      <AlertCircle size={18} />
      <span>{message}</span>
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="loading" role="status">
      <span className="spinner" />
      {label}
    </div>
  );
}

export function categoryName(value: string) {
  return value
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/^./, (char) => char.toUpperCase());
}

export function formatDate(value: string) {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(value));
}

export function ScoreBadge({ score }: { score: number | null }) {
  return (
    <span className={`score-badge severity-${score ?? "none"}`}>
      {score === null ? "Not scored" : `${score} / 5`}
    </span>
  );
}
