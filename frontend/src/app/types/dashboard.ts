export interface LabGroupSummary {
  id: number;
  name: string;
  wbs_code: string;
  description: string;
  budget: number;
  threshold: number;
}

export interface SpendingSummary {
  total_actual_spend_sgd: string;
  by_lab_group: Record<string, string>;
  total_pending_sgd: string;
  pending_by_lab_group: Record<string, string>;
}
