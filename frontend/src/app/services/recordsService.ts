import type { User } from "../context/AuthContext";
import type { CommittedPR } from "../types/records";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

function userHeaders(user: User | null): HeadersInit {
  return {
    "X-User-Email": user?.email ?? "demo.teamlead@sit.edu.sg",
    "X-User-Name": user?.name ?? "Demo Team Lead",
    "X-User-Role": user?.role ?? "teamlead",
  };
}

export async function listCommittedPRs(user: User | null): Promise<CommittedPR[]> {
  const response = await fetch(`${API_BASE_URL}/api/records/prs`, {
    headers: userHeaders(user),
  });

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
