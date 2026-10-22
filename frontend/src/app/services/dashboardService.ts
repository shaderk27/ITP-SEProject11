import type {
  BreakdownResponse,
  LabGroupSummary,
  SpendingSummary,
} from "../types/dashboard";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export async function listLabGroups(
  periodId?: number | null,
): Promise<LabGroupSummary[]> {
  const query = periodId != null ? `?period_id=${periodId}` : "";
  const response = await fetch(`${API_BASE_URL}/api/config/labgroups${query}`, {
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

export interface Period {
  id: number;
  name: string;
  year: number;
  start_date: string;
  end_date: string;
  is_closed: boolean;
}

export async function listPeriods(): Promise<Period[]> {
  const response = await fetch(`${API_BASE_URL}/api/config/periods`, {
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(`Failed to load fiscal years (${response.status}).`);
  }
  return response.json();
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
  periodId?: number | null,
): Promise<BreakdownResponse> {
  const base = dateRangeQuery(dateRange, startDate, endDate);
  const query =
    periodId != null
      ? base
        ? `${base}&period_id=${periodId}`
        : `?period_id=${periodId}`
      : base;
  const response = await fetch(
    `${API_BASE_URL}/api/dashboard/breakdown${query}`,
    { credentials: "include" },
  );

  if (!response.ok) {
    throw new Error(`Failed to load dashboard breakdown (${response.status}).`);
  }

  return response.json();
}

export interface MonthlyPoint {
  month: string; // "YYYY-MM"
  amount: string;
}

export async function getMonthly(
  startDate: string = "",
  endDate: string = "",
  labGroupId?: number | null,
  labId?: number | null,
): Promise<MonthlyPoint[]> {
  const params = new URLSearchParams();
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  if (labGroupId != null) params.set("lab_group_id", String(labGroupId));
  if (labId != null) params.set("lab_id", String(labId));
  const q = params.toString() ? `?${params.toString()}` : "";
  const response = await fetch(`${API_BASE_URL}/api/dashboard/monthly${q}`, {
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(`Failed to load monthly trend (${response.status}).`);
  }
  const data = await response.json();
  return data.points as MonthlyPoint[];
}

/** Dashboard filter state, forwarded to the Excel export endpoint. */
export interface DashboardExportFilters {
  /** Effective window, already clamped to the selected fiscal year. */
  startDate: string;
  endDate: string;
  dateRange: string;
  periodId: number | null;
  /** Lab Group dropdown — null when "All Lab Groups". */
  labGroupId: number | null;
  /** Lab dropdown — null when "All labs". */
  labId: number | null;
  /** Raw custom range as typed, for the cover block. */
  customStart: string;
  customEnd: string;
}

/**
 * Download the dashboard as a styled .xlsx workbook.
 *
 * The backend rebuilds the numbers by calling the very same scoped functions
 * the dashboard's own endpoints use, so the file cannot show more than the
 * caller's role allows. Returns the saved filename for the success toast.
 */
export async function exportDashboard(
  filters: DashboardExportFilters,
): Promise<string> {
  const params = new URLSearchParams();
  if (filters.startDate) params.set("start_date", filters.startDate);
  if (filters.endDate) params.set("end_date", filters.endDate);
  if (filters.dateRange) params.set("date_range", filters.dateRange);
  // 0 = All time; it must be sent, not dropped as falsy.
  if (filters.periodId != null) params.set("period_id", String(filters.periodId));
  if (filters.labGroupId != null)
    params.set("lab_group_id", String(filters.labGroupId));
  if (filters.labId != null) params.set("lab_id", String(filters.labId));
  if (filters.customStart) params.set("custom_start", filters.customStart);
  if (filters.customEnd) params.set("custom_end", filters.customEnd);

  const response = await fetch(
    `${API_BASE_URL}/api/dashboard/export?${params.toString()}`,
    { credentials: "include" },
  );

  if (!response.ok) {
    let detail = "";
    try {
      const body = await response.json();
      detail = typeof body?.detail === "string" ? body.detail : "";
    } catch {
      // Non-JSON error body; fall back to the status code.
    }
    throw new Error(detail || `Export failed (${response.status}).`);
  }

  const blob = await response.blob();
  const header = response.headers.get("Content-Disposition");
  const filename = filenameFromDisposition(header) ?? "Dashboard.xlsx";

  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
  return filename;
}

/** Pull the server-supplied filename out of the Content-Disposition header. */
function filenameFromDisposition(header: string | null): string | null {
  if (!header) return null;
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (encoded?.[1]) {
    try {
      return decodeURIComponent(encoded[1].trim());
    } catch {
      // Fall through to the plain form.
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header);
  return plain?.[1]?.trim() ?? null;
}
