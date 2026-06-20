import { Card } from "../components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { FilterBar } from "../components/shared/FilterBar";
import { StatusBadge } from "../components/shared/StatusBadge";
import { useAuth } from "../context/AuthContext";
import { Info } from "lucide-react";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

// Mock Data Definitions
const labGroupData = [
  { name: "W3 - Food Processing", budget: 180000, actual: 98500, utilization: 54.7 },
  { name: "W4 - Materials Testing", budget: 150000, actual: 76200, utilization: 50.8 },
  { name: "W5 - Analytics", budget: 120000, actual: 42100, utilization: 35.1 },
  { name: "W6 - Quality Control", budget: 100000, actual: 0, utilization: 0 },
  { name: "General", budget: 90000, actual: 7000, utilization: 7.8 },
];

const labData = [
  { name: "W3L1 - Food Pilot Plant", code: "W3L1", budget: 65000, actual: 72800, status: "exceeded" },
  { name: "W3L2 - Food Chemistry", code: "W3L2", budget: 45000, actual: 18200, status: "healthy" },
  { name: "W3L3 - Food Microbiology", code: "W3L3", budget: 40000, actual: 7500, status: "healthy" },
  { name: "W4L1 - Tensile Testing", code: "W4L1", budget: 55000, actual: 38100, status: "healthy" },
  { name: "W4L2 - Materials Analysis", code: "W4L2", budget: 50000, actual: 38100, status: "warning" },
];

const categoryData = [
  { name: "Equipment", value: 98500, color: "#1e3a8a" },
  { name: "Supplies", value: 67200, color: "#3b82f6" },
  { name: "Services", value: 42100, color: "#0d9488" },
  { name: "Training", value: 15800, color: "#f59e0b" },
  { name: "Other", value: 200, color: "#6b7280" },
];

const trendData = [
  { month: "Jan", w3: 18500, w4: 12200, w5: 8100 },
  { month: "Feb", w3: 22100, w4: 15800, w5: 6500 },
  { month: "Mar", w3: 19800, w4: 18900, w5: 9200 },
  { month: "Apr", w3: 21200, w4: 16100, w5: 10800 },
  { month: "May", w3: 17900, w4: 13200, w5: 7500 },
];

