export interface UploadValidationError {
  field: string;
  message: string;
  severity: "error" | "warning";
}

export interface UploadLineItem {
  row_number: number;
  pr_number: string;
  pr_sub_date: string;
  requestor: string;
  purpose: string;
  grand_total_sgd: string | null;
  item_details: string;
  quantity: string | null;
  unit_rate: string | null;
  wbs: string;
  instruction_to_vendor: string;
  pr_category: string;
  lab: string;
  lab_group?: string;
  classification_reason?: string;
  amount_gst: string;
  line_identity_key: string;
  content_hash: string;
}

export interface UploadRecordResult {
  status: "inserted" | "updated" | "duplicate";
  reason: string;
  line: UploadLineItem;
  previous_batch_id: string | null;
}

export interface UploadProcessResult {
  success: boolean;
  metadata: {
    batch_id: string;
    filename: string;
    uploader_email: string;
    uploader_name: string;
    uploader_role: string;
    uploaded_at: string;
    files?: Array<{
      batch_id: string;
      filename: string;
      uploader_email: string;
      uploader_name: string;
      uploader_role: string;
      uploaded_at: string;
    }>;
  };
  counts: {
    total_lines: number;
    accepted: number;
    duplicate_skipped: number;
    reupload_updated: number;
    needs_review: number;
    rejected: number;
  };
  validation_errors: UploadValidationError[];
  records: {
    inserted: UploadRecordResult[];
    updated: UploadRecordResult[];
    duplicate: UploadRecordResult[];
  };
}
