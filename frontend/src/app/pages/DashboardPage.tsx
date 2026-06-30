import { useEffect, useMemo, useState } from "react";
import { DollarSign, TrendingUp, AlertCircle, Wallet, Percent, Clock } from "lucide-react";
import { KPICard } from "../components/shared/KPICard";
import { Card } from "../components/ui/card";
import { FilterBar } from "../components/shared/FilterBar";
import { StatusBadge } from "../components/shared/StatusBadge";
import { RoleInfo } from "../components/shared/RoleInfo";
import { useAuth } from "../context/AuthContext";
import { getSpendingSummary, listLabGroups } from "../services/dashboardService";
import type { LabGroupSummary, SpendingSummary } from "../types/dashboard";
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
  // For Admin defaults to "all"; for Team Lead we auto-set to their lab_group
  // once it's known (see effect below).
  const [selectedGroupId, setSelectedGroupId] = useState<string>(() =>
    user?.labGroupId ? String(user.labGroupId) : "all",
  );
  const [loadError, setLoadError] = useState<string | null>(null);

  // Auto-lock the dropdown to the Team Lead's own lab group whenever the
  // user changes (e.g. login/logout switching identities). Admins keep "all".
  useEffect(() => {
    if (user?.role === "teamlead" && user.labGroupId) {
      setSelectedGroupId(String(user.labGroupId));
    } else if (user?.role === "admin") {
      setSelectedGroupId("all");
    }
  }, [user?.role, user?.labGroupId]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([listLabGroups(), getSpendingSummary()])
      .then(([groups, spendingSummary]) => {
        if (!cancelled) {
          setLabGroups(groups);
          setSpending(spendingSummary);
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
  }, []);

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
  // Utilisation = Approved / Total Budget (pending does NOT affect it).
  const availableBalance = totalBudget - actualSpend - pendingSpend;
  const utilizationPct = totalBudget > 0 ? (actualSpend / totalBudget) * 100 : 0;

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
        }}
        filters={[
          {
            label: "Date Range",
            options: [
              { value: "7d", label: "Last 7 days" },
              { value: "30d", label: "Last 30 days" },
              { value: "90d", label: "Last 90 days" },
              { value: "ytd", label: "Year to date" },
            ],
          },
          {
            label: "Lab Group",
            value: selectedGroupId,
            options: labGroupOptions,
          },
        ]}
      />

      <div className="p-6 space-y-6">
        {/* Role Info */}
        <RoleInfo />

        {loadError && (
          <Card className="p-4 bg-[#fef2f2] border-[#fecaca]">
            <p className="text-sm text-[#b91c1c]">{loadError}</p>
          </Card>
        )}

        {/* KPI Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5 gap-6">
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
        </div>

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
