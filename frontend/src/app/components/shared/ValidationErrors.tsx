import { XCircle, AlertCircle } from "lucide-react";
import { Card } from "../ui/card";

interface ValidationError {
  field: string;
  message: string;
  severity: "error" | "warning";
}

interface ValidationErrorsProps {
  errors: ValidationError[];
}

export function ValidationErrors({ errors }: ValidationErrorsProps) {
  if (errors.length === 0) return null;

  const errorCount = errors.filter(e => e.severity === "error").length;
  const warningCount = errors.filter(e => e.severity === "warning").length;

  return (
    <Card className="p-4 bg-[#fef2f2] border-[#fecaca]">
      <div className="flex items-start gap-3">
        <XCircle className="h-5 w-5 text-[#dc2626] flex-shrink-0 mt-0.5" />
        <div className="flex-1">
          <h4 className="text-sm font-semibold text-[#dc2626] mb-2">
            File Validation Failed
          </h4>
          <p className="text-sm text-[#991b1b] mb-3">
            Found {errorCount} {errorCount === 1 ? 'error' : 'errors'} and {warningCount} {warningCount === 1 ? 'warning' : 'warnings'} in the uploaded file.
          </p>
          <div className="space-y-2">
            {errors.map((error, idx) => (
              <div
                key={idx}
                className="flex items-start gap-2 text-sm text-[#991b1b] p-2 bg-white/50 rounded"
              >
                {error.severity === "error" ? (
                  <XCircle className="h-4 w-4 flex-shrink-0 mt-0.5" />
                ) : (
                  <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5 text-[#d97706]" />
                )}
                <div>
                  <span className="font-medium">{error.field}:</span> {error.message}
                </div>
              </div>
            ))}
          </div>
          <p className="text-xs text-[#991b1b] mt-3">
            Please fix these issues and re-upload the file.
          </p>
        </div>
      </div>
    </Card>
  );
}
