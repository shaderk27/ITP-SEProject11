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

export interface LabGroupOption {
  lab_group_id: number;
  lab_group_name: string;
  wbs_code: string;
}

export interface LabOption {
  lab_id: number;
  lab_name: string;
  lab_group_id: number;
  is_general: boolean;
}

export interface CategoryOption {
  category_id: number;
  category_name: string;
}

export interface LastReviewAction {
  reviewer_name: string;
  reviewed_at: string;
  comment: string | null;
  action_type: string;
}

export interface QueueItemDetail {
  review_queue_id: number;
  queue_status: string;
  review_reason: string;
  batch_upload_status: string;
  last_action: LastReviewAction | null;
  staging_line_id: number;
  source_line_no: number | null;
  item_details: string;
  amount_gst: string;
  qty: string | null;
  unit_rate: string | null;
  raw_pr_category: string | null;
  source_pr_number: string;
  requestor_name: string;
  purpose: string;
  wbs_code: string;
  instruction_to_vendor: string;
  pr_sub_date: string | null;
  batch_id: number;
  batch_filename: string;
  suggested_lab_group_id: number | null;
  suggested_lab_id: number | null;
  suggested_category_id: number | null;
  current_lab_group: string;
  current_lab: string;
  current_category: string;
  is_lab_group_general: boolean;
  is_lab_general: boolean;
  is_category_general: boolean;
  available_lab_groups: LabGroupOption[];
  available_labs: LabOption[];
  available_categories: CategoryOption[];
}

export interface CorrectionRequest {
  lab_group_id: number;
  lab_id: number;
  category_id: number;
  comment?: string;
}

export interface CorrectionResponse {
  success: boolean;
  review_queue_id: number;
  new_queue_status: string;
  batch_remaining_open: number;
}

export interface CommitResponse {
  success: boolean;
  batch_id: number;
  new_upload_status: string;
  prs_created: number;
  prs_updated: number;
  lines_created: number;
  pr_ids: number[];
}
