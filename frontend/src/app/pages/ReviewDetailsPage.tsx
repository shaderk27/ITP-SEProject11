import { useState } from "react";
import { useParams, useNavigate, Navigate } from "react-router";
import { AlertCircle, CheckCircle, ChevronDown, ChevronRight, Info } from "lucide-react";
import { Card } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Label } from "../components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { Textarea } from "../components/ui/textarea";
import { StatusBadge } from "../components/shared/StatusBadge";
import { useAuth } from "../context/AuthContext";

const reviewLines = {
  "REV-001": {
    uploadBatchId: "UP-2026-053",
    pr: "PR-2026-1525",
    lineNo: "Line 3",
    requestor: "Sarah Chen",
    prDate: "2026-05-15",
    lastUpdate: "2026-05-20 14:18",
    itemDetails: "Miscellaneous supplies for food processing unit",
    quantity: "10",
    unitRate: "$65.00",
    amount: "$650.00",
    wbs: "MISC-001",
    purpose: "Supplies for W3 Food Processing workshop",
    instructionToVendor: "Deliver to Building 3, Level 1, Food Processing Lab",
    original: {
      labGroup: "FCB",
      lab: "General",
      category: "Consumables",
    },
    reasons: [
      "WBS mapped to Lab Group FCB with medium confidence.",
      "Purpose and vendor instruction suggest Food Processing, but no configured lab alias matched exactly.",
      "Lab remains General inside FCB, so spending can count to FCB budget but should stay visible in review.",
      "Category matched Consumables; General Category is not the issue for this line.",
    ],
  },
  "REV-002": {
    uploadBatchId: "UP-2026-053",
    pr: "PR-2026-1526",
    lineNo: "Line 1",
    requestor: "Michael Tan",
    prDate: "2026-05-18",
    lastUpdate: "2026-05-20 14:22",
    itemDetails: "External testing service",
    quantity: "1",
    unitRate: "$3,200.00",
    amount: "$3,200.00",
    wbs: "W3-99-01",
    purpose: "External testing service for material samples",
    instructionToVendor: "Send samples to approved testing vendor",
    original: {
      labGroup: "General",
      lab: "General",
      category: "Services",
    },
    reasons: [
      "WBS did not map confidently to a configured Lab Group.",
      "Lab Group General rows should remain out of budget calculation until reviewed.",
      "Purpose suggests external testing, but ownership boundary is still unclear.",
    ],
  },
  "REV-003": {
    uploadBatchId: "UP-2026-052",
    pr: "PR-2026-1527",
    lineNo: "Line 2",
    requestor: "Emily Wong",
    prDate: "2026-05-19",
    lastUpdate: "2026-05-21 09:04",
    itemDetails: "Specialized equipment calibration",
    quantity: "1",
    unitRate: "$1,850.00",
    amount: "$1,850.00",
    wbs: "W4-01-12",
    purpose: "Calibration for analytical instrument",
    instructionToVendor: "Coordinate calibration with lab IC",
    original: {
      labGroup: "EPD",
      lab: "W4L1",
      category: "General",
    },
    reasons: [
      "WBS mapped to EPD and lab W4L1.",
      "Uploaded category did not match configured category presets.",
      "Only Category is General for this line; Lab Group and Lab are already known.",
    ],
  },
  "REV-004": {
    uploadBatchId: "UP-2026-052",
    pr: "PR-2026-1519",
    lineNo: "Line 1",
    requestor: "Emily Wong",
    prDate: "2026-05-19",
    lastUpdate: "2026-05-19 09:04",
    itemDetails: "Consumable replacement pack",
    quantity: "4",
    unitRate: "$230.00",
    amount: "$920.00",
    wbs: "W4-01-12",
    purpose: "Replacement consumables for tensile testing",
    instructionToVendor: "Deliver to W4L1",
    original: {
      labGroup: "EPD",
      lab: "W4L1",
      category: "General",
    },
    reasons: [
      "WBS mapped to EPD and W4L1.",
      "Uploaded category did not match configured category presets.",
      "Category fallback requires Team Lead confirmation before batch commit.",
    ],
  },
};

