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

// Drilldown breakdown — same 6 metrics at every level (Lab Group → Lab → Category)
export interface BreakdownMetrics {
  budget_sgd: string;
  actual_spend_sgd: string;
  pending_sgd: string;
  available_balance_sgd: string;
  utilisation_pct: number;
  projected_utilisation_pct: number;
}

export interface BreakdownCategory extends BreakdownMetrics {
  // null when a committed line's category could not be resolved ("Uncategorised").
  category_id: number | null;
  category_name: string;
}

export interface BreakdownLab extends BreakdownMetrics {
  lab_id: number;
  lab_name: string;
  categories: BreakdownCategory[];
}

export interface BreakdownLabGroup extends BreakdownMetrics {
  lab_group_id: number;
  lab_group_name: string;
  labs: BreakdownLab[];
}

export interface BreakdownResponse {
  lab_groups: BreakdownLabGroup[];
}
