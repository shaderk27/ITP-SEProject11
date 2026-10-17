import { useState, type MouseEvent } from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "../ui/alert-dialog";
import { FileDown } from "lucide-react";

interface ExportConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  recordCount: number;
  /** Performs the download. Rejects on failure, which keeps the dialog open. */
  onConfirm: () => void | Promise<void>;
}

export function ExportConfirmDialog({
  open,
  onOpenChange,
  recordCount,
  onConfirm,
}: ExportConfirmDialogProps) {
  const [exporting, setExporting] = useState(false);

  // Radix closes the dialog on action-button click by default; block that so
  // the spinner stays visible while the file is generated, and so a failed
  // export leaves the dialog up for a retry. The caller closes it on success.
  const handleExport = async (event: MouseEvent) => {
    event.preventDefault();
    setExporting(true);
    try {
      await onConfirm();
    } catch {
      // The caller has already surfaced the error; just re-enable the button.
    } finally {
      setExporting(false);
    }
  };

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <FileDown className="h-5 w-5 text-[#1e3a8a]" />
            Export PR Records
          </AlertDialogTitle>
          <AlertDialogDescription className="space-y-3 pt-2">
            <p>
              You are about to export{" "}
              <span className="font-semibold text-foreground">
                {recordCount} PR record{recordCount === 1 ? "" : "s"}
              </span>{" "}
              to an Excel file, matching the filters currently applied to this
              page and your own access level.
            </p>
            <div className="bg-[#f0f9ff] border border-[#bfdbfe] rounded-lg p-3">
              <p className="text-sm text-[#1e40af]">
                <span className="font-medium">Export will include:</span>
              </p>
              <ul className="text-sm text-[#1e3a8a] mt-2 space-y-1">
                <li>• One row per PR line item</li>
                <li>• PR Number, Date, Requestor, Purpose, WBS Code</li>
                <li>• Lab Group, Lab, Category</li>
                <li>• Qty, Unit Rate, Amount + GST, Status</li>
                <li>• A Summary sheet with totals by group and category</li>
              </ul>
            </div>
            <p className="text-sm">
              The file will be downloaded to your default downloads folder.
            </p>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={exporting}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleExport}
            disabled={exporting}
            className="bg-[#1e3a8a] hover:bg-[#1e40af]"
          >
            {exporting ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2" />
                Exporting...
              </>
            ) : (
              <>
                <FileDown className="h-4 w-4 mr-2" />
                Export to Excel
              </>
            )}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
