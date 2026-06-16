import { AlertTriangle } from "lucide-react";
import { Card } from "../ui/card";

interface DuplicateWarningProps {
  count: number;
}

export function DuplicateWarning({ count }: DuplicateWarningProps) {
  if (count === 0) return null;

  return (
    <Card className="p-4 bg-[#fef3c7] border-[#fde68a]">
      <div className="flex items-start gap-3">
        <AlertTriangle className="h-5 w-5 text-[#d97706] flex-shrink-0 mt-0.5" />
        <div className="flex-1">
          <h4 className="text-sm font-semibold text-[#92400e] mb-1">
            Duplicate / Reupload Lines Detected
          </h4>
          <p className="text-sm text-[#92400e]">
            {count} uploaded line {count === 1 ? "matched" : "lines matched"} existing PR line identities.
            Exact duplicates should be skipped; changed content for the same line identity should be treated as a reupload update.
          </p>
          <p className="text-xs text-[#92400e] mt-2">
            The identity key must not use amount as the primary match field, because changed amounts are valid updates.
          </p>
        </div>
      </div>
    </Card>
  );
}
