import type { LabGroupSummary, SpendingSummary } from "../types/dashboard";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export async function listLabGroups(): Promise<LabGroupSummary[]> {
  const response = await fetch(`${API_BASE_URL}/api/config/labgroups`);

  if (!response.ok) {
    throw new Error(`Failed to load lab groups (${response.status}).`);
  }

  const raw = await response.json();
  return (raw as LabGroupSummary[]).map((g) => ({
    ...g,
    budget: Number(g.budget) || 0,
  }));
}

export async function getSpendingSummary(): Promise<SpendingSummary> {
  const response = await fetch(`${API_BASE_URL}/api/dashboard/spending`, {
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(`Failed to load spending summary (${response.status}).`);
  }

  return response.json();
}
