import { render, screen } from "@testing-library/react";

import { StatusBadge } from "../status-badge";

describe("StatusBadge", () => {
  it("renders the correct status label", () => {
    render(<StatusBadge status="PENDING" />);
    expect(screen.getByText(/pending/i)).toBeInTheDocument();
  });
});


