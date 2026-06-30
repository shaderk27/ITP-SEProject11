import { Fragment, useEffect, useMemo, useState } from "react";
import {
  DollarSign,
  TrendingUp,
  AlertCircle,
  Wallet,
  Percent,
  Clock,
  Activity,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { KPICard } from "../components/shared/KPICard";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { FilterBar } from "../components/shared/FilterBar";
import { StatusBadge } from "../components/shared/StatusBadge";
import { RoleInfo } from "../components/shared/RoleInfo";
import { useAuth } from "../context/AuthContext";
import {
  getBreakdown,
  getSpendingSummary,
  listLabGroups,
} from "../services/dashboardService";
import type {
  BreakdownLabGroup,
  BreakdownResponse,
  LabGroupSummary,
  SpendingSummary,
} from "../types/dashboard";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

const budgetData = [
  { month: "Jan", budget: 45000, actual: 42000 },
  { month: "Feb", budget: 45000, actual: 46500 },
  { month: "Mar", budget: 45000, actual: 43200 },
  { month: "Apr", budget: 45000, actual: 47800 },
  { month: "May", budget: 45000, actual: 44100 },
  { month: "Jun", budget: 45000, actual: 0 },
];

const categoryData = [
  { category: "Equipment", amount: 28500 },
  { category: "Supplies", amount: 18200 },
  { category: "Services", amount: 15300 },
  { category: "Training", amount: 8900 },
  { category: "Other", amount: 5600 },
];

const recentUploads = [
  { id: "UP-2024-152", date: "2026-05-20", records: 45, status: "processed" },
  { id: "UP-2024-151", date: "2026-05-18", records: 28, status: "review" },
  { id: "UP-2024-150", date: "2026-05-15", records: 62, status: "processed" },
];

export function DashboardPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [labGroups, setLabGroups] = useState<LabGroupSummary[]>([]);
  const [spending, setSpending] = useState<SpendingSummary | null>(null);
  const [breakdown, setBreakdown] = useState<BreakdownResponse | null>(null);
  // For Admin defaults to "all"; for Team Lead we auto-set to their lab_group
  // once it's known (see effect below).
  const [selectedGroupId, setSelectedGroupId] = useState<string>(() =>
    user?.labGroupId ? String(user.labGroupId) : "all",
  );
  // Date Range dropdown: all / fy (current fiscal year) / 7d / 30d / 90d.
  const [dateRange, setDateRange] = useState("all");
  // Custom date range (overrides the preset when either is set).
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const customActive = Boolean(startDate || endDate);
  const [loadError, setLoadError] = useState<string | null>(null);
  // Track which lab_group / lab rows are expanded in the drilldown table.
  const [expandedGroups, setExpandedGroups] = useState<Set<number>>(new Set());
  const [expandedLabs, setExpandedLabs] = useState<Set<number>>(new Set());

  // Auto-lock the dropdown to the Team Lead's own lab group whenever the user
  // changes (e.g. login/logout switching identities). Admins keep "all".
  // Done during render with a previous-value guard (React's "adjust state when
  // a prop changes" pattern) instead of an effect, which would fire an extra
  // cascading render on every identity change.
  const userKey = `${user?.role ?? ""}:${user?.labGroupId ?? ""}`;
  const [prevUserKey, setPrevUserKey] = useState<string | null>(null);
  if (userKey !== prevUserKey) {
    setPrevUserKey(userKey);
    if (user?.role === "teamlead" && user.labGroupId) {
      setSelectedGroupId(String(user.labGroupId));
    } else if (user?.role === "admin") {
      setSelectedGroupId("all");
    }
  }

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      listLabGroups(),
      getSpendingSummary(dateRange, startDate, endDate),
      getBreakdown(dateRange, startDate, endDate),
    ])
      .then(([groups, spendingSummary, breakdownResp]) => {
        if (!cancelled) {
          setLabGroups(groups);
          setSpending(spendingSummary);
          setBreakdown(breakdownResp);
          setLoadError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setLoadError(err instanceof Error ? err.message : "Failed to load dashboard data.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [dateRange, startDate, endDate]);

  // Total Budget = raw System Config number, scoped by the Lab Group dropdown.
  // Always shows the full configured budget (not adjusted for spend/pending).
  const totalBudget = useMemo(() => {
    if (selectedGroupId === "all") {
      return labGroups.reduce((sum, g) => sum + g.budget, 0);
    }
    const match = labGroups.find((g) => String(g.id) === selectedGroupId);
    return match ? match.budget : 0;
  }, [labGroups, selectedGroupId]);

  // Actual Spend = sum of Approved lines only. Backend role-filters; Team
  // Lead only ever gets their own group's numbers.
  const actualSpend = useMemo(() => {
    if (!spending) return 0;
    if (selectedGroupId === "all") {
      return Number(spending.total_actual_spend_sgd) || 0;
    }
    const raw = spending.by_lab_group[selectedGroupId];
    return raw ? Number(raw) || 0 : 0;
  }, [spending, selectedGroupId]);

  // Pending = committed but not yet approved. Only used to reduce Available
  // Balance; doesn't affect Total Budget or Utilisation %.
  const pendingSpend = useMemo(() => {
    if (!spending) return 0;
    if (selectedGroupId === "all") {
      return Number(spending.total_pending_sgd) || 0;
    }
    const raw = spending.pending_by_lab_group[selectedGroupId];
    return raw ? Number(raw) || 0 : 0;
  }, [spending, selectedGroupId]);

  // Available = Total Budget - Approved - Pending.
  // Utilisation        = Approved / Total Budget (already-spent share).
  // Projected Util     = (Approved + Pending) / Total Budget (worst-case share
  //                      if every pending line gets approved). Useful as a
  //                      proactive "you're about to run out" indicator.
  const availableBalance = totalBudget - actualSpend - pendingSpend;
  const utilizationPct = totalBudget > 0 ? (actualSpend / totalBudget) * 100 : 0;
  const projectedUtilizationPct =
    totalBudget > 0 ? ((actualSpend + pendingSpend) / totalBudget) * 100 : 0;

  // Drilldown rows respect the Lab Group dropdown filter so the table mirrors
  // whatever scope the KPI cards above are showing.
  const filteredBreakdown: BreakdownLabGroup[] = useMemo(() => {
    if (!breakdown) return [];
    if (selectedGroupId === "all") return breakdown.lab_groups;
    return breakdown.lab_groups.filter(
      (g) => String(g.lab_group_id) === selectedGroupId,
    );
  }, [breakdown, selectedGroupId]);

  const toggleGroup = (id: number) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleLab = (id: number) => {
    setExpandedLabs((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // "All Lab Groups" only makes sense for users who can see more than one
  // (Admin). Team Lead is locked to their own group, so we omit it.
  const labGroupOptions = [
    ...(isAdmin ? [{ value: "all", label: "All Lab Groups" }] : []),
    ...labGroups.map((g) => ({ value: String(g.id), label: g.name })),
  ];

  return (
    <div className="h-full overflow-auto bg-[#f8f9fa]">
      {/* Filters */}
      <FilterBar
        searchPlaceholder="Search dashboard..."
        onFilterChange={(filterId, value) => {
          if (filterId === "Lab Group") setSelectedGroupId(value);
          if (filterId === "Date Range") {
            // Picking a preset clears any custom range so the preset applies.
            setDateRange(value);
            setStartDate("");
            setEndDate("");
          }
        }}
        filters={[
          {
            label: "Date Range",
            value: dateRange,
            options: [
              { value: "all", label: "All time" },
              { value: "fy", label: "This fiscal year" },
              { value: "7d", label: "Last 7 days" },
              { value: "30d", label: "Last 30 days" },
              { value: "90d", label: "Last 90 days" },
            ],
          },
          {
            label: "Lab Group",
            value: selectedGroupId,
            options: labGroupOptions,
          },
        ]}
      />

      {/* Custom date range — overrides the preset when set. */}
      <div className="flex items-center gap-3 px-4 py-3 bg-white border-b border-border text-sm">
        <span className="text-muted-foreground">Custom range:</span>
        <label className="flex items-center gap-1.5">
          <span className="text-muted-foreground">From</span>
          <input
            type="date"
            lang="en-GB"
            value={startDate}
            max={endDate || undefined}
            onChange={(e) => setStartDate(e.target.value)}
            className="rounded-md border border-border px-2 py-1"
          />
        </label>
        <label className="flex items-center gap-1.5">
          <span className="text-muted-foreground">To</span>
          <input
            type="date"
            lang="en-GB"
            value={endDate}
            min={startDate || undefined}
            onChange={(e) => setEndDate(e.target.value)}
            className="rounded-md border border-border px-2 py-1"
          />
        </label>
        {customActive && (
          <>
            <span className="text-xs text-blue-600">
              Custom range active — preset ignored
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setStartDate("");
                setEndDate("");
              }}
            >
              Clear
            </Button>
          </>
        )}
      </div>

      <div className="p-6 space-y-6">
        {/* Role Info */}
        <RoleInfo />

        {loadError && (
          <Card className="p-4 bg-[#fef2f2] border-[#fecaca]">
            <p className="text-sm text-[#b91c1c]">{loadError}</p>
          </Card>
        )}

        {/* KPI Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-6 gap-6">
          <KPICard
            title="Total Budget"
            value={formatCurrency(totalBudget)}
            icon={DollarSign}
            status="info"
          />
          <KPICard
            title="Actual Spend"
            value={formatCurrency(actualSpend)}
            icon={TrendingUp}
            status="info"
          />
          <KPICard
            title="Pending Amount"
            value={formatCurrency(pendingSpend)}
            icon={Clock}
            status="info"
          />
          <KPICard
            title="Available Balance"
            value={formatCurrency(availableBalance)}
            icon={Wallet}
            status="info"
          />
          <KPICard
            title="Utilisation %"
            value={`${utilizationPct.toFixed(1)}%`}
            icon={Percent}
            status={utilizationPct >= 95 ? "error" : utilizationPct >= 80 ? "warning" : "info"}
          />
          <KPICard
            title="Projected Utilisation %"
            value={`${projectedUtilizationPct.toFixed(1)}%`}
            icon={Activity}
            status={
              projectedUtilizationPct >= 95
                ? "error"
                : projectedUtilizationPct >= 80
                  ? "warning"
                  : "info"
            }
          />
        </div>

        {/* Drilldown: Lab Group → Lab → Category */}
        <Card className="p-6 bg-white border-border">
          <h3 className="text-lg font-semibold mb-4 text-foreground">
            Budget Breakdown
          </h3>
          {!breakdown ? (
            <p className="text-sm text-muted-foreground">Loading breakdown…</p>
          ) : filteredBreakdown.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No budget or spending data in this scope yet. Set budgets in System Config and commit a batch to see numbers here.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-[#f8f9fa]">
                  <tr className="border-b border-border">
                    <th className="text-left p-3 text-xs font-medium text-muted-foreground">Name</th>
                    <th className="text-right p-3 text-xs font-medium text-muted-foreground">Budget</th>
                    <th className="text-right p-3 text-xs font-medium text-muted-foreground">Actual Spend</th>
                    <th className="text-right p-3 text-xs font-medium text-muted-foreground">Pending</th>
                    <th className="text-right p-3 text-xs font-medium text-muted-foreground">Available</th>
                    <th className="text-right p-3 text-xs font-medium text-muted-foreground">Util %</th>
                    <th className="text-right p-3 text-xs font-medium text-muted-foreground">Proj %</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredBreakdown.map((group) => {
                    const groupOpen = expandedGroups.has(group.lab_group_id);
                    return (
                      <Fragment key={`g-${group.lab_group_id}`}>
                        <tr
                          className="border-b border-border hover:bg-[#f8f9fa] cursor-pointer"
                          onClick={() => toggleGroup(group.lab_group_id)}
                        >
                          <td className="p-3 text-sm font-semibold text-foreground">
                            <span className="inline-flex items-center gap-2">
                              {groupOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                              {group.lab_group_name}
                            </span>
                          </td>
                          <td className="p-3 text-sm text-right font-medium text-foreground">{formatCurrency(Number(group.budget_sgd))}</td>
                          <td className="p-3 text-sm text-right text-foreground">{formatCurrency(Number(group.actual_spend_sgd))}</td>
                          <td className="p-3 text-sm text-right text-foreground">{formatCurrency(Number(group.pending_sgd))}</td>
                          <td className="p-3 text-sm text-right font-medium text-foreground">{formatCurrency(Number(group.available_balance_sgd))}</td>
                          <td className={`p-3 text-sm text-right font-medium ${pctColor(group.utilisation_pct)}`}>{group.utilisation_pct.toFixed(1)}%</td>
                          <td className={`p-3 text-sm text-right font-medium ${pctColor(group.projected_utilisation_pct)}`}>{group.projected_utilisation_pct.toFixed(1)}%</td>
                        </tr>
                        {groupOpen &&
                          group.labs.map((lab) => {
                            const labOpen = expandedLabs.has(lab.lab_id);
                            return (
                              <Fragment key={`l-${lab.lab_id}`}>
                                <tr
                                  className="border-b border-border bg-[#fafafa] hover:bg-[#f3f4f6] cursor-pointer"
                                  onClick={() => toggleLab(lab.lab_id)}
                                >
                                  <td className="p-3 pl-10 text-sm text-foreground">
                                    <span className="inline-flex items-center gap-2">
                                      {labOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                                      {lab.lab_name}
                                    </span>
                                  </td>
                                  <td className="p-3 text-sm text-right text-foreground">{formatCurrency(Number(lab.budget_sgd))}</td>
                                  <td className="p-3 text-sm text-right text-foreground">{formatCurrency(Number(lab.actual_spend_sgd))}</td>
                                  <td className="p-3 text-sm text-right text-foreground">{formatCurrency(Number(lab.pending_sgd))}</td>
                                  <td className="p-3 text-sm text-right text-foreground">{formatCurrency(Number(lab.available_balance_sgd))}</td>
                                  <td className={`p-3 text-sm text-right ${pctColor(lab.utilisation_pct)}`}>{lab.utilisation_pct.toFixed(1)}%</td>
                                  <td className={`p-3 text-sm text-right ${pctColor(lab.projected_utilisation_pct)}`}>{lab.projected_utilisation_pct.toFixed(1)}%</td>
                                </tr>
                                {labOpen &&
                                  lab.categories.map((cat) => (
                                    <tr
                                      key={`c-${lab.lab_id}-${cat.category_id}`}
                                      className="border-b border-border bg-[#f5f5f5]"
                                    >
                                      <td className="p-3 pl-16 text-sm text-muted-foreground">{cat.category_name}</td>
                                      <td className="p-3 text-sm text-right text-muted-foreground">{formatCurrency(Number(cat.budget_sgd))}</td>
                                      <td className="p-3 text-sm text-right text-muted-foreground">{formatCurrency(Number(cat.actual_spend_sgd))}</td>
                                      <td className="p-3 text-sm text-right text-muted-foreground">{formatCurrency(Number(cat.pending_sgd))}</td>
                                      <td className="p-3 text-sm text-right text-muted-foreground">{formatCurrency(Number(cat.available_balance_sgd))}</td>
                                      <td className={`p-3 text-sm text-right ${pctColor(cat.utilisation_pct)}`}>{cat.utilisation_pct.toFixed(1)}%</td>
                                      <td className={`p-3 text-sm text-right ${pctColor(cat.projected_utilisation_pct)}`}>{cat.projected_utilisation_pct.toFixed(1)}%</td>
                                    </tr>
                                  ))}
                              </Fragment>
                            );
                          })}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {/* Charts Row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Budget vs Actual Chart */}
          <Card className="p-6 bg-white border-border">
            <h3 className="text-lg font-semibold mb-4 text-foreground">
              Budget vs Actual Spending
            </h3>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={budgetData} barGap={8} barCategoryGap="20%">
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="month" stroke="#6b7280" />
                <YAxis stroke="#6b7280" />
                <Tooltip />
                <Legend />
                <Bar dataKey="budget" fill="#1e3a8a" name="Budget" minPointSize={5} radius={[4, 4, 0, 0]} />
                <Bar dataKey="actual" fill="#3b82f6" name="Actual" minPointSize={5} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>

          {/* Spending by Category */}
          <Card className="p-6 bg-white border-border">
            <h3 className="text-lg font-semibold mb-4 text-foreground">
              Spending by Category
            </h3>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={categoryData} layout="vertical" barCategoryGap="20%">
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis type="number" stroke="#6b7280" />
                <YAxis dataKey="category" type="category" stroke="#6b7280" />
                <Tooltip />
                <Bar dataKey="amount" fill="#0d9488" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </div>

        {/* Monthly Trend */}
        <Card className="p-6 bg-white border-border">
          <h3 className="text-lg font-semibold mb-4 text-foreground">
            Monthly Spending Trend
          </h3>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={budgetData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="month" stroke="#6b7280" />
              <YAxis stroke="#6b7280" />
              <Tooltip />
              <Legend />
              <Line
                type="monotone"
                dataKey="budget"
                stroke="#1e3a8a"
                strokeWidth={2}
                name="Budget"
              />
              <Line
                type="monotone"
                dataKey="actual"
                stroke="#3b82f6"
                strokeWidth={2}
                name="Actual"
              />
            </LineChart>
          </ResponsiveContainer>
        </Card>

        {/* Recent Activity */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card className="p-6 bg-white border-border">
            <h3 className="text-lg font-semibold mb-4 text-foreground">
              Recent Uploads
            </h3>
            <div className="space-y-3">
              {recentUploads.map((upload) => (
                <div
                  key={upload.id}
                  className="flex items-center justify-between py-3 border-b border-border last:border-0"
                >
                  <div>
                    <p className="text-sm font-medium text-foreground">
                      {upload.id}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {upload.date} • {upload.records} records
                    </p>
                  </div>
                  <StatusBadge
                    status={
                      upload.status === "processed" ? "approved" : "pending"
                    }
                  >
                    {upload.status === "processed" ? "Processed" : "Review"}
                  </StatusBadge>
                </div>
              ))}
            </div>
          </Card>

          <Card className="p-6 bg-white border-border">
            <h3 className="text-lg font-semibold mb-4 text-foreground">
              Active Alerts
            </h3>
            <div className="space-y-3">
              <div className="flex items-start gap-3 p-3 bg-[#fef2f2] rounded-lg border border-[#fecaca]">
                <AlertCircle className="h-5 w-5 text-[#dc2626] mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-[#dc2626]">
                    Budget Exceeded
                  </p>
                  <p className="text-xs text-[#991b1b] mt-1">
                    W3L1 - Food Processing exceeded threshold by 12%
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-3 p-3 bg-[#fef3c7] rounded-lg border border-[#fde68a]">
                <AlertCircle className="h-5 w-5 text-[#d97706] mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-[#d97706]">
                    Approaching Threshold
                  </p>
                  <p className="text-xs text-[#92400e] mt-1">
                    W4L2 - Materials Testing at 88% utilization
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-3 p-3 bg-[#fef3c7] rounded-lg border border-[#fde68a]">
                <AlertCircle className="h-5 w-5 text-[#d97706] mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-[#d97706]">
                    Review Required
                  </p>
                  <p className="text-xs text-[#92400e] mt-1">
                    28 records pending team lead approval
                  </p>
                </div>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

function formatCurrency(amount: number): string {
  return amount.toLocaleString("en-SG", {
    style: "currency",
    currency: "SGD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  });
}

// Threshold colors for utilisation / projected utilisation cells.
// Matches the KPI card thresholds: ≥95% = error (red), ≥80% = warning (yellow).
function pctColor(pct: number): string {
  if (pct >= 95) return "text-[#dc2626]";
  if (pct >= 80) return "text-[#d97706]";
  return "text-foreground";
}
