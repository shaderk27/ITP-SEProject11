import { useState, useEffect, useMemo } from "react";
import { Navigate } from "react-router";
import { Card } from "../components/ui/card";
import { AlertCircle, TrendingUp, Info, AlertTriangle, Search, X, FileText } from "lucide-react";
import { Button } from "../components/ui/button";
import { useAuth } from "../context/AuthContext";

export function AlertsPage() {
  const { user, hasPermission, canAccessLabGroup } = useAuth();
  
  const [labs, setLabs] = useState<any[]>([]);
  const [categories, setCategories] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  // Filter States
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedType, setSelectedType] = useState("all");
  const [selectedGroup, setSelectedGroup] = useState("all");
  
  // Modal State
  const [selectedLabDetails, setSelectedLabDetails] = useState<any>(null);

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

  // 1. Fetch the Live Lab Data & Categories
  useEffect(() => {
    const fetchData = async () => {
      try {
        const [labsRes, catsRes] = await Promise.all([
          fetch(`${API_BASE_URL}/api/config/labs`, { credentials: "include" }),
          fetch(`${API_BASE_URL}/api/config/categories`, { credentials: "include" })
        ]);
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

  // Page-level guard
  if (!hasPermission("alerts:view")) {
    return <Navigate to="/403" replace />;
  }

  // 2. Dynamically Generate Alerts based on Real Math
  const allAlerts = useMemo(() => {
    return labs
      .filter((lab) => lab.budget > 0) // Only look at labs with a budget
      .map((lab) => {
        const util = (lab.spent / lab.budget) * 100;
        
        let type = "none";
        let threshold = 0;
        
        if (util >= 100) { type = "exceeded"; threshold = 100; }
        else if (util >= 95) { type = "critical"; threshold = 95; }
        else if (util >= 80) { type = "alert"; threshold = 80; }
        else if (util >= 50) { type = "warning"; threshold = 50; }

        return {
          id: `LAB-${lab.id}`,
          labGroupId: lab.group_id,
          labGroupName: lab.group || "Unassigned",
          labCode: lab.code,
          labName: lab.name,
          budget: lab.budget,
          actual: lab.spent || 0,
          utilization: Number(util.toFixed(1)),
          type,
          threshold,
          budgets: lab.budgets,                 // Keep original category allocations
          spentByCategory: lab.spent_by_category // Keep original category spending
        };
      })
      .filter((a) => a.type !== "none" && canAccessLabGroup(a.labGroupId))
      .sort((a, b) => b.utilization - a.utilization); // Sort highest danger first
  }, [labs, canAccessLabGroup]);

  // Extract unique lab groups for the working dropdown
  const uniqueGroups = useMemo(() => {
    const groups = new Map();
    allAlerts.forEach((a) => groups.set(a.labGroupId, a.labGroupName));
    return Array.from(groups.entries()).map(([id, name]) => ({
      id: id.toString(),
      name,
    }));
  }, [allAlerts]);

  // 3. Apply the working filters
  const filteredAlerts = useMemo(() => {
    return allAlerts.filter((a) => {
      const matchesSearch = `${a.labCode} ${a.labName}`
        .toLowerCase()
        .includes(searchTerm.toLowerCase());
      const matchesType = selectedType === "all" || a.type === selectedType;
      const matchesGroup =
        selectedGroup === "all" || a.labGroupId.toString() === selectedGroup;
      
      return matchesSearch && matchesType && matchesGroup;
    });
  }, [allAlerts, searchTerm, selectedType, selectedGroup]);


  const showLabBanner = user?.role !== "admin" && user?.labGroupId != null;

  if (isLoading) {
    return <div className="p-8 text-center text-muted-foreground">Loading Alerts...</div>;
  }

  return (
    <div className="h-full overflow-auto bg-[#f8f9fa] relative">
      
      {/* FILTER BAR */}
      <div className="bg-white p-4 border-b border-border flex flex-col sm:flex-row gap-4 items-center justify-between shadow-sm">
        <div className="relative w-full sm:w-96">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search alerts by Lab Code or Name..."
            className="w-full pl-9 pr-4 py-2 border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-[#1e3a8a]/20 focus:border-[#1e3a8a]"
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
          
          <select
            className="w-full sm:w-auto px-3 py-2 border border-border rounded-md text-sm bg-white outline-none"
            value={selectedGroup}
            onChange={(e) => setSelectedGroup(e.target.value)}
          >
            <option value="all">All Lab Groups</option>
            {uniqueGroups.map((g) => (
              <option key={g.id} value={g.id}>{g.name}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="p-6 space-y-6">
        <div>
          <h2 className="text-2xl font-semibold text-foreground">Alerts Center</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Real-time budget threshold warnings and notifications
          </p>
        </div>

        {/* Scoped-view banner for teamlead and labic */}
        {showLabBanner && (
          <Card className="p-4 bg-[#f0f9ff] border-[#bfdbfe]">
            <div className="flex items-start gap-3">
              <Info className="h-5 w-5 text-[#2563eb] flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm text-[#1e40af] font-medium">
                  {user?.role === "teamlead" ? "Team Lead View" : "Lab IC View"}
                </p>
                <p className="text-xs text-[#1e3a8a] mt-1">
                  Showing alerts for your assigned lab group only.
                </p>
              </div>
            </div>
          </Card>
        )}

        {/* 4-CARD DYNAMIC SUMMARY METRICS */}
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
          {/* Exceeded Card */}
          <Card className="p-5 bg-white border-border shadow-sm">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-[#dc2626]/10 flex items-center justify-center">
                <AlertCircle className="h-5 w-5 text-[#dc2626]" />
              </div>
              <div>
                <p className="text-xl font-bold text-foreground">
                  {filteredAlerts.filter((a) => a.type === "exceeded").length}
                </p>
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Exceeded</p>
              </div>
            </div>
          </Card>

          {/* 95% Card */}
          <Card className="p-5 bg-white border-border shadow-sm">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-[#e11d48]/10 flex items-center justify-center">
                <AlertTriangle className="h-5 w-5 text-[#e11d48]" />
              </div>
              <div>
                <p className="text-xl font-bold text-foreground">
                  {filteredAlerts.filter((a) => a.type === "critical").length}
                </p>
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">95% Critical</p>
              </div>
            </div>
          </Card>

          {/* 80% Card */}
          <Card className="p-5 bg-white border-border shadow-sm">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-[#d97706]/10 flex items-center justify-center">
                <TrendingUp className="h-5 w-5 text-[#d97706]" />
              </div>
              <div>
                <p className="text-xl font-bold text-foreground">
                  {filteredAlerts.filter((a) => a.type === "alert").length}
                </p>
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">80% Alert</p>
              </div>
            </div>
          </Card>

          {/* 50% Card */}
          <Card className="p-5 bg-white border-border shadow-sm">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-[#2563eb]/10 flex items-center justify-center">
                <Info className="h-5 w-5 text-[#2563eb]" />
              </div>
              <div>
                <p className="text-xl font-bold text-foreground">
                  {filteredAlerts.filter((a) => a.type === "warning").length}
                </p>
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">50% Warning</p>
              </div>
            </div>
          </Card>
        </div>

        {/* Active Alerts List */}
        <Card className="bg-white border-border shadow-sm">
          <div className="p-6 border-b border-border">
            <h3 className="text-lg font-semibold text-foreground">Triggered Thresholds</h3>
          </div>

          {filteredAlerts.length === 0 ? (
            <div className="p-12 text-center text-muted-foreground text-sm">
              All labs are currently under the 50% utilization threshold!
            </div>
          ) : (
            <div className="divide-y divide-border">
              {filteredAlerts.map((alert) => {
                
                const alertConfig =
                  alert.type === "exceeded" ? {
                    bgColor: "bg-[#fef2f2]", borderColor: "border-[#fecaca]", iconColor: "text-[#dc2626]", barColor: "bg-[#dc2626]", label: "Exceeded",
                  } : alert.type === "critical" ? {
                    bgColor: "bg-[#fff1f2]", borderColor: "border-[#fecdd3]", iconColor: "text-[#e11d48]", barColor: "bg-[#e11d48]", label: "95% Critical",
                  } : alert.type === "alert" ? {
                    bgColor: "bg-[#fffbeb]", borderColor: "border-[#fde68a]", iconColor: "text-[#d97706]", barColor: "bg-[#d97706]", label: "80% Alert",
                  } : {
                    bgColor: "bg-[#eff6ff]", borderColor: "border-[#bfdbfe]", iconColor: "text-[#2563eb]", barColor: "bg-[#2563eb]", label: "50% Warning",
                  };

                return (
                  <div key={alert.id} className="p-6">
                    <div className={`${alertConfig.bgColor} ${alertConfig.borderColor} border rounded-lg p-5`}>
                      <div className="flex items-start gap-4">
                        <AlertCircle className={`h-6 w-6 ${alertConfig.iconColor} flex-shrink-0 mt-0.5`} />
                        <div className="flex-1">
                          <div className="flex items-start justify-between mb-4">
                            <div>
                              <h4 className="font-bold text-gray-900 mb-0.5">
                                {alert.labCode} — {alert.labName}
                              </h4>
                              <p className="text-sm font-medium text-gray-600">
                                {alert.labGroupName}
                              </p>
                            </div>
                            <span className={`px-2.5 py-1 rounded-md text-xs font-bold border ${alertConfig.borderColor} ${alertConfig.bgColor} ${alertConfig.iconColor}`}>
                              {alertConfig.label}
                            </span>
                          </div>

                          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4 bg-white/60 p-3 rounded-md border border-black/5">
                            <div>
                              <p className="text-xs text-muted-foreground mb-1">Allocated Budget</p>
                              <p className="text-sm font-bold text-gray-800">
                                ${alert.budget.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                              </p>
                            </div>
                            <div>
                              <p className="text-xs text-muted-foreground mb-1">Actual Spend</p>
                              <p className="text-sm font-bold text-gray-800">
                                ${alert.actual.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                              </p>
                            </div>
                            <div>
                              <p className="text-xs text-muted-foreground mb-1">Utilization</p>
                              <p className={`text-sm font-bold ${alertConfig.iconColor}`}>
                                {alert.utilization}%
                              </p>
                            </div>
                            <div>
                              <p className="text-xs text-muted-foreground mb-1">Crossed Threshold</p>
                              <p className="text-sm font-bold text-gray-800">
                                {alert.threshold}%
                              </p>
                            </div>
                          </div>

                          <div className="mb-4">
                            <div className="w-full h-2.5 bg-gray-200/80 rounded-full overflow-hidden shadow-inner">
                              <div
                                className={`h-full ${alertConfig.barColor} transition-all duration-500`}
                                style={{ width: `${Math.min(alert.utilization, 100)}%` }}
                              />
                            </div>
                          </div>

                          <div className="flex items-center justify-end">
                            <Button 
                              variant="outline" 
                              size="sm" 
                              className="bg-white h-8 text-xs font-semibold"
                              onClick={() => setSelectedLabDetails(alert)}
                            >
                              <FileText className="h-3.5 w-3.5 mr-1.5" />
                              View Breakdown
                            </Button>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Card>
      </div>

      {/* --- THE SPENDING BREAKDOWN MODAL --- */}
      {selectedLabDetails && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <Card className="w-full max-w-2xl bg-white shadow-xl overflow-hidden">
            <div className="flex justify-between items-start gap-4 p-6 border-b border-border bg-[#f8f9fa]">
              <div>
                <h3 className="text-lg font-bold text-gray-900">Budget Breakdown</h3>
                <p className="text-sm text-gray-500">{selectedLabDetails.labCode} — {selectedLabDetails.labName}</p>
              </div>
              <Button variant="ghost" size="sm" onClick={() => setSelectedLabDetails(null)}><X className="h-4 w-4" /></Button>
            </div>
            
            <div className="p-6">
              <table className="w-full text-sm text-left border-collapse">
                <thead className="bg-gray-50 border-y border-gray-200">
                  <tr>
                    <th className="p-3 font-semibold text-gray-600">Category</th>
                    <th className="p-3 font-semibold text-gray-600 text-right">Allocated</th>
                    <th className="p-3 font-semibold text-gray-600 text-right">Spent</th>
                    <th className="p-3 font-semibold text-gray-600 text-right">Remaining</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {categories.map(cat => {
                    // Extract data based on Category ID
                    const allocated = selectedLabDetails.budgets?.[cat.id] || 0;
                    const spent = selectedLabDetails.spentByCategory?.[cat.id] || 0;
                    
                    // Hide categories that have no allocation AND no spending
                    if (allocated === 0 && spent === 0) return null;
                    
                    const balance = allocated - spent;
                    
                    return (
                      <tr key={cat.id} className="hover:bg-gray-50/50 transition-colors">
                        <td className="p-3 font-medium text-gray-800">{cat.name}</td>
                        <td className="p-3 text-right text-gray-600">
                          ${allocated.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                        </td>
                        <td className="p-3 text-right text-rose-600 font-medium">
                          ${spent.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                        </td>
                        <td className={`p-3 text-right font-bold ${balance < 0 ? 'text-red-600' : 'text-emerald-600'}`}>
                          ${balance.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
                <tfoot className="bg-gray-50 border-y border-gray-200 font-bold">
                  <tr>
                    <td className="p-3 text-gray-800">Total</td>
                    <td className="p-3 text-right text-gray-800">
                      ${selectedLabDetails.budget.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </td>
                    <td className="p-3 text-right text-rose-600">
                      ${selectedLabDetails.actual.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </td>
                    <td className="p-3 text-right text-emerald-600">
                      ${(selectedLabDetails.budget - selectedLabDetails.actual).toLocaleString(undefined, { minimumFractionDigits: 2 })}
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