import { useState, useEffect, useMemo, Fragment } from "react";
import { Navigate } from "react-router";
import { Card } from "../components/ui/card";
import {
  AlertCircle,
  Building2,
  Search,
  X,
  FileText,
  ChevronDown,
  ChevronRight,
  Zap,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { useAuth } from "../context/AuthContext";

const formatCurrency = (amount: number = 0) => {
  const absFormatted = Math.abs(amount).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return amount < 0 ? `-$${absFormatted}` : `$${absFormatted}`;
};

interface Category {
  id: number;
  name: string;
}
interface LabGroupData {
  id: number;
  name: string;
  wbs_code: string;
  budget: number;
  spent: number;
}
interface LabData {
  id: number;
  group_id: number;
  group: string;
  code: string;
  name: string;
  budget: number;
  spent: number;
  budgets: Record<string, number>;
  spent_by_category: Record<string, number>;
}

interface LabAlert {
  id: string;
  labId: number;
  groupId: number;
  labCode: string;
  labName: string;
  budget: number;
  actual: number;
  utilization: number;
  type: string;
  threshold: number;
  budgets: Record<string, number>;
  spentByCategory: Record<string, number>;
}
interface GroupAlert {
  groupId: number;
  groupName: string;
  wbsCode: string;
  totalBudget: number;
  totalSpent: number;
  groupUtilization: number;
  groupType: string;
  labs: LabAlert[];
}

interface DrilldownPRLine {
  pr_line_id: number;
  pr_id: number;
  source_pr_number: string;
  line_no: number | null;
  item_description: string;
  requestor_name: string;
  request_date: string | null;
  amount_gst: string;
  pr_status: string | null;
  latest_batch_id: number | null;
  is_triggering_line: boolean;
}

interface DrilldownCategory {
  category_id: number | null;
  category_name: string;
  budget_sgd: string;
  actual_spend_sgd: string;
  pending_sgd: string;
  committed_spend_sgd: string;
  available_balance_sgd: string;
  utilisation_pct: number;
  projected_utilisation_pct: number;
  pr_lines: DrilldownPRLine[];
}

export function AlertsPage() {
  const { user, hasPermission } = useAuth();

  const [labGroups, setLabGroups] = useState<LabGroupData[]>([]);
  const [labs, setLabs] = useState<LabData[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const [searchTerm, setSearchTerm] = useState("");
  const [selectedType, setSelectedType] = useState("all");
  const [selectedGroup, setSelectedGroup] = useState("all");

  const [selectedLabDetails, setSelectedLabDetails] = useState<LabAlert | null>(
    null
  );
  const [drilldownCategories, setDrilldownCategories] = useState<
    Record<string, DrilldownCategory>
  >({});
  const [isDrilldownLoading, setIsDrilldownLoading] = useState(false);
  const [expandedCategories, setExpandedCategories] = useState<
    Record<string, boolean>
  >({});

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [groupsRes, labsRes, catsRes] = await Promise.all([
          fetch(`${API_BASE_URL}/api/config/labgroups`, {
            credentials: "include",
          }),
          fetch(`${API_BASE_URL}/api/config/labs`, { credentials: "include" }),
          fetch(`${API_BASE_URL}/api/config/categories`, {
            credentials: "include",
          }),
        ]);
        if (groupsRes.ok) setLabGroups(await groupsRes.json());
        if (labsRes.ok) setLabs(await labsRes.json());
        if (catsRes.ok) setCategories(await catsRes.json());
      } catch (err) {
        console.error(err);
      } finally {
        setIsLoading(false);
      }
    };
    fetchData();
  }, [API_BASE_URL]);

  // Fetch W17-01B PR line drilldown when a Lab's Breakdown modal is opened
  useEffect(() => {
    if (!selectedLabDetails) return;

    let isCancelled = false;
    const fetchDrilldown = async () => {
      try {
        const res = await fetch(
          `${API_BASE_URL}/api/alerts/drilldown?lab_group_id=${selectedLabDetails.groupId}&lab_id=${selectedLabDetails.labId}`,
          { credentials: "include" }
        );
        if (res.ok && !isCancelled) {
          const data = await res.json();
          const catMap: Record<string, DrilldownCategory> = {};

          for (const grp of data.lab_groups || []) {
            const matchedLab = grp.labs?.find(
              (lab: { lab_id: number }) =>
                lab.lab_id === selectedLabDetails.labId
            );
            if (matchedLab?.categories) {
              matchedLab.categories.forEach((c: DrilldownCategory) => {
                const key =
                  c.category_id !== null ? String(c.category_id) : "null";
                catMap[key] = c;
              });
              break;
            }
          }
          setDrilldownCategories(catMap);
        }
      } catch (err) {
        console.error("Failed to load alert drill-down lines:", err);
      } finally {
        if (!isCancelled) {
          setIsDrilldownLoading(false);
        }
      }
    };

    fetchDrilldown();
    return () => {
      isCancelled = true;
    };
  }, [API_BASE_URL, selectedLabDetails]);

  const handleOpenBreakdown = (lab: LabAlert) => {
    setDrilldownCategories({});
    setExpandedCategories({});
    setIsDrilldownLoading(true);
    setSelectedLabDetails(lab);
  };

  const handleCloseBreakdown = () => {
    setSelectedLabDetails(null);
    setDrilldownCategories({});
    setExpandedCategories({});
    setIsDrilldownLoading(false);
  };

  const toggleCategoryExpand = (catKey: string) => {
    setExpandedCategories((prev) => ({
      ...prev,
      [catKey]: !prev[catKey],
    }));
  };

  const getSeverity = (util: number) => {
    if (util >= 100)
      return {
        type: "exceeded",
        threshold: 100,
        label: "Exceeded",
        colors: "bg-[#fef2f2] border-[#fecaca] text-[#dc2626]",
      };
    if (util >= 95)
      return {
        type: "critical",
        threshold: 95,
        label: "95% Critical",
        colors: "bg-[#fff1f2] border-[#fecdd3] text-[#e11d48]",
      };
    if (util >= 80)
      return {
        type: "alert",
        threshold: 80,
        label: "80% Alert",
        colors: "bg-[#fffbeb] border-[#fde68a] text-[#d97706]",
      };
    if (util >= 50)
      return {
        type: "warning",
        threshold: 50,
        label: "50% Warning",
        colors: "bg-[#eff6ff] border-[#bfdbfe] text-[#2563eb]",
      };
    return {
      type: "none",
      threshold: 0,
      label: "Healthy",
      colors: "bg-gray-50 border-gray-200 text-gray-500",
    };
  };

  const groupedAlerts = useMemo(() => {
    const result: GroupAlert[] = [];

    const groupsToProcess = labGroups.filter((g) => {
      if (user?.role === "admin") return true;
      if (user?.role === "teamlead") return g.id === user?.labGroupId;
      if (user?.role === "labic") {
        return labs.some(
          (l) => l.group_id === g.id && user.labIds.includes(l.id)
        );
      }
      return false;
    });

    groupsToProcess.forEach((group) => {
      const isLabIC = user?.role === "labic";

      const groupUtil =
        !isLabIC && group.budget > 0 ? (group.spent / group.budget) * 100 : 0;
      const groupSeverity = getSeverity(groupUtil);

      let groupLabs = labs.filter(
        (l) => l.group_id === group.id && (l.budget > 0 || l.spent > 0)
      );

      if (isLabIC) {
        groupLabs = groupLabs.filter((l) => user?.labIds.includes(l.id));
      }

      const labAlerts: LabAlert[] = [];
      groupLabs.forEach((lab) => {
        const util =
          lab.budget > 0
            ? (lab.spent / lab.budget) * 100
            : lab.spent > 0
            ? 100
            : 0;
        const severity = getSeverity(util);

        if (severity.type !== "none" || groupSeverity.type !== "none") {
          labAlerts.push({
            id: `LAB-${lab.id}`,
            labId: lab.id,
            groupId: group.id,
            labCode: lab.code,
            labName: lab.name,
            budget: lab.budget,
            actual: lab.spent || 0,
            utilization: Number(util.toFixed(1)),
            type: severity.type,
            threshold: severity.threshold,
            budgets: lab.budgets,
            spentByCategory: lab.spent_by_category,
          });
        }
      });

      if (groupSeverity.type !== "none" || labAlerts.length > 0) {
        labAlerts.sort((a, b) => b.utilization - a.utilization);

        result.push({
          groupId: group.id,
          groupName: group.name,
          wbsCode: group.wbs_code,
          totalBudget: isLabIC ? 0 : group.budget,
          totalSpent: isLabIC ? 0 : group.spent,
          groupUtilization: Number(groupUtil.toFixed(1)),
          groupType: groupSeverity.type,
          labs: labAlerts,
        });
      }
    });

    return result.sort((a, b) => b.groupUtilization - a.groupUtilization);
  }, [labGroups, labs, user]);

  const filteredGroups = useMemo(() => {
    return groupedAlerts.filter((g) => {
      if (selectedGroup !== "all" && g.groupId.toString() !== selectedGroup)
        return false;
      if (selectedType !== "all" && g.groupType !== selectedType) {
        const childMatches = g.labs.some((l) => l.type === selectedType);
        if (!childMatches) return false;
      }

      if (searchTerm) {
        const term = searchTerm.toLowerCase();
        const groupMatches =
          g.groupName.toLowerCase().includes(term) ||
          g.wbsCode.toLowerCase().includes(term);
        const childMatches = g.labs.some(
          (l) =>
            l.labCode.toLowerCase().includes(term) ||
            l.labName.toLowerCase().includes(term)
        );
        if (!groupMatches && !childMatches) return false;
      }

      return true;
    });
  }, [groupedAlerts, searchTerm, selectedType, selectedGroup]);

  if (!hasPermission("alerts:view")) return <Navigate to="/403" replace />;
  if (isLoading)
    return (
      <div className="p-8 text-center text-muted-foreground">
        Loading Alerts...
      </div>
    );

  return (
    <div className="h-full overflow-auto bg-[#f8f9fa] relative">
      {user?.role !== "labic" && (
        <div className="bg-white p-4 border-b border-border flex flex-col sm:flex-row gap-4 items-center justify-between shadow-sm">
          <div className="relative w-full sm:w-96">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search by Group or Lab name..."
              className="w-full pl-9 pr-4 py-2 border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-[#1e3a8a]/20"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>
          <div className="flex w-full sm:w-auto gap-4">
            <select
              className="w-full sm:w-auto px-3 py-2 border border-border rounded-md text-sm bg-white outline-none"
              value={selectedType}
              onChange={(e) => setSelectedType(e.target.value)}
            >
              <option value="all">All Thresholds</option>
              <option value="exceeded">Exceeded (&gt;100%)</option>
              <option value="critical">Critical (95%)</option>
              <option value="alert">Alert (80%)</option>
              <option value="warning">Warning (50%)</option>
            </select>

            {user?.role === "admin" && (
              <select
                className="w-full sm:w-auto px-3 py-2 border border-border rounded-md text-sm bg-white outline-none"
                value={selectedGroup}
                onChange={(e) => setSelectedGroup(e.target.value)}
              >
                <option value="all">All Lab Groups</option>
                {labGroups.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.name}
                  </option>
                ))}
              </select>
            )}
          </div>
        </div>
      )}

      <div className="p-6 space-y-6">
        <div>
          <h2 className="text-2xl font-semibold text-foreground">
            Alerts Center
          </h2>
          <p className="text-sm text-muted-foreground mt-1">
            Hierarchical budget threshold warnings and PR line traceability.
          </p>
        </div>

        <div className="space-y-6">
          {filteredGroups.length === 0 ? (
            <div className="p-12 text-center text-gray-500 bg-white border border-gray-200 rounded-lg shadow-sm">
              No budget alerts found. All managed lab groups are healthy.
            </div>
          ) : (
            filteredGroups.map((group) => {
              const groupSev = getSeverity(group.groupUtilization);

              return (
                <Card
                  key={group.groupId}
                  className="bg-white border-gray-200 shadow-sm overflow-hidden"
                >
                  <div
                    className={`p-5 border-b-4 ${
                      groupSev.type === "none"
                        ? "border-b-gray-200 bg-gray-50"
                        : groupSev.colors
                            .split(" ")[1]
                            .replace("border-", "border-b-")
                    } ${
                      groupSev.type === "none"
                        ? ""
                        : groupSev.colors.split(" ")[0]
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="p-2 rounded-lg bg-white/60 shadow-sm">
                          <Building2
                            className={`h-6 w-6 ${
                              groupSev.colors.split(" ")[2]
                            }`}
                          />
                        </div>
                        <div>
                          <h3 className="text-lg font-black text-gray-900 tracking-tight flex items-center gap-2">
                            {group.groupName}

                            {user?.role !== "labic" ? (
                              <span
                                className={`px-2 py-0.5 text-xs rounded-full border bg-white ${groupSev.colors}`}
                              >
                                {groupSev.type === "none"
                                  ? "Group Budget Healthy"
                                  : `Group Budget ${groupSev.label}`}
                              </span>
                            ) : (
                              <span className="px-2 py-0.5 text-xs rounded-full border bg-gray-100 text-gray-600 border-gray-200">
                                Parent Group
                              </span>
                            )}
                          </h3>
                          <p className="text-sm font-medium text-gray-600 font-mono mt-0.5">
                            {group.wbsCode}
                          </p>
                        </div>
                      </div>

                      {user?.role !== "labic" && (
                        <div className="text-right bg-white/60 p-2.5 rounded-lg border border-black/5">
                          <p className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-0.5">
                            Group Utilisation
                          </p>
                          <p
                            className={`text-xl font-black ${
                              groupSev.colors.split(" ")[2]
                            }`}
                          >
                            {group.groupUtilization}%
                          </p>
                        </div>
                      )}
                    </div>

                    {user?.role !== "labic" && (
                      <div className="mt-4 grid grid-cols-2 gap-4">
                        <div className="bg-white/50 rounded p-2">
                          <p className="text-xs text-gray-500 font-medium">
                            Total Budget
                          </p>
                          <p className="text-sm font-bold text-gray-900">
                            {formatCurrency(group.totalBudget)}
                          </p>
                        </div>
                        <div className="bg-white/50 rounded p-2">
                          <p className="text-xs text-gray-500 font-medium">
                            Group Spent
                          </p>
                          <p className="text-sm font-bold text-gray-900">
                            {formatCurrency(group.totalSpent)}
                          </p>
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="p-4 space-y-3 bg-gray-50/50">
                    {group.labs.length === 0 ? (
                      <p className="text-sm text-gray-400 italic text-center p-4">
                        All individual labs within this group are healthy.
                      </p>
                    ) : (
                      group.labs.map((lab) => {
                        const labSev = getSeverity(lab.utilization);
                        return (
                          <div
                            key={lab.id}
                            className={`p-4 rounded-lg border bg-white shadow-sm flex items-center justify-between ${labSev.colors}`}
                          >
                            <div className="flex-1">
                              <div className="flex items-center gap-2 mb-1">
                                <AlertCircle
                                  className={`h-4 w-4 ${
                                    labSev.colors.split(" ")[2]
                                  }`}
                                />
                                <h4 className="font-bold text-gray-900">
                                  {lab.labCode} — {lab.labName}
                                </h4>
                                <span
                                  className={`text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded ${labSev.colors}`}
                                >
                                  {labSev.label}
                                </span>
                              </div>
                              <div className="flex items-center gap-6 mt-2 text-sm">
                                <div>
                                  <span className="text-gray-500 text-xs">
                                    Allocated:
                                  </span>{" "}
                                  <span className="font-semibold text-gray-800">
                                    {formatCurrency(lab.budget)}
                                  </span>
                                </div>
                                <div>
                                  <span className="text-gray-500 text-xs">
                                    Spent:
                                  </span>{" "}
                                  <span className="font-semibold text-gray-800">
                                    {formatCurrency(lab.actual)}
                                  </span>
                                </div>
                                <div>
                                  <span className="text-gray-500 text-xs">
                                    Utilisation:
                                  </span>{" "}
                                  <span
                                    className={`font-bold ${
                                      labSev.colors.split(" ")[2]
                                    }`}
                                  >
                                    {lab.utilization}%
                                  </span>
                                </div>
                              </div>
                            </div>
                            <Button
                              variant="outline"
                              size="sm"
                              className="bg-white h-8 text-xs font-semibold shrink-0 ml-4"
                              onClick={() => handleOpenBreakdown(lab)}
                            >
                              <FileText className="h-3.5 w-3.5 mr-1.5" />{" "}
                              Breakdown
                            </Button>
                          </div>
                        );
                      })
                    )}
                  </div>
                </Card>
              );
            })
          )}
        </div>
      </div>

      {selectedLabDetails && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <Card className="w-full max-w-4xl bg-white shadow-xl overflow-hidden flex flex-col max-h-[85vh]">
            <div className="flex justify-between items-start gap-4 p-6 border-b border-border bg-[#f8f9fa] shrink-0">
              <div>
                <h3 className="text-lg font-bold text-gray-900">
                  Budget &amp; PR Line Traceability Breakdown
                </h3>
                <p className="text-sm text-gray-500">
                  {selectedLabDetails.labCode} — {selectedLabDetails.labName}
                </p>
                <p className="text-xs text-gray-400 mt-1">
                  Click any category row below to inspect its contributing and
                  threshold-triggering Purchase Request lines.
                </p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleCloseBreakdown}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>

            <div className="p-6 overflow-y-auto">
              <table className="w-full text-sm text-left border-collapse">
                <thead className="bg-gray-50 border-y border-gray-200">
                  <tr>
                    <th className="p-3 font-semibold text-gray-600">
                      Category
                    </th>
                    <th className="p-3 font-semibold text-gray-600 text-right">
                      Allocated
                    </th>
                    <th className="p-3 font-semibold text-gray-600 text-right">
                      Spent
                    </th>
                    <th className="p-3 font-semibold text-gray-600 text-right">
                      Remaining
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {categories.map((cat) => {
                    const catKey = String(cat.id);
                    const allocated = Number(
                      selectedLabDetails.budgets?.[cat.id] || 0
                    );
                    const spent = Number(
                      selectedLabDetails.spentByCategory?.[cat.id] || 0
                    );
                    if (allocated === 0 && spent === 0) return null;
                    const balance = allocated - spent;

                    const drillCat = drilldownCategories[catKey];
                    const prLines = drillCat?.pr_lines || [];
                    const isExpanded = !!expandedCategories[catKey];

                    return (
                      <Fragment key={cat.id}>
                        <tr
                          onClick={() => toggleCategoryExpand(catKey)}
                          className="hover:bg-blue-50/40 transition-colors cursor-pointer select-none"
                        >
                          <td className="p-3 font-medium text-gray-800 flex items-center gap-2">
                            {isExpanded ? (
                              <ChevronDown className="h-4 w-4 text-gray-500 shrink-0" />
                            ) : (
                              <ChevronRight className="h-4 w-4 text-gray-500 shrink-0" />
                            )}
                            <span>{cat.name}</span>
                            {!isDrilldownLoading && prLines.length > 0 && (
                              <span className="ml-2 px-2 py-0.5 text-[10px] font-bold rounded-full bg-gray-100 text-gray-600 border border-gray-200">
                                {prLines.length}{" "}
                                {prLines.length === 1 ? "line" : "lines"}
                              </span>
                            )}
                            {balance < 0 && (
                              <span className="ml-1 px-1.5 py-0.5 text-[9px] font-bold uppercase rounded bg-red-100 text-red-700 border border-red-200">
                                Overrun
                              </span>
                            )}
                          </td>
                          <td className="p-3 text-right text-gray-600">
                            {formatCurrency(allocated)}
                          </td>
                          <td className="p-3 text-right text-rose-600 font-medium">
                            {formatCurrency(spent)}
                          </td>
                          <td
                            className={`p-3 text-right font-bold ${
                              balance < 0 ? "text-red-600" : "text-emerald-600"
                            }`}
                          >
                            {formatCurrency(balance)}
                          </td>
                        </tr>

                        {isExpanded && (
                          <tr className="bg-gray-50/80">
                            <td colSpan={4} className="p-4">
                              {isDrilldownLoading ? (
                                <p className="text-xs text-gray-400 italic text-center py-2">
                                  Loading contributing PR lines...
                                </p>
                              ) : prLines.length === 0 ? (
                                <p className="text-xs text-gray-400 italic text-center py-2">
                                  No committed PR lines recorded for this
                                  category in the current fiscal period.
                                </p>
                              ) : (
                                <div className="rounded-md border border-gray-200 bg-white overflow-hidden shadow-xs">
                                  <table className="w-full text-xs text-left">
                                    <thead className="bg-gray-100/80 text-gray-500 uppercase text-[10px] font-bold border-b border-gray-200">
                                      <tr>
                                        <th className="py-2 px-3">PR Number</th>
                                        <th className="py-2 px-3">
                                          Item Description
                                        </th>
                                        <th className="py-2 px-3">Requestor</th>
                                        <th className="py-2 px-3">Date</th>
                                        <th className="py-2 px-3">Status</th>
                                        <th className="py-2 px-3 text-right">
                                          Amount (SGD)
                                        </th>
                                      </tr>
                                    </thead>
                                    <tbody className="divide-y divide-gray-100">
                                      {prLines.map((line) => (
                                        <tr
                                          key={line.pr_line_id}
                                          className={
                                            line.is_triggering_line
                                              ? "bg-amber-50/70 hover:bg-amber-50"
                                              : "hover:bg-gray-50"
                                          }
                                        >
                                          <td className="py-2 px-3 font-mono font-semibold text-gray-900 whitespace-nowrap">
                                            <div className="flex items-center gap-1.5">
                                              <span>
                                                {line.source_pr_number}
                                                {line.line_no !== null
                                                  ? ` #${line.line_no}`
                                                  : ""}
                                              </span>
                                              {line.is_triggering_line && (
                                                <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[9px] font-bold uppercase bg-amber-100 text-amber-800 border border-amber-300">
                                                  <Zap className="h-2.5 w-2.5" />
                                                  Triggering Line
                                                </span>
                                              )}
                                            </div>
                                          </td>
                                          <td className="py-2 px-3 text-gray-700 max-w-xs truncate">
                                            {line.item_description || "—"}
                                          </td>
                                          <td className="py-2 px-3 text-gray-600 whitespace-nowrap">
                                            {line.requestor_name || "—"}
                                          </td>
                                          <td className="py-2 px-3 text-gray-500 whitespace-nowrap">
                                            {line.request_date || "—"}
                                          </td>
                                          <td className="py-2 px-3 whitespace-nowrap">
                                            <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-gray-100 text-gray-700">
                                              {line.pr_status || "Committed"}
                                            </span>
                                          </td>
                                          <td className="py-2 px-3 text-right font-bold text-gray-900 whitespace-nowrap">
                                            {formatCurrency(
                                              Number(line.amount_gst)
                                            )}
                                          </td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              )}
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
                <tfoot className="bg-gray-50 border-t-2 border-gray-200 font-bold">
                  <tr>
                    <td className="p-3 text-gray-700 uppercase text-xs">
                      Total Lab Summary
                    </td>
                    <td className="p-3 text-right text-gray-900">
                      {formatCurrency(selectedLabDetails.budget)}
                    </td>
                    <td className="p-3 text-right text-rose-600">
                      {formatCurrency(selectedLabDetails.actual)}
                    </td>
                    <td
                      className={`p-3 text-right ${
                        selectedLabDetails.budget - selectedLabDetails.actual <
                        0
                          ? "text-red-600"
                          : "text-emerald-600"
                      }`}
                    >
                      {formatCurrency(
                        selectedLabDetails.budget - selectedLabDetails.actual
                      )}
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}