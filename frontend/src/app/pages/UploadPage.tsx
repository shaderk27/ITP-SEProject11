import { useState } from "react";
import { useNavigate } from "react-router";
import { Upload, FileSpreadsheet, CheckCircle, AlertCircle, X } from "lucide-react";
import { Card } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { ValidationErrors } from "../components/shared/ValidationErrors";
import { useAuth } from "../context/AuthContext";
import { processUploadBatch } from "../services/uploadService";

const ACCEPTED_EXTENSIONS = ["xlsx", "csv"];

function validateUploadFiles(files: File[]) {
  return files.filter((file) => {
    const extension = file.name.split(".").pop()?.toLowerCase();
    return !extension || !ACCEPTED_EXTENSIONS.includes(extension);
  });
}

function mergeUploadFiles(currentFiles: File[], incomingFiles: File[]) {
  const merged = [...currentFiles];
  const existingKeys = new Set(currentFiles.map(getUploadFileKey));

  incomingFiles.forEach((file) => {
    const key = getUploadFileKey(file);
    if (!existingKeys.has(key)) {
      merged.push(file);
      existingKeys.add(key);
    }
  });

  return merged;
}

function getUploadFileKey(file: File) {
  return `${file.name}-${file.size}-${file.lastModified}`;
}

export function UploadPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [isDragging, setIsDragging] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [validationErrors, setValidationErrors] = useState<Array<{field: string; message: string; severity: "error" | "warning"}>>([]);
  const [isProcessing, setIsProcessing] = useState(false);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const droppedFiles = Array.from(e.dataTransfer.files);
    const invalidFiles = validateUploadFiles(droppedFiles);
    if (droppedFiles.length > 0 && invalidFiles.length === 0) {
      setFiles((currentFiles) => mergeUploadFiles(currentFiles, droppedFiles));
      setValidationErrors([]);
    } else if (invalidFiles.length > 0) {
      setValidationErrors([
        {
          field: "File Format",
          message: `Invalid file format: ${invalidFiles.map((file) => file.name).join(", ")}. Upload Excel (.xlsx) or CSV (.csv) files only.`,
          severity: "error",
        },
      ]);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = Array.from(e.target.files ?? []);
    if (selectedFiles.length > 0) {
      const invalidFiles = validateUploadFiles(selectedFiles);
      if (invalidFiles.length > 0) {
        setValidationErrors([
          {
            field: "File Format",
            message: `Invalid file format: ${invalidFiles.map((file) => file.name).join(", ")}. Upload Excel (.xlsx) or CSV (.csv) files only.`,
            severity: "error",
          },
        ]);
        return;
      }

      setFiles((currentFiles) => mergeUploadFiles(currentFiles, selectedFiles));
      setValidationErrors([]);
    }
  };

  const handleRemoveFile = (fileToRemove: File) => {
    setFiles((currentFiles) => currentFiles.filter((file) => getUploadFileKey(file) !== getUploadFileKey(fileToRemove)));
    setValidationErrors([]);
  };

  const handleProcess = async () => {
    if (files.length === 0) return;

    const invalidFiles = validateUploadFiles(files);
    if (invalidFiles.length > 0) {
      alert("Invalid file format. Please upload Excel (.xlsx) or CSV (.csv) files only.");
      return;
    }

    setIsProcessing(true);
    setValidationErrors([]);

    try {
      const result = await processUploadBatch(files, user);
      if (!result.success) {
        setValidationErrors(result.validation_errors);
        return;
      }
      navigate("/upload/result", { state: { uploadResult: result } });
    } catch (error) {
      setValidationErrors([
        {
          field: "Upload",
          message: error instanceof Error ? error.message : "Upload failed. Please try again.",
          severity: "error",
        },
      ]);
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className="h-full overflow-auto bg-[#f8f9fa]">
      <div className="p-6 max-w-4xl mx-auto space-y-6">
        <div>
          <h2 className="text-2xl font-semibold text-foreground mb-2">
            Upload PR Line Items
          </h2>
          <p className="text-sm text-muted-foreground">
            Upload Excel or CSV files containing consolidated PR rows for line-item processing.
          </p>
        </div>

        {/* Upload Area */}
        <Card
          className={`p-8 bg-white border-2 border-dashed transition-colors ${
            isDragging
              ? "border-[#1e3a8a] bg-[#1e3a8a]/5"
              : "border-border hover:border-[#1e3a8a]/50"
          }`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <div className="flex flex-col items-center justify-center text-center space-y-4">
            <div className="h-16 w-16 rounded-full bg-[#1e3a8a]/10 flex items-center justify-center">
              <Upload className="h-8 w-8 text-[#1e3a8a]" />
            </div>
            <div>
              <p className="text-lg font-medium text-foreground mb-1">
                {files.length > 0 ? `${files.length} file${files.length === 1 ? "" : "s"} selected` : "Drag and drop your files here"}
              </p>
              <p className="text-sm text-muted-foreground">
                or click to browse for Excel (.xlsx) or CSV files
              </p>
            </div>
            <input
              type="file"
              accept=".xlsx,.csv"
              multiple
              onChange={handleFileSelect}
              className="hidden"
              id="file-upload"
            />
            <label htmlFor="file-upload">
              <Button variant="outline" asChild>
                <span className="cursor-pointer">Browse Files</span>
              </Button>
            </label>
            {files.length > 0 && (
              <div className="w-full max-w-md space-y-2">
                <div className="flex items-center justify-center gap-2 text-sm text-[#059669]">
                  <CheckCircle className="h-4 w-4" />
                  <span>Files ready to process</span>
                </div>
                <div className="max-h-32 overflow-auto rounded border border-border bg-[#f8f9fa] text-left">
                  {files.map((selectedFile) => (
                    <div key={getUploadFileKey(selectedFile)} className="flex items-center justify-between gap-2 px-3 py-2 text-xs text-muted-foreground border-b border-border last:border-0">
                      <span className="min-w-0 flex-1 truncate">{selectedFile.name}</span>
                      <button
                        type="button"
                        onClick={() => handleRemoveFile(selectedFile)}
                        className="h-6 w-6 shrink-0 rounded border border-border bg-white text-muted-foreground hover:text-[#dc2626] hover:border-[#fecaca] inline-flex items-center justify-center"
                        aria-label={`Remove ${selectedFile.name}`}
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </Card>

        {/* Validation Errors */}
        <ValidationErrors errors={validationErrors} />

        {/* Required Fields Info */}
        <Card className="p-6 bg-white border-border">
          <h3 className="text-lg font-semibold mb-4 text-foreground">
            Required Fields
          </h3>
          <div className="grid grid-cols-2 gap-4">
            <div className="flex items-start gap-3">
              <CheckCircle className="h-5 w-5 text-[#059669] mt-0.5" />
              <div>
                <p className="text-sm font-medium text-foreground">PR Number</p>
                <p className="text-xs text-muted-foreground">PR header identifier</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <CheckCircle className="h-5 w-5 text-[#059669] mt-0.5" />
              <div>
                <p className="text-sm font-medium text-foreground">Purpose</p>
                <p className="text-xs text-muted-foreground">Description of PR</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <CheckCircle className="h-5 w-5 text-[#059669] mt-0.5" />
              <div>
                <p className="text-sm font-medium text-foreground">WBS Code</p>
                <p className="text-xs text-muted-foreground">Work breakdown structure</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <CheckCircle className="h-5 w-5 text-[#059669] mt-0.5" />
              <div>
                <p className="text-sm font-medium text-foreground">Amount + GST</p>
                <p className="text-xs text-muted-foreground">Line-item spending value</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <CheckCircle className="h-5 w-5 text-[#059669] mt-0.5" />
              <div>
                <p className="text-sm font-medium text-foreground">Requestor</p>
                <p className="text-xs text-muted-foreground">Person who created PR</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <CheckCircle className="h-5 w-5 text-[#059669] mt-0.5" />
              <div>
                <p className="text-sm font-medium text-foreground">Date</p>
                <p className="text-xs text-muted-foreground">PR creation date</p>
              </div>
            </div>
          </div>
        </Card>

        {/* Important Notes */}
        <Card className="p-6 bg-[#fef3c7] border-[#fde68a]">
          <div className="flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-[#d97706] mt-0.5" />
            <div>
              <h3 className="text-sm font-semibold text-[#92400e] mb-2">
                Important Notes
              </h3>
              <ul className="text-xs text-[#92400e] space-y-1">
                <li>- Files will be validated before processing</li>
                <li>- Each row is treated as a PR line item, not only a PR header</li>
                <li>- WBS maps Lab Group first; unclear values fall back to General and review</li>
                <li>- Duplicate detection uses line identity plus content comparison, not PR number alone</li>
              </ul>
            </div>
          </div>
        </Card>

        {/* Action Buttons */}
        <div className="flex justify-end gap-4">
          <Button variant="outline">Cancel</Button>
          <Button
            className="bg-[#1e3a8a] hover:bg-[#1e40af] text-white"
            disabled={files.length === 0 || validationErrors.length > 0 || isProcessing}
            onClick={handleProcess}
          >
            <FileSpreadsheet className="h-4 w-4 mr-2" />
            {isProcessing ? "Processing..." : `Validate & Process${files.length > 1 ? ` ${files.length} Files` : ""}`}
          </Button>
        </div>
      </div>
    </div>
  );
}
