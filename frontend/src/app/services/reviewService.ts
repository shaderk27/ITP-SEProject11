import type {
  CommitResponse,
  CorrectionRequest,
  CorrectionResponse,
  QueueItemDetail,
  ReviewBatchDetail,
  ReviewBatchSummary,
} from "../types/review";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

// All calls ship the `access_token` JWT cookie set by /api/auth/login.
// Backend resolves the user from that cookie (see dependencies/auth.py).
const FETCH_OPTS: RequestInit = { credentials: "include" };

export async function listReviewBatches(): Promise<ReviewBatchSummary[]> {
  const response = await fetch(`${API_BASE_URL}/api/review/batches`, FETCH_OPTS);

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(detail || `Failed to load review batches (${response.status}).`);
  }

  return response.json();
}

export async function getBatchDetail(batchId: number): Promise<ReviewBatchDetail> {
  const response = await fetch(`${API_BASE_URL}/api/review/batches/${batchId}`, FETCH_OPTS);

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(detail || `Failed to load batch detail (${response.status}).`);
  }

  return response.json();
}

export async function getQueueItem(itemId: number): Promise<QueueItemDetail> {
  const response = await fetch(`${API_BASE_URL}/api/review/queue/${itemId}`, FETCH_OPTS);

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(detail || `Failed to load queue item (${response.status}).`);
  }

  return response.json();
}

export async function saveCorrection(
  itemId: number,
  body: CorrectionRequest,
): Promise<CorrectionResponse> {
  const response = await fetch(`${API_BASE_URL}/api/review/queue/${itemId}/correct`, {
    ...FETCH_OPTS,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(detail || `Failed to save correction (${response.status}).`);
  }

  return response.json();
}

export async function commitBatch(batchId: number): Promise<CommitResponse> {
  const response = await fetch(`${API_BASE_URL}/api/review/batches/${batchId}/commit`, {
    ...FETCH_OPTS,
    method: "POST",
  });

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(detail || `Failed to commit batch (${response.status}).`);
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
