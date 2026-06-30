import type { CommittedPR } from "../types/records";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

const FETCH_OPTS: RequestInit = { credentials: "include" };

export async function listCommittedPRs(
  dateRange: string = "all",
): Promise<CommittedPR[]> {
  const query =
    dateRange && dateRange !== "all"
      ? `?date_range=${encodeURIComponent(dateRange)}`
      : "";
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
