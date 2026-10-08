import { useState } from "react";
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
  onConfirm: () => void;
}

export function ExportConfirmDialog({
  open,
  onOpenChange,
  recordCount,
  onConfirm,
}: ExportConfirmDialogProps) {
  const [exporting, setExporting] = useState(false);

  const handleExport = () => {
    setExporting(true);

    // Simulate export process
    setTimeout(() => {
      onConfirm();
      setExporting(false);
      onOpenChange(false);
    }, 1500);
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
              You are about to export <span className="font-semibold text-foreground">{recordCount} PR records</span> to an Excel file.
            </p>
            <div className="bg-[#f0f9ff] border border-[#bfdbfe] rounded-lg p-3">
              <p className="text-sm text-[#1e40af]">
                <span className="font-medium">Export will include:</span>
              </p>
              <ul className="text-sm text-[#1e3a8a] mt-2 space-y-1">
                <li>• PR Number, Date, Requestor</li>
                <li>• Purpose and WBS Code</li>
                <li>• Lab Group, Lab, Category</li>
                <li>• Amount and Status</li>
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
