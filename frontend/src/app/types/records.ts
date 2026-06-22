/**
 * Types matching backend/app/api/records.py response shapes.
 * Keep in sync.
 */

export interface CommittedPRLine {
  pr_line_id: number;
  line_no: number | null;
  item_description: string;
  qty: string | null;
  unit_rate: string | null;
  amount_gst: string;
  currency_code: string;
  lab_name: string;
  category_name: string;
  source_staging_line_id: number | null;
}

export interface CommittedPR {
  pr_id: number;
  source_pr_number: string;
  requestor_name: string;
  purpose: string;
  wbs_code: string;
  grand_total_sgd: string;
  lab_group_name: string;
  latest_batch_id: number | null;
  updated_at: string;
  status: string;
  lines: CommittedPRLine[];
}
