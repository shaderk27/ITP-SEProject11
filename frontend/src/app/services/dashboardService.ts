import type {
  BreakdownResponse,
  LabGroupSummary,
  SpendingSummary,
} from "../types/dashboard";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export async function listLabGroups(): Promise<LabGroupSummary[]> {
  const response = await fetch(`${API_BASE_URL}/api/config/labgroups`, {
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(`Failed to load lab groups (${response.status}).`);
  }

  const raw = await response.json();
  return (raw as LabGroupSummary[]).map((g) => ({
    ...g,
    budget: Number(g.budget) || 0,
  }));
}

function dateRangeQuery(
  dateRange: string,
  startDate: string,
  endDate: string,
): string {
  const params = new URLSearchParams();
  if (startDate || endDate) {
    // Custom range overrides the preset.
    if (startDate) params.set("start_date", startDate);
    if (endDate) params.set("end_date", endDate);
  } else if (dateRange && dateRange !== "all") {
    params.set("date_range", dateRange);
  }
  return params.toString() ? `?${params.toString()}` : "";
}

export async function getSpendingSummary(
  dateRange: string = "all",
  startDate: string = "",
  endDate: string = "",
): Promise<SpendingSummary> {
  const response = await fetch(
    `${API_BASE_URL}/api/dashboard/spending${dateRangeQuery(dateRange, startDate, endDate)}`,
    { credentials: "include" },
  );

  if (!response.ok) {
    throw new Error(`Failed to load spending summary (${response.status}).`);
  }

  return response.json();
}

export async function getBreakdown(
  dateRange: string = "all",
  startDate: string = "",
  endDate: string = "",
): Promise<BreakdownResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/dashboard/breakdown${dateRangeQuery(dateRange, startDate, endDate)}`,
    { credentials: "include" },
  );

  if (!response.ok) {
    throw new Error(`Failed to load dashboard breakdown (${response.status}).`);
  }

  return response.json();
}
