import {
  ArrowRight,
  Check,
  FileText,
  Quote,
  ShieldCheck,
  CalendarDays,
  ScanLine,
  ArrowUpRight,
} from "lucide-react";
import { Link } from "react-router-dom";
import { Footer, Logo } from "../components/shared";

export function Landing() {
  return (
    <div className="shell landing-shell">
      <header className="public-header">
        <Logo />
        <nav>
          <a href="#how-it-works">How it works</a>
          <Link to="/login">Sign in</Link>
          <Link className="button small" to="/register">
            Try the demo <ArrowUpRight size={15} />
          </Link>
        </nav>
      </header>
      <main>
        <section className="hero">
          <div className="hero-copy">
            <div className="eyebrow">
              <span className="live-dot" /> YOUR RENTAL CONTRACT, MADE CLEAR
            </div>
            <h1>
              Know what’s in
              <br />
              the <span>fine print.</span>
            </h1>
            <p>
              Understand the clauses that could cost you. Turn a rental contract
              into clear explanations, grounded evidence, and dates worth
              remembering.
            </p>
            <div className="hero-actions">
              <Link className="button" to="/register">
                Explore your contract <ArrowRight size={18} />
              </Link>
              <a className="text-link" href="#how-it-works">
                See how it works
              </a>
            </div>
            <div className="hero-note">
              <ShieldCheck size={15} /> English and German · Residential rentals
            </div>
          </div>
          <div className="hero-visual">
            <div className="visual-label">
              <span className="live-dot" /> ANALYSIS PREVIEW{" "}
              <span>Illustrative example</span>
            </div>
            <div className="preview-card">
              <div className="preview-file">
                <span className="document-icon">
                  <FileText size={24} />
                </span>
                <div>
                  <strong>Sample rental agreement</strong>
                  <span>Synthetic English contract</span>
                </div>
                <span className="status-tag completed">Reviewed</span>
              </div>
              <div className="preview-summary">
                <div>
                  <span className="eyebrow">RULE-BASED RISK</span>
                  <p>Something to look at.</p>
                </div>
                <span className="big-score">
                  4<span>/5</span>
                </span>
              </div>
              <div className="preview-finding">
                <div>
                  <span className="tiny-square amber" /> Auto-renewal{" "}
                  <span className="mini-tag">Elevated</span>
                </div>
                <p>
                  Your lease renews for another year unless you give notice at
                  least 60 calendar days before it ends.
                </p>
                <blockquote>
                  <Quote size={14} /> “This lease automatically renews for a
                  further twelve months…”
                </blockquote>
                <span className="preview-caption">
                  Excerpt shown for illustration; app findings show full quotes.
                </span>
              </div>
              <div className="preview-date">
                <CalendarDays size={18} />
                <div>
                  <strong>Renewal notice deadline</strong>
                  <span>Calculated from the contract’s stated dates</span>
                </div>
                <ArrowUpRight size={16} />
              </div>
            </div>
            <div className="floating-note">
              <span>
                <Check size={15} />
              </span>{" "}
              Evidence you can check.
            </div>
          </div>
        </section>
        <section className="trust-strip">
          <span>LESS GUESSWORK. MORE CONTEXT.</span>
          <div>
            <Quote size={18} /> Exact clause evidence
          </div>
          <div>
            <ShieldCheck size={18} /> Consistent risk rules
          </div>
          <div>
            <CalendarDays size={18} /> Important dates
          </div>
        </section>
        <section className="how-section" id="how-it-works">
          <div className="section-intro">
            <div>
              <span className="eyebrow">FROM PDF TO PERSPECTIVE</span>
              <h2>A clearer view in three steps.</h2>
            </div>
            <p>
              Seven rule categories, plus AI assessment.
              <br />
              One place to understand them.
            </p>
          </div>
          <div className="step-grid">
            {[
              {
                n: "01",
                icon: FileText,
                title: "Bring your rental contract",
                text: "Upload an English or German text-based rental PDF, or start with a synthetic example.",
              },
              {
                n: "02",
                icon: ScanLine,
                title: "Let Radar read the details",
                text: "We verify quotes, apply transparent rules, and assess additional conditions separately.",
              },
              {
                n: "03",
                icon: ShieldCheck,
                title: "See what deserves attention",
                text: "Review plain-English explanations, evidence, and supported deadlines.",
              },
            ].map(({ n, icon: Icon, title, text }) => (
              <article className="step-card" key={n}>
                <div className="step-top">
                  <Icon size={22} />
                  <span>{n}</span>
                </div>
                <h3>{title}</h3>
                <p>{text}</p>
              </article>
            ))}
          </div>
        </section>
        <section className="demo-banner">
          <div>
            <span className="eyebrow">A PORTFOLIO PROJECT WITH A PURPOSE</span>
            <h2>Read with more confidence.</h2>
            <p>
              Explore how evidence-first analysis can make a rental contract
              easier to understand.
            </p>
          </div>
          <Link className="button light" to="/register">
            Start with a sample <ArrowRight size={18} />
          </Link>
        </section>
      </main>
      <Footer />
    </div>
  );
}
