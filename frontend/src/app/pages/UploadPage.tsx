import { useState } from "react";
import { useNavigate } from "react-router";
import { Upload, FileSpreadsheet, CheckCircle, AlertCircle } from "lucide-react";
import { Card } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { ValidationErrors } from "../components/shared/ValidationErrors";
import { useAuth } from "../context/AuthContext";
import { processUpload } from "../services/uploadService";

export function UploadPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [isDragging, setIsDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);
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
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile && (droppedFile.name.endsWith(".xlsx") || droppedFile.name.endsWith(".csv"))) {
      setFile(droppedFile);
      setValidationErrors([]);
    } else if (droppedFile) {
      setValidationErrors([
        { field: "File Format", message: "Invalid file format. Please upload Excel (.xlsx) or CSV (.csv) files only.", severity: "error" },
      ]);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      setFile(selectedFile);
      setValidationErrors([]);

      // Mock validation - in real app this would happen on backend
      const fileExtension = selectedFile.name.split('.').pop()?.toLowerCase();
      if (!fileExtension || !['xlsx', 'csv'].includes(fileExtension)) {
        setValidationErrors([
          { field: "File Format", message: "Invalid file format. Please upload Excel (.xlsx) or CSV (.csv) files only.", severity: "error" }
        ]);
      }
    }
  };

  const handleProcess = async () => {
    if (!file) return;

    // Mock validation
    const fileExtension = file.name.split('.').pop()?.toLowerCase();
    if (!fileExtension || !['xlsx', 'csv'].includes(fileExtension)) {
      alert("Invalid file format. Please upload Excel (.xlsx) or CSV (.csv) files only.");
      return;
    }

    setIsProcessing(true);
    setValidationErrors([]);

    try {
      const result = await processUpload(file, user);
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
                {file ? file.name : "Drag and drop your file here"}
              </p>
              <p className="text-sm text-muted-foreground">
                or click to browse for Excel (.xlsx) or CSV files
              </p>
            </div>
            <input
              type="file"
              accept=".xlsx,.csv"
              onChange={handleFileSelect}
              className="hidden"
              id="file-upload"
            />
            <label htmlFor="file-upload">
              <Button variant="outline" asChild>
                <span className="cursor-pointer">Browse Files</span>
              </Button>
            </label>
            {file && (
              <div className="flex items-center gap-2 text-sm text-[#059669]">
                <CheckCircle className="h-4 w-4" />
                <span>File ready to process</span>
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
            disabled={!file || validationErrors.length > 0 || isProcessing}
            onClick={handleProcess}
          >
            <FileSpreadsheet className="h-4 w-4 mr-2" />
            {isProcessing ? "Processing..." : "Validate & Process"}
          </Button>
        </div>
      </div>
    </div>
  );
}
