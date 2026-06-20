/**
 * Types matching the backend's /api/review/* responses.
 * Keep these in sync with backend/app/api/review.py.
 */

export interface ReviewBatchSummary {
  batch_id: number;
  filename: string;
  upload_status: string;
  uploaded_at: string;   // ISO timestamp
  uploader_name: string;
  total_lines: number;
  open_queue_count: number;
}

export interface ReviewQueueLine {
  review_queue_id: number;
  staging_line_id: number;
  source_line_no: number | null;
  item_details: string;
  amount_gst: string;        // Decimal as string for safe transport
  wbs_code: string;
  current_lab_group: string;
  current_lab: string;
  current_category: string;
  is_lab_group_general: boolean;
  is_lab_general: boolean;
  is_category_general: boolean;
  review_reason: string;
  queue_status: string;
}

export interface ReviewPRGroup {
  source_pr_number: string;
  requestor_name: string;
  purpose: string;
  wbs_code: string;
  lines: ReviewQueueLine[];
}

export interface ReviewBatchDetail {
  batch_id: number;
  filename: string;
  upload_status: string;
  uploaded_at: string;
  uploader_name: string;
  prs: ReviewPRGroup[];
}
