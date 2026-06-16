import { DollarSign, TrendingUp, AlertCircle, FileText } from "lucide-react";
import { KPICard } from "../components/shared/KPICard";
import { Card } from "../components/ui/card";
import { FilterBar } from "../components/shared/FilterBar";
import { StatusBadge } from "../components/shared/StatusBadge";
import { RoleInfo } from "../components/shared/RoleInfo";
import { useAuth } from "../context/AuthContext";
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

  // Filter data based on user role and assigned labs
  const getFilteredData = () => {
    if (user?.role === "admin") {
      return { budgetData, categoryData, recentUploads };
    } else if (user?.role === "teamlead") {
      // Filter for assigned labs
      return { budgetData, categoryData, recentUploads };
    } else if (user?.role === "labic") {
      // Show only their specific lab data
      return { budgetData, categoryData, recentUploads };
    }
    return { budgetData, categoryData, recentUploads };
  };

  const filteredData = getFilteredData();

  return (
    <div className="h-full overflow-auto bg-[#f8f9fa]">
      {/* Filters */}
      <FilterBar
        searchPlaceholder="Search dashboard..."
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
            options: [
              { value: "all", label: "All Lab Groups" },
              { value: "w3", label: "W3 - Food Processing" },
              { value: "w4", label: "W4 - Materials Testing" },
            ],
          },
        ]}
      />

      <div className="p-6 space-y-6">
        {/* Role Info */}
        <RoleInfo />

        {/* KPI Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <KPICard
            title={user?.role === "labic" ? "Lab Budget" : "Total Budget"}
            value={user?.role === "labic" ? "$65,000" : "$540,000"}
            icon={DollarSign}
            status="info"
          />
          <KPICard
            title="Actual Spend"
            value={user?.role === "labic" ? "$72,800" : "$223,800"}
            icon={TrendingUp}
            trend={{ value: user?.role === "labic" ? "+12% over budget" : "+8.2% vs last month", isPositive: user?.role === "labic" ? false : true }}
            status={user?.role === "labic" ? "error" : "success"}
          />
          <KPICard
            title="Utilization"
            value={user?.role === "labic" ? "112%" : "41.4%"}
            icon={TrendingUp}
            status={user?.role === "labic" ? "error" : "warning"}
          />
          <KPICard
            title="Active Alerts"
            value={user?.role === "labic" ? "1" : "3"}
            icon={AlertCircle}
            status="error"
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
