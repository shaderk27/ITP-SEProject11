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
