import type {
  AnalysisResponse,
  DocumentResponse,
} from "../src/api/generated/types.gen";

export const document: DocumentResponse = {
  id: "00000000-0000-4000-8000-000000000001",
  document_kind: "synthetic",
  filename: "balanced-lease.pdf",
  status: "processing",
  stage: "queued",
  error_code: null,
  error_message: null,
  retryable: false,
  created_at: "2026-10-07T18:00:00Z",
  updated_at: "2026-10-07T18:00:00Z",
  completed_at: null,
};

export const results: AnalysisResponse = {
  document_id: document.id,
  facts: {
    start_date: "2027-01-01",
    end_date: "2027-12-31",
    monthly_rent: { amount: "1500", currency: "USD" },
    deposit_amount: null,
    evidence: {
      start_date: "Starts January 1, 2027.",
      end_date: "Ends December 31, 2027.",
      monthly_rent: "Monthly rent is USD 1500.",
      deposit_amount: null,
    },
    warnings: [],
    contract_type: "residential_rental",
    language: "english",
  },
  field_evidence: {
    start_date: { quote: "Starts January 1, 2027.", verified: true },
    end_date: { quote: "Ends December 31, 2027.", verified: true },
    monthly_rent: { quote: "Monthly rent is USD 1500.", verified: true },
    deposit_amount: { quote: null, verified: false },
  },
  overall_score: 4,
  ai_overall_score: null,
  ai_review_status: "not_run",
  ai_rubric_version: null,
  ai_findings: [],
  clauses: [
    {
      id: "00000000-0000-4000-8000-000000000002",
      clause: {
        category: "AUTO_RENEWAL",
        quote: "The lease automatically renews for twelve months.",
        explanation:
          "The lease renews for another year unless the required notice is given.",
        attributes: {
          automatic: true,
          renewal_months: 12,
          notice_days: null,
          notice_day_basis: null,
          notice_anchor: null,
        },
      },
      quote_verified: true,
      score: 4,
      partial: true,
      risk_factors: [
        {
          code: "RENEWAL_LENGTH",
          severity: 4,
          explanation:
            "Automatic renewal commits the tenant to another extended term.",
          inputs: { renewal_months: 12 },
        },
      ],
      warnings: ["Not evaluated: notice_days."],
    },
    {
      id: "00000000-0000-4000-8000-000000000003",
      clause: {
        category: "LATE_PAYMENT",
        quote: "An invented late payment clause.",
        explanation: "This returned quote could not be verified.",
        attributes: {
          fee_amount: null,
          fee_percent_of_rent: null,
          grace_days: null,
          grace_day_basis: null,
          accrues_daily: true,
        },
      },
      quote_verified: false,
      score: null,
      partial: true,
      risk_factors: [],
      warnings: ["Unverified quote excluded from scoring and dates."],
    },
  ],
  important_dates: [
    {
      id: "00000000-0000-4000-8000-000000000004",
      clause_id: null,
      kind: "contract_end",
      date: "2027-12-31",
      basis: "Verified contract end date.",
      source_references: ["end_date"],
    },
  ],
  categories_not_found: [
    "TENANT_LIABILITY",
    "RENT_INCREASE",
    "EARLY_TERMINATION",
    "SECURITY_DEPOSIT",
    "LANDLORD_TERMINATION",
  ],
  warnings: [
    "Analysis has evidence gaps; overall score summarizes observed, scorable findings.",
  ],
  provider: "claude",
  model: "browser-test-fixture",
  prompt_version: "1.0",
  schema_version: "1.0",
  rules_version: "1.0",
};
