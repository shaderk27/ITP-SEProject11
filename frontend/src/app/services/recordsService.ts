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

/** Filter state of the PR Records page, forwarded to the export endpoint. */
export interface ExportFilters {
  /** Effective window already clamped to the selected fiscal year. */
  startDate: string;
  endDate: string;
  /** Date Range preset ("all" | "30d" | "90d" | "ytd") — cover-block label. */
  dateRange: string;
  /** Free-text search box contents. */
  search: string;
  /** Lab Group dropdown value (lowercased group name, or "all"). */
  labGroup: string;
  /** Selected fiscal year, for the cover block. */
  periodId: number | null;
  /** Raw custom range as typed, so the cover can say "Custom: x to y". */
  customStart: string;
  customEnd: string;
}

/**
 * Download the currently-visible PR Records as a styled .xlsx workbook.
 *
 * The backend re-applies the same role scoping as the list endpoint, so the
 * file can never contain rows the user isn't allowed to see. Returns the
 * filename the browser saved, for the success toast.
 */
export async function exportCommittedPRs(
  filters: ExportFilters,
): Promise<string> {
  const params = new URLSearchParams();
  if (filters.startDate) params.set("start_date", filters.startDate);
  if (filters.endDate) params.set("end_date", filters.endDate);
  if (filters.dateRange) params.set("date_range", filters.dateRange);
  if (filters.search.trim()) params.set("search", filters.search.trim());
  if (filters.labGroup) params.set("lab_group", filters.labGroup);
  if (filters.periodId) params.set("period_id", String(filters.periodId));
  if (filters.customStart) params.set("custom_start", filters.customStart);
  if (filters.customEnd) params.set("custom_end", filters.customEnd);

  const response = await fetch(
    `${API_BASE_URL}/api/records/export?${params.toString()}`,
    FETCH_OPTS,
  );

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(detail || `Export failed (${response.status}).`);
  }

  const blob = await response.blob();
  const filename =
    filenameFromDisposition(response.headers.get("Content-Disposition")) ??
    "PR_Records.xlsx";
  triggerDownload(blob, filename);
  return filename;
}

/** Pull the server-supplied filename out of the Content-Disposition header. */
function filenameFromDisposition(header: string | null): string | null {
  if (!header) return null;
  // Prefer the RFC 5987 form, which is percent-encoded.
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

/** Save a blob to the user's downloads folder via a transient anchor. */
function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  // Revoke on the next tick so the download has a chance to start in Safari.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
