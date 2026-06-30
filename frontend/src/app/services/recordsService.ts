import type { CommittedPR } from "../types/records";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

const FETCH_OPTS: RequestInit = { credentials: "include" };

export async function listCommittedPRs(
  dateRange: string = "all",
  startDate: string = "",
  endDate: string = "",
): Promise<CommittedPR[]> {
  const params = new URLSearchParams();
  if (startDate || endDate) {
    // Custom range overrides the preset.
    if (startDate) params.set("start_date", startDate);
    if (endDate) params.set("end_date", endDate);
  } else if (dateRange && dateRange !== "all") {
    params.set("date_range", dateRange);
  }
  const query = params.toString() ? `?${params.toString()}` : "";
  const response = await fetch(
    `${API_BASE_URL}/api/records/prs${query}`,
    FETCH_OPTS,
  );

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(detail || `Failed to load PR records (${response.status}).`);
  }

  return response.json();
}

async function readErrorDetail(response: Response): Promise<string> {
  try {
    const body = await response.json();
    return typeof body?.detail === "string" ? body.detail : "";
  } catch {
    return "";
  }
}
