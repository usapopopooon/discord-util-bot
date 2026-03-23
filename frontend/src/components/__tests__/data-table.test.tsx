import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { DataTable, type Column } from "../data-table";

interface TestRow {
  id: number;
  name: string;
  status: string;
}

const columns: Column<TestRow>[] = [
  { header: "ID", accessor: (row) => row.id },
  { header: "Name", accessor: (row) => row.name },
  { header: "Status", accessor: (row) => row.status },
];

const testData: TestRow[] = [
  { id: 1, name: "Alice", status: "active" },
  { id: 2, name: "Bob", status: "inactive" },
];

describe("DataTable", () => {
  it("renders column headers", () => {
    render(<DataTable columns={columns} data={testData} />);

    expect(screen.getByText("ID")).toBeInTheDocument();
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("Status")).toBeInTheDocument();
  });

  it("renders data rows", () => {
    render(<DataTable columns={columns} data={testData} />);

    expect(screen.getByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("Bob")).toBeInTheDocument();
    expect(screen.getByText("active")).toBeInTheDocument();
    expect(screen.getByText("inactive")).toBeInTheDocument();
  });

  it("renders all cell values with correct accessor", () => {
    render(<DataTable columns={columns} data={testData} />);

    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("shows default empty message when data is empty", () => {
    render(<DataTable columns={columns} data={[]} />);

    expect(screen.getByText("No data found")).toBeInTheDocument();
  });

  it("shows custom empty message when provided", () => {
    render(<DataTable columns={columns} data={[]} emptyMessage="Nothing to display" />);

    expect(screen.getByText("Nothing to display")).toBeInTheDocument();
  });

  it("renders the correct number of data rows", () => {
    const { container } = render(<DataTable columns={columns} data={testData} />);

    // Header row + 2 data rows
    const rows = container.querySelectorAll("tr");
    expect(rows).toHaveLength(3);
  });

  it("renders empty state with colspan spanning all columns", () => {
    const { container } = render(<DataTable columns={columns} data={[]} />);

    const td = container.querySelector("td");
    expect(td).toHaveAttribute("colspan", "3");
  });

  it("handles columns with custom accessor rendering JSX", () => {
    const columnsWithJsx: Column<TestRow>[] = [
      {
        header: "Badge",
        accessor: (row) => <span data-testid="badge">{row.status}</span>,
      },
    ];

    render(<DataTable columns={columnsWithJsx} data={testData} />);

    const badges = screen.getAllByTestId("badge");
    expect(badges).toHaveLength(2);
    expect(badges[0]).toHaveTextContent("active");
    expect(badges[1]).toHaveTextContent("inactive");
  });
});
