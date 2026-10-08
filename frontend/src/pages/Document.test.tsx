import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { ClauseResult } from "../api/generated/types.gen";
import { Finding } from "./Document";

afterEach(cleanup);

const finding: ClauseResult = {
  id: "00000000-0000-0000-0000-000000000001",
  clause: {
    category: "LATE_PAYMENT",
    quote: "<script>window.compromised=true</script>",
    explanation: "A quoted clause can contain untrusted markup.",
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
  warnings: ["Quote could not be verified; excluded from scoring."],
};

describe("Evidence display", () => {
  it("escapes contract text and shows unverified quotes without a score", () => {
    const { container } = render(<Finding finding={finding} />);
    expect(screen.getByText(finding.clause.quote)).toBeInTheDocument();
    expect(container.querySelector("script")).toBeNull();
    expect(screen.getByText("Unverified quote")).toBeInTheDocument();
    expect(screen.getByText("Not scored")).toBeInTheDocument();
    expect(screen.getByText("Incomplete inputs")).toBeInTheDocument();
  });

  it("keeps partial scoring separate from quote verification", () => {
    render(
      <Finding
        finding={{
          ...finding,
          quote_verified: true,
          score: 5,
          risk_factors: [
            {
              code: "DAILY_LATE_FEE",
              severity: 5,
              explanation: "Late fees accrue daily.",
              inputs: { accrues_daily: true },
            },
          ],
        }}
      />,
    );
    expect(screen.getByText("Text verified")).toBeInTheDocument();
    expect(screen.getByText("5 / 5")).toBeInTheDocument();
    expect(screen.getByText("Late fees accrue daily.")).toBeInTheDocument();
    expect(screen.getByText("Incomplete inputs")).toBeInTheDocument();
  });
});
