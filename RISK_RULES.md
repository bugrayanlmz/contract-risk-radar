# Risk rules v1.0

These rules are software heuristics for synthetic residential rental contracts. They are not jurisdiction-specific legal limits, enforceability judgments, or legal advice.

## Evidence and missing information

Every clause needs an exact normalized substring match against extracted PDF text before it can contribute to scores or dates. Contract-level amounts and dates also need verified supporting quotes. Text verification establishes presence, not semantic accuracy.

Normalization uses Unicode NFKC, straight quotation marks, letter-to-letter dehyphenation across line breaks, and collapsed whitespace. It preserves case, punctuation, and same-line hyphens. It uses no fuzzy matching.

Each clause receives the maximum triggered severity, never a sum. A score of 1 requires at least one usable scoring input and no escalation from the available inputs. Unknown inputs produce warnings and a partial score. No usable inputs or an unverified quote produces no score. False is an observed fact; null is unknown.

The overall score is the highest non-null clause score. No scorable clauses means an unavailable overall score. A missing category is “Not found,” not “Safe.”

## Thresholds

| Category | Rule | Severity |
|---|---|---|
| Auto-renewal | Explicitly automatic | 2 |
| Auto-renewal | Automatic renewal lasts 6–11 months | 3 |
| Auto-renewal | Automatic renewal lasts at least 12 months | 4 |
| Auto-renewal | Automatic renewal requires over 30 through 60 calendar days' notice | 3 |
| Auto-renewal | Automatic renewal requires over 60 calendar days' notice | 4 |
| Early termination | Fee greater than zero through one month's rent | 2 |
| Early termination | Fee over one through two months' rent | 3 |
| Early termination | Fee over two months' rent | 4 |
| Early termination | Prohibited, or all remaining rent is due | 5 |
| Security deposit | Canonical deposit over one through two months' rent | 3 |
| Security deposit | Canonical deposit over two months' rent | 4 |
| Security deposit | Return period exceeds 30 calendar days | 3 |
| Security deposit | Unrestricted deductions | 4 |
| Security deposit | Explicitly nonrefundable | 5 |
| Late payment | Fee greater than zero through 5% of monthly rent | 2 |
| Late payment | Fee over 5% through 10% | 3 |
| Late payment | Fee over 10% | 4 |
| Late payment | Explicit zero calendar-day grace period | 3 |
| Late payment | Daily accrual | 5 |
| Rent increase | Increase greater than zero through 5% of monthly rent | 2 |
| Rent increase | Increase over 5% through 10% | 3 |
| Rent increase | Increase over 10% | 4 |
| Rent increase | Allowed at intervals shorter than 12 months | 4 |
| Rent increase | Explicitly uncapped | 5 |
| Landlord termination | Without cause | 4 |
| Landlord termination | Notice of 7–29 calendar days | 3 |
| Landlord termination | Notice of fewer than 7 calendar days | 5 |
| Tenant liability | Explicitly includes normal wear | 3 |
| Tenant liability | Includes structural repairs | 4 |
| Tenant liability | Unlimited or includes landlord negligence | 5 |

Renewal duration and notice triggers require automatic renewal to be true. Rent-increase amounts and caps are not evaluated when increases are explicitly prohibited; interval escalation requires permission to be explicitly true. Other terms can be evaluated independently when stated. These gates prevent unrelated numbers from escalating a score.

Examples: a 12-month automatic renewal with 60 calendar days of notice scores 4 (length), with both risk factors shown. A 10% one-time late fee scores 3; 10.0001% scores 4. A refundable USD 2,000 deposit against verified USD 1,000 rent scores 3; USD 2,000.0001 scores 4. A fully unknown landlord notice period contributes no notice factor.

## Amounts, periods, and calculations

Money uses decimals with at most four fractional digits. Monetary ratios require a positive verified monthly rent and the same explicitly established ISO currency on both amounts. An ambiguous `$` symbol does not establish USD. Never perform currency conversion. A fee stated directly in months of rent or as a percentage needs no inferred monetary amount.

Fixed money and percentage/months-of-rent alternatives are mutually exclusive representations of one fee or increase. Complex, conditional, or compound formulas remain null rather than being guessed. Explicit calendar-day periods alone drive day-based thresholds. Business-day and unspecified periods are not converted or treated as zero.

## Dates

Verified canonical start/end dates appear directly. Renewal notice deadlines subtract the stated calendar-day notice from the verified contract end date only when that anchor is explicit. Calendar subtraction handles leap years and year boundaries. Rent-increase effective dates require verified clause evidence. Each date includes its calculation basis and references.

Do not assume move-out equals lease end, exercise a future renewal, calculate unspecified payment dates, or convert business-day periods. Deposit-return dates remain unresolved until an actual move-out date exists. Tracking is an in-app timeline, without notifications.

## Limits

The LLM can miss clauses or misinterpret evidence even when quotes verify. Image-only pages and missing facts create evidence gaps. A low observed score does not establish a safe or enforceable contract. Changing rules requires a new version and corresponding boundary tests; stored results retain their original version.

## Separate additional AI assessment — rubric 1.0

The seven deterministic categories and thresholds above remain version 1.0. A ninth provider request assesses important practical conditions outside the observed rule findings. It receives the original English/German document and a structured summary of rule coverage; it must avoid repeating those issues. Original-language quotes must be short contiguous passages, with English explanations, titles, rationale, and explicit uncertainty. No legal validity or jurisdiction-specific legal determination is requested.

| Model score | Observed practical impact |
|---|---|
| 1 | Low observed burden |
| 2 | Limited burden |
| 3 | Material but bounded burden |
| 4 | Serious potential impact |
| 5 | Extreme or unbounded potential impact |

For example, a small compulsory equipment purchase can have limited impact; mandatory disclosure of all private bank statements can have serious impact; unlimited unrelated charges can have extreme impact. These examples describe the rubric, not fixed score rules. AI judgments may vary across models/runs and can miss issues or misinterpret evidence.

At most 20 additional findings are accepted. Duplicate normalized quote/title pairs are removed; one passage may support distinct issues. Every quote passes the same exact verification as rule evidence (NFKC, curly/German quotation marks, line-break hyphenation, collapsed whitespace; case and umlauts/ß preserved). Unverified candidates retain the model score for inspection but their displayed score is null, with a warning. `ai_overall_score` is the maximum verified additional score or null. An empty AI list means no additional issues were identified, not that the document is safe.

`overall_score` summarizes only deterministic clauses. No combined overall score is produced. Additional AI findings do not drive canonical amounts or date calculations. Evidence text verification cannot validate interpretation, facts not supported by the quote, or legal effect. PDF highlights require verification and a displayed score of 2–5; missing viewer coordinates do not change the backend verification result.
