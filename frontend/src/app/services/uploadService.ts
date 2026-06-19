import type { User } from "../context/AuthContext";
import type { UploadProcessResult } from "../types/upload";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

function userHeaders(user: User | null) {
  return {
    "X-User-Email": user?.email ?? "demo.teamlead@sit.edu.sg",
    "X-User-Name": user?.name ?? "Demo Team Lead",
    "X-User-Role": user?.role ?? "teamlead",
  };
}

export async function processUpload(file: File, user: User | null): Promise<UploadProcessResult> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}/api/uploads/process`, {
    method: "POST",
    headers: userHeaders(user),
    body: formData,
  });

  if (!response.ok) {
    throw new Error(await readUploadError(response));
  }

  return response.json();
}

export async function processUploadBatch(files: File[], user: User | null): Promise<UploadProcessResult> {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));

  const response = await fetch(`${API_BASE_URL}/api/uploads/process-batch`, {
    method: "POST",
    headers: userHeaders(user),
    body: formData,
  });

  if (!response.ok) {
    throw new Error(await readUploadError(response));
  }

  return response.json();
}

async function readUploadError(response: Response) {
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    const detail = await response.json().catch(() => null);
    const message = Array.isArray(detail?.detail)
      ? detail.detail.map((item: { msg?: string }) => item.msg).filter(Boolean).join("; ")
      : detail?.detail;
    return message ? `Upload failed (${response.status}): ${message}` : `Upload failed (${response.status}).`;
  }

  const text = await response.text().catch(() => "");
  return text ? `Upload failed (${response.status}): ${text}` : `Upload failed (${response.status}).`;
}
