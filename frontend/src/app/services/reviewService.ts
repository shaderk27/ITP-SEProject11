import type { User } from "../context/AuthContext";
import type {
  CommitResponse,
  CorrectionRequest,
  CorrectionResponse,
  QueueItemDetail,
  ReviewBatchDetail,
  ReviewBatchSummary,
} from "../types/review";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

/**
 * Header pattern mirrors uploadService.ts so the same demo-login email
 * works for both. When real auth (W7-02) ships, this whole block becomes
 * an Authorization: Bearer token instead.
 */
function userHeaders(user: User | null): HeadersInit {
  return {
    "X-User-Email": user?.email ?? "demo.teamlead@sit.edu.sg",
    "X-User-Name": user?.name ?? "Demo Team Lead",
    "X-User-Role": user?.role ?? "teamlead",
  };
}

export async function listReviewBatches(user: User | null): Promise<ReviewBatchSummary[]> {
  const response = await fetch(`${API_BASE_URL}/api/review/batches`, {
    headers: userHeaders(user),
  });

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(detail || `Failed to load review batches (${response.status}).`);
  }

  return response.json();
}

export async function getBatchDetail(batchId: number, user: User | null): Promise<ReviewBatchDetail> {
  const response = await fetch(`${API_BASE_URL}/api/review/batches/${batchId}`, {
    headers: userHeaders(user),
  });

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(detail || `Failed to load batch detail (${response.status}).`);
  }

  return response.json();
}

export async function getQueueItem(itemId: number, user: User | null): Promise<QueueItemDetail> {
  const response = await fetch(`${API_BASE_URL}/api/review/queue/${itemId}`, {
    headers: userHeaders(user),
  });

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(detail || `Failed to load queue item (${response.status}).`);
  }

  return response.json();
}

export async function saveCorrection(
  itemId: number,
  body: CorrectionRequest,
  user: User | null,
): Promise<CorrectionResponse> {
  const response = await fetch(`${API_BASE_URL}/api/review/queue/${itemId}/correct`, {
    method: "POST",
    headers: {
      ...userHeaders(user),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(detail || `Failed to save correction (${response.status}).`);
  }

  return response.json();
}

export async function commitBatch(batchId: number, user: User | null): Promise<CommitResponse> {
  const response = await fetch(`${API_BASE_URL}/api/review/batches/${batchId}/commit`, {
    method: "POST",
    headers: userHeaders(user),
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