export function ReportsPage() {
  const { user } = useAuth();

  // Filter lab group data based on user authorization bounds
  const getFilteredLabGroupData = () => {
    if (user?.role === "admin") {
      return labGroupData;
    } 
    
    if (user?.role === "teamlead") {
      // Team Lead sees only their assigned lab groups (e.g. matching "W3")
      return labGroupData.filter(group =>
        user.assignedLabs?.some(assignedLab => 
          group.name.toLowerCase().startsWith(assignedLab.substring(0, 2).toLowerCase())
        )
      );
    } 
    
    if (user?.role === "labic") {
      // Lab IC sees only their specific target lab's overarching cluster
      const firstLabCode = user.assignedLabs?.[0];
      if (!firstLabCode) return [];
      return labGroupData.filter(group =>
        group.name.toLowerCase().startsWith(firstLabCode.substring(0, 2).toLowerCase())
      );
    }
    
    return [];
  };

  // Filter specific sub-labs based on user assignment parameters
  const getFilteredLabData = () => {
    if (user?.role === "admin") {
      return labData;
    } 
    
    if (user?.role === "teamlead" || user?.role === "labic") {
      // Matches clean array strings against user tracking identifiers 
      return labData.filter(lab =>
        user.assignedLabs?.some(assignedLab => lab.code === assignedLab)
      );
    }
    
    return [];
  };

  const filteredLabGroupData = getFilteredLabGroupData();
  const filteredLabData = getFilteredLabData();

  return (
    <div className="h-full overflow-auto bg-[#f8f9fa]">
      <FilterBar
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
            label: "Fiscal Year",
            options: [
              { value: "2026", label: "FY 2026" },
              { value: "2025", label: "FY 2025" },
              { value: "2024", label: "FY 2024" },
            ],
          },
        ]}
        showExport={true}
      />

      <div className="p-6">
        <div className="mb-6">
          <h2 className="text-2xl font-semibold text-foreground">Reports</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Budget utilization and spending analysis
          </p>
        </div>

        {user?.role !== "admin" && (
          <Card className="p-4 bg-[#f0f9ff] border-[#bfdbfe] mb-6">
            <div className="flex items-start gap-3">
              <Info className="h-5 w-5 text-[#2563eb] flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm text-[#1e40af] font-medium">
                  {user?.role === "labic" ? "Lab IC View" : "Team Lead View"}
                </p>
                <p className="text-xs text-[#1e3a8a] mt-1">
                  Data is filtered to show only your assigned labs: {user?.assignedLabs?.join(", ")}
                </p>
              </div>
            </div>
          </Card>
        )}

        <Tabs defaultValue="labgroup" className="w-full">
          <TabsList className="bg-white border border-border mb-6">
            <TabsTrigger value="labgroup">By Lab Group</TabsTrigger>
            <TabsTrigger value="lab">By Lab</TabsTrigger>
            <TabsTrigger value="category">By Category</TabsTrigger>
            <TabsTrigger value="trends">Trends</TabsTrigger>
          </TabsList>

          <TabsContent value="labgroup" className="space-y-6">
            <Card className="p-6 bg-white border-border">
              <h3 className="text-lg font-semibold mb-4 text-foreground">
                Budget vs Actual by Lab Group
              </h3>
              <ResponsiveContainer width="100%" height={400}>
                <BarChart data={filteredLabGroupData} barGap={8} barCategoryGap="20%">
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis dataKey="name" stroke="#6b7280" />
                  <YAxis stroke="#6b7280" />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="budget" fill="#1e3a8a" name="Budget" minPointSize={5} radius={[4, 4, 0, 0]} />
                  <Bar dataKey="actual" fill="#3b82f6" name="Actual Spend" minPointSize={5} radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </Card>

            <Card className="p-6 bg-white border-border">
              <h3 className="text-lg font-semibold mb-4 text-foreground">
                Lab Group Summary
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-[#f8f9fa]">
                    <tr className="border-b border-border">
                      <th className="text-left p-3 text-sm font-medium text-muted-foreground">
                        Lab Group
                      </th>
                      <th className="text-right p-3 text-sm font-medium text-muted-foreground">
                        Budget
                      </th>
                      <th className="text-right p-3 text-sm font-medium text-muted-foreground">
                        Actual
                      </th>
                      <th className="text-right p-3 text-sm font-medium text-muted-foreground">
                        Remaining
                      </th>
                      <th className="text-right p-3 text-sm font-medium text-muted-foreground">
                        Utilization
                      </th>
                      <th className="text-left p-3 text-sm font-medium text-muted-foreground">
                        Status
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredLabGroupData.map((row, idx) => {
                      const remaining = row.budget - row.actual;
                      const status =
                        row.utilization > 100
                          ? "exceeded"
                          : row.utilization > 85
                          ? "warning"
                          : "healthy";
                      return (
                        <tr
                          key={idx}
                          className="border-b border-border last:border-0 hover:bg-[#f8f9fa]"
                        >
                          <td className="p-3 text-sm font-medium text-foreground">
                            {row.name}
                          </td>
                          <td className="p-3 text-sm text-right text-muted-foreground">
                            ${row.budget.toLocaleString()}
                          </td>
                          <td className="p-3 text-sm text-right font-medium text-foreground">
                            ${row.actual.toLocaleString()}
                          </td>
                          <td className="p-3 text-sm text-right text-muted-foreground">
                            ${remaining.toLocaleString()}
                          </td>
                          <td className="p-3 text-sm text-right font-medium text-foreground">
                            {row.utilization.toFixed(1)}%
                          </td>
                          <td className="p-3">
                            <StatusBadge status={status as any}>
                              {status === "exceeded"
                                ? "Exceeded"
                                : status === "warning"
                                ? "Warning"
                                : "Healthy"}
                            </StatusBadge>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Card>
          </TabsContent>

          <TabsContent value="lab" className="space-y-6">
            <Card className="p-6 bg-white border-border">
              <h3 className="text-lg font-semibold mb-4 text-foreground">
                Top 5 Labs by Spending
              </h3>
              <ResponsiveContainer width="100%" height={400}>
                <BarChart data={filteredLabData} layout="vertical" barGap={8} barCategoryGap="20%">
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis type="number" stroke="#6b7280" />
                  <YAxis dataKey="name" type="category" stroke="#6b7280" width={180} />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="budget" fill="#1e3a8a" name="Budget" minPointSize={5} radius={[0, 4, 4, 0]} />
                  <Bar dataKey="actual" fill="#3b82f6" name="Actual" minPointSize={5} radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </Card>

            <Card className="p-6 bg-white border-border">
              <h3 className="text-lg font-semibold mb-4 text-foreground">
                Lab Details
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-[#f8f9fa]">
                    <tr className="border-b border-border">
                      <th className="text-left p-3 text-sm font-medium text-muted-foreground">
                        Lab
                      </th>
                      <th className="text-right p-3 text-sm font-medium text-muted-foreground">
                        Budget
                      </th>
                      <th className="text-right p-3 text-sm font-medium text-muted-foreground">
                        Actual
                      </th>
                      <th className="text-right p-3 text-sm font-medium text-muted-foreground">
                        Variance
                      </th>
                      <th className="text-left p-3 text-sm font-medium text-muted-foreground">
                        Status
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredLabData.map((row, idx) => {
                      const variance = row.actual - row.budget;
                      return (
                        <tr
                          key={idx}
                          className="border-b border-border last:border-0 hover:bg-[#f8f9fa]"
                        >
                          <td className="p-3 text-sm font-medium text-foreground">
                            {row.name}
                          </td>
                          <td className="p-3 text-sm text-right text-muted-foreground">
                            ${row.budget.toLocaleString()}
                          </td>
                          <td className="p-3 text-sm text-right font-medium text-foreground">
                            ${row.actual.toLocaleString()}
                          </td>
                          <td
                            className={`p-3 text-sm text-right font-medium ${
                              variance > 0 ? "text-[#dc2626]" : "text-[#059669]"
                            }`}
                          >
                            {variance > 0 ? "+" : ""}${variance.toLocaleString()}
                          </td>
                          <td className="p-3">
                            <StatusBadge status={row.status as any}>
                              {row.status === "exceeded"
                                ? "Exceeded"
                                : row.status === "warning"
                                ? "Warning"
                                : "Healthy"}
                            </StatusBadge>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Card>
          </TabsContent>

          <TabsContent value="category" className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <Card className="p-6 bg-white border-border">
                <h3 className="text-lg font-semibold mb-4 text-foreground">
                  Spending by Category
                </h3>
                <ResponsiveContainer width="100%" height={350}>
                  <PieChart>
                    <Pie
                      data={categoryData}
                      cx="50%"
                      cy="50%"
                      labelLine={false}
                      label={({ name, percent }) =>
                        `${name} ${(percent * 100).toFixed(0)}%`
                      }
                      outerRadius={120}
                      fill="#8884d8"
                      dataKey="value"
                    >
                      {categoryData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              </Card>

              <Card className="p-6 bg-white border-border">
                <h3 className="text-lg font-semibold mb-4 text-foreground">
                  Category Breakdown
                </h3>
                <div className="space-y-4">
                  {categoryData.map((item, idx) => {
                    const total = categoryData.reduce((sum, i) => sum + i.value, 0);
                    const percentage = ((item.value / total) * 100).toFixed(1);
                    return (
                      <div key={idx}>
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <div
                              className="h-3 w-3 rounded"
                              style={{ backgroundColor: item.color }}
                            />
                            <span className="text-sm font-medium text-foreground">
                              {item.name}
                            </span>
                          </div>
                          <span className="text-sm text-muted-foreground">
                            ${item.value.toLocaleString()} ({percentage}%)
                          </span>
                        </div>
                        <div className="w-full h-2 bg-[#f1f5f9] rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full"
                            style={{
                              width: `${percentage}%`,
                              backgroundColor: item.color,
                            }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </Card>
            </div>
          </TabsContent>

          <TabsContent value="trends" className="space-y-6">
            <Card className="p-6 bg-white border-border">
              <h3 className="text-lg font-semibold mb-4 text-foreground">
                Monthly Spending Trends
              </h3>
              <ResponsiveContainer width="100%" height={400}>
                <LineChart data={trendData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis dataKey="month" stroke="#6b7280" />
                  <YAxis stroke="#6b7280" />
                  <Tooltip />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="w3"
                    stroke="#1e3a8a"
                    strokeWidth={2}
                    name="W3 - Food Processing"
                  />
                  <Line
                    type="monotone"
                    dataKey="w4"
                    stroke="#3b82f6"
                    strokeWidth={2}
                    name="W4 - Materials Testing"
                  />
                  <Line
                    type="monotone"
                    dataKey="w5"
                    stroke="#0d9488"
                    strokeWidth={2}
                    name="W5 - Analytics"
                  />
                </LineChart>
              </ResponsiveContainer>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}