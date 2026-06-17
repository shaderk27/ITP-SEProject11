import type { User } from "../context/AuthContext";
import type { UploadProcessResult } from "../types/upload";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export async function processUpload(file: File, user: User | null): Promise<UploadProcessResult> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}/api/uploads/process`, {
    method: "POST",
    headers: {
      "X-User-Email": user?.email ?? "demo.teamlead@sit.edu.sg",
      "X-User-Name": user?.name ?? "Demo Team Lead",
      "X-User-Role": user?.role ?? "teamlead",
    },
    body: formData,
  });

  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? "Upload failed. Please try again.");
  }

  return response.json();
}