export function ReviewDetailsPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const reviewLine = reviewLines[id as keyof typeof reviewLines] ?? reviewLines["REV-001"];
  const [labGroup, setLabGroup] = useState(reviewLine.original.labGroup);
  const [lab, setLab] = useState(reviewLine.original.lab);
  const [category, setCategory] = useState(reviewLine.original.category);
  const [notes, setNotes] = useState("");
  const [showRaw, setShowRaw] = useState(true);
  const [showTrace, setShowTrace] = useState(true);
  const { user } = useAuth();

  const canReview =
    user?.role === "admin" ||
    user?.assignedLabs?.includes(
      reviewLine.original.lab
    );
  if (!canReview) {
    return <Navigate to="/403" replace />;
  }
  const handleSave = () => {
    navigate("/review");
  };

  return (
    <div className="h-full overflow-auto bg-[#f8f9fa]">
      <div className="p-6 max-w-6xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-semibold text-foreground">Resolve Review Line</h2>
            <p className="text-sm text-muted-foreground mt-1">
              {reviewLine.pr} - {reviewLine.lineNo} from {reviewLine.uploadBatchId}
              {id ? ` (${id})` : ""}
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              Saving this page resolves only this line. The upload batch can be approved after every line in the batch is resolved.
            </p>
          </div>
          <Button variant="outline" onClick={() => navigate("/review")}>
            Back to Queue
          </Button>
        </div>

        <Card className="p-5 bg-[#fff7ed] border-[#fed7aa]">
          <div className="flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-[#c2410c] mt-0.5" />
            <div>
              <p className="text-sm font-medium text-[#9a3412]">Line-item edit required</p>
              <p className="text-sm text-[#9a3412] mt-1">
                This line is not blocked because the whole PR is invalid. Only this PR line needs classification review.
                Keep Lab Group, Lab, and Category decisions separate.
              </p>
            </div>
          </div>
        </Card>

        <div className="grid grid-cols-1 xl:grid-cols-[1fr_360px] gap-6">
          <div className="space-y-4">
            <Card className="bg-white border-border overflow-hidden">
              <button
                type="button"
                className="w-full p-5 flex items-center justify-between text-left"
                onClick={() => setShowRaw((value) => !value)}
              >
                <span className="flex items-center gap-2 text-lg font-semibold text-foreground">
                  <Info className="h-5 w-5 text-[#2563eb]" />
                  Uploaded Line Data
                </span>
                {showRaw ? <ChevronDown className="h-5 w-5" /> : <ChevronRight className="h-5 w-5" />}
              </button>
              {showRaw && (
                <div className="border-t border-border p-5 grid grid-cols-1 md:grid-cols-3 gap-5">
                  <div>
                    <Label className="text-muted-foreground">Item Details</Label>
                    <p className="text-sm text-foreground mt-1">{reviewLine.itemDetails}</p>
                  </div>
                  <div>
                    <Label className="text-muted-foreground">Purpose</Label>
                    <p className="text-sm text-foreground mt-1">{reviewLine.purpose}</p>
                  </div>
                  <div>
                    <Label className="text-muted-foreground">Instruction to Vendor</Label>
                    <p className="text-sm text-foreground mt-1">{reviewLine.instructionToVendor}</p>
                  </div>
                  <div>
                    <Label className="text-muted-foreground">WBS</Label>
                    <p className="text-sm font-medium text-foreground mt-1">{reviewLine.wbs}</p>
                  </div>
                  <div>
                    <Label className="text-muted-foreground">Requestor</Label>
                    <p className="text-sm text-foreground mt-1">{reviewLine.requestor}</p>
                  </div>
                  <div>
                    <Label className="text-muted-foreground">Amount + GST</Label>
                    <p className="text-sm font-medium text-foreground mt-1">{reviewLine.amount}</p>
                  </div>
                  <div>
                    <Label className="text-muted-foreground">Qty</Label>
                    <p className="text-sm text-foreground mt-1">{reviewLine.quantity}</p>
                  </div>
                  <div>
                    <Label className="text-muted-foreground">Unit Rate</Label>
                    <p className="text-sm text-foreground mt-1">{reviewLine.unitRate}</p>
                  </div>
                  <div>
                    <Label className="text-muted-foreground">Last Update</Label>
                    <p className="text-sm text-foreground mt-1">{reviewLine.lastUpdate}</p>
                  </div>
                </div>
              )}
            </Card>

            <Card className="bg-white border-border overflow-hidden">
              <button
                type="button"
                className="w-full p-5 flex items-center justify-between text-left"
                onClick={() => setShowTrace((value) => !value)}
              >
                <span className="flex items-center gap-2 text-lg font-semibold text-foreground">
                  <AlertCircle className="h-5 w-5 text-[#d97706]" />
                  Review Reason
                </span>
                {showTrace ? <ChevronDown className="h-5 w-5" /> : <ChevronRight className="h-5 w-5" />}
              </button>
              {showTrace && (
                <div className="border-t border-border p-5 space-y-3">
                  {reviewLine.reasons.map((reason, index) => (
                    <div key={reason} className="flex items-start gap-3 rounded-md bg-[#f8f9fa] p-3">
                      <span className="h-6 w-6 rounded-full bg-[#1e3a8a] text-white text-xs flex items-center justify-center">
                        {index + 1}
                      </span>
                      <p className="text-sm text-muted-foreground">{reason}</p>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>

          <div className="space-y-4">
            <Card className="p-5 bg-white border-border">
              <h3 className="text-lg font-semibold mb-4 text-foreground flex items-center gap-2">
                <CheckCircle className="h-5 w-5 text-[#059669]" />
                Final Classification
              </h3>
              <div className="space-y-4">
                <div>
                  <Label>Lab Group</Label>
                  <Select value={labGroup} onValueChange={setLabGroup}>
                    <SelectTrigger className="mt-1">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="FCB">FCB</SelectItem>
                      <SelectItem value="EPD">EPD</SelectItem>
                      <SelectItem value="General">General</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div>
                  <Label>Lab</Label>
                  <Select value={lab} onValueChange={setLab}>
                    <SelectTrigger className="mt-1">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="General">General</SelectItem>
                      <SelectItem value="W3L1 Food PP">W3L1 Food PP</SelectItem>
                      <SelectItem value="W3L2 Food Chemistry">W3L2 Food Chemistry</SelectItem>
                      <SelectItem value="W3L3 Food Microbiology">W3L3 Food Microbiology</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div>
                  <Label>Category</Label>
                  <Select value={category} onValueChange={setCategory}>
                    <SelectTrigger className="mt-1">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="General">General</SelectItem>
                      <SelectItem value="Consumables">Consumables</SelectItem>
                      <SelectItem value="Supplies">Supplies</SelectItem>
                      <SelectItem value="Maintenance">Maintenance</SelectItem>
                      <SelectItem value="Others">Others</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div>
                  <Label>Audit Note</Label>
                  <Textarea
                    placeholder="Reason for manual correction..."
                    value={notes}
                    onChange={(event) => setNotes(event.target.value)}
                    className="mt-1"
                    rows={4}
                  />
                </div>
              </div>
            </Card>

            <Card className="p-5 bg-[#f0f9ff] border-[#bfdbfe]">
              <h4 className="text-sm font-semibold text-[#1e40af] mb-3">Line Resolution Preview</h4>
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm text-muted-foreground">Lab Group</span>
                  <StatusBadge status={labGroup === "General" ? "general" : "info"}>{labGroup}</StatusBadge>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm text-muted-foreground">Lab</span>
                  <StatusBadge status={lab === "General" ? "general" : "info"}>{lab}</StatusBadge>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm text-muted-foreground">Category</span>
                  <StatusBadge status={category === "General" ? "general" : "info"}>{category}</StatusBadge>
                </div>
              </div>
            </Card>

            <Button className="w-full bg-[#059669] hover:bg-[#047857] text-white" onClick={handleSave}>
              Save Line Resolution
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
