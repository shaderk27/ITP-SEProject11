import { useState, useEffect, useMemo } from "react";
import { Navigate } from "react-router";
import { Card } from "../components/ui/card";
import { AlertCircle, Building2, Search, X, FileText } from "lucide-react";
import { Button } from "../components/ui/button";
import { useAuth } from "../context/AuthContext";

interface Category { id: number; name: string; }
interface LabGroupData { id: number; name: string; wbs_code: string; budget: number; spent: number; }
interface LabData { id: number; group_id: number; group: string; code: string; name: string; budget: number; spent: number; budgets: Record<string, number>; spent_by_category: Record<string, number>; }

interface LabAlert { id: string; labCode: string; labName: string; budget: number; actual: number; utilization: number; type: string; threshold: number; budgets: Record<string, number>; spentByCategory: Record<string, number>; }
interface GroupAlert { groupId: number; groupName: string; wbsCode: string; totalBudget: number; totalSpent: number; groupUtilization: number; groupType: string; labs: LabAlert[]; }

export function AlertsPage() {
  const { user, hasPermission } = useAuth();

  const [labGroups, setLabGroups] = useState<LabGroupData[]>([]);
  const [labs, setLabs] = useState<LabData[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const [searchTerm, setSearchTerm] = useState("");
  const [selectedType, setSelectedType] = useState("all");
  const [selectedGroup, setSelectedGroup] = useState("all");

  const [selectedLabDetails, setSelectedLabDetails] = useState<LabAlert | null>(null);

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [groupsRes, labsRes, catsRes] = await Promise.all([
          fetch(`${API_BASE_URL}/api/config/labgroups`, { credentials: "include" }),
          fetch(`${API_BASE_URL}/api/config/labs`, { credentials: "include" }),
          fetch(`${API_BASE_URL}/api/config/categories`, { credentials: "include" })
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

  const getSeverity = (util: number) => {
    if (util >= 100) return { type: "exceeded", threshold: 100, label: "Exceeded", colors: "bg-[#fef2f2] border-[#fecaca] text-[#dc2626]" };
    if (util >= 95) return { type: "critical", threshold: 95, label: "95% Critical", colors: "bg-[#fff1f2] border-[#fecdd3] text-[#e11d48]" };
    if (util >= 80) return { type: "alert", threshold: 80, label: "80% Alert", colors: "bg-[#fffbeb] border-[#fde68a] text-[#d97706]" };
    if (util >= 50) return { type: "warning", threshold: 50, label: "50% Warning", colors: "bg-[#eff6ff] border-[#bfdbfe] text-[#2563eb]" };
    return { type: "none", threshold: 0, label: "Healthy", colors: "bg-gray-50 border-gray-200 text-gray-500" };
  };

  const groupedAlerts = useMemo(() => {
    const result: GroupAlert[] = [];

    const groupsToProcess = labGroups.filter(g => {
        if (user?.role === "admin") return true;
        if (user?.role === "teamlead") return g.id === user?.labGroupId;
        if (user?.role === "labic") {
            const myLab = labs.find(l => l.id === user?.labId);
            return g.id === myLab?.group_id;
        }
        return false;
    });

    groupsToProcess.forEach(group => {
        const isLabIC = user?.role === "labic";

        // Lab ICs do not calculate group utilization to keep the parent card neutral
        const groupUtil = (!isLabIC && group.budget > 0) ? (group.spent / group.budget) * 100 : 0;
        const groupSeverity = getSeverity(groupUtil);

        let groupLabs = labs.filter(l => l.group_id === group.id && l.budget > 0);

        if (isLabIC) {
            groupLabs = groupLabs.filter(l => l.id === user?.labId);
        }

        const labAlerts: LabAlert[] = [];
        groupLabs.forEach(lab => {
            const util = (lab.spent / lab.budget) * 100;
            const severity = getSeverity(util);

            if (severity.type !== "none" || groupSeverity.type !== "none") {
                labAlerts.push({
                    id: `LAB-${lab.id}`,
                    labCode: lab.code,
                    labName: lab.name,
                    budget: lab.budget,
                    actual: lab.spent || 0,
                    utilization: Number(util.toFixed(1)),
                    type: severity.type,
                    threshold: severity.threshold,
                    budgets: lab.budgets,
                    spentByCategory: lab.spent_by_category
                });
            }
        });

        if (groupSeverity.type !== "none" || labAlerts.length > 0) {
            labAlerts.sort((a, b) => b.utilization - a.utilization);

            result.push({
                groupId: group.id,
                groupName: group.name,
                wbsCode: group.wbs_code,
                totalBudget: isLabIC ? 0 : group.budget, // Zeroed out for ICs
                totalSpent: isLabIC ? 0 : group.spent,   // Zeroed out for ICs
                groupUtilization: Number(groupUtil.toFixed(1)),
                groupType: groupSeverity.type,
                labs: labAlerts
            });
        }
    });

    return result.sort((a, b) => b.groupUtilization - a.groupUtilization);
  }, [labGroups, labs, user]);


  const filteredGroups = useMemo(() => {
    return groupedAlerts.filter(g => {
        if (selectedGroup !== "all" && g.groupId.toString() !== selectedGroup) return false;
        if (selectedType !== "all" && g.groupType !== selectedType) {
            const childMatches = g.labs.some(l => l.type === selectedType);
            if (!childMatches) return false;
        }

        if (searchTerm) {
            const term = searchTerm.toLowerCase();
            const groupMatches = g.groupName.toLowerCase().includes(term) || g.wbsCode.toLowerCase().includes(term);
            const childMatches = g.labs.some(l => l.labCode.toLowerCase().includes(term) || l.labName.toLowerCase().includes(term));
            if (!groupMatches && !childMatches) return false;
        }

        return true;
    });
  }, [groupedAlerts, searchTerm, selectedType, selectedGroup]);


  if (!hasPermission("alerts:view")) return <Navigate to="/403" replace />;
  if (isLoading) return <div className="p-8 text-center text-muted-foreground">Loading Alerts...</div>;

  return (
    <div className="h-full overflow-auto bg-[#f8f9fa] relative">

      {user?.role !== "labic" && (
        <div className="bg-white p-4 border-b border-border flex flex-col sm:flex-row gap-4 items-center justify-between shadow-sm">
          <div className="relative w-full sm:w-96">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
            <input type="text" placeholder="Search by Group or Lab name..." className="w-full pl-9 pr-4 py-2 border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-[#1e3a8a]/20" value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} />
          </div>
          <div className="flex w-full sm:w-auto gap-4">
            <select className="w-full sm:w-auto px-3 py-2 border border-border rounded-md text-sm bg-white outline-none" value={selectedType} onChange={(e) => setSelectedType(e.target.value)}>
              <option value="all">All Thresholds</option>
              <option value="exceeded">Exceeded (&gt;100%)</option>
              <option value="critical">Critical (95%)</option>
              <option value="alert">Alert (80%)</option>
              <option value="warning">Warning (50%)</option>
            </select>

            {user?.role === "admin" && (
                <select className="w-full sm:w-auto px-3 py-2 border border-border rounded-md text-sm bg-white outline-none" value={selectedGroup} onChange={(e) => setSelectedGroup(e.target.value)}>
                <option value="all">All Lab Groups</option>
                {labGroups.map((g) => (<option key={g.id} value={g.id}>{g.name}</option>))}
                </select>
            )}
          </div>
        </div>
      )}

      <div className="p-6 space-y-6">
        <div>
            <h2 className="text-2xl font-semibold text-foreground">Alerts Center</h2>
            <p className="text-sm text-muted-foreground mt-1">Hierarchical budget threshold warnings.</p>
        </div>

        <div className="space-y-6">
            {filteredGroups.length === 0 ? (
                <div className="p-12 text-center text-gray-500 bg-white border border-gray-200 rounded-lg shadow-sm">
                    No budget alerts found. All managed lab groups are healthy.
                </div>
            ) : (
                filteredGroups.map(group => {
                    const groupSev = getSeverity(group.groupUtilization);

                    return (
                        <Card key={group.groupId} className="bg-white border-gray-200 shadow-sm overflow-hidden">
                            <div className={`p-5 border-b-4 ${groupSev.type === 'none' ? 'border-b-gray-200 bg-gray-50' : groupSev.colors.split(' ')[1].replace('border-', 'border-b-')} ${groupSev.type === 'none' ? '' : groupSev.colors.split(' ')[0]}`}>
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-3">
                                        <div className={`p-2 rounded-lg bg-white/60 shadow-sm`}>
                                            <Building2 className={`h-6 w-6 ${groupSev.colors.split(' ')[2]}`} />
                                        </div>
                                        <div>
                                            <h3 className="text-lg font-black text-gray-900 tracking-tight flex items-center gap-2">
                                                {group.groupName}

                                                {/* Lab ICs see a neutral 'Parent Group' tag instead of group health */}
                                                {user?.role !== "labic" ? (
                                                    <span className={`px-2 py-0.5 text-xs rounded-full border bg-white ${groupSev.colors}`}>
                                                        {groupSev.type === 'none' ? 'Group Budget Healthy' : `Group Budget ${groupSev.label}`}
                                                    </span>
                                                ) : (
                                                    <span className="px-2 py-0.5 text-xs rounded-full border bg-gray-100 text-gray-600 border-gray-200">
                                                        Parent Group
                                                    </span>
                                                )}
                                            </h3>
                                            <p className="text-sm font-medium text-gray-600 font-mono mt-0.5">{group.wbsCode}</p>
                                        </div>
                                    </div>

                                    {/* HIDDEN FROM LAB ICS */}
                                    {user?.role !== "labic" && (
                                        <div className="text-right bg-white/60 p-2.5 rounded-lg border border-black/5">
                                            <p className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-0.5">Group Utilisation</p>
                                            <p className={`text-xl font-black ${groupSev.colors.split(' ')[2]}`}>{group.groupUtilization}%</p>
                                        </div>
                                    )}
                                </div>

                                {/* HIDDEN FROM LAB ICS */}
                                {user?.role !== "labic" && (
                                    <div className="mt-4 grid grid-cols-2 gap-4">
                                        <div className="bg-white/50 rounded p-2">
                                            <p className="text-xs text-gray-500 font-medium">Total Budget</p>
                                            <p className="text-sm font-bold text-gray-900">${group.totalBudget.toLocaleString(undefined, { minimumFractionDigits: 2 })}</p>
                                        </div>
                                        <div className="bg-white/50 rounded p-2">
                                            <p className="text-xs text-gray-500 font-medium">Group Spent</p>
                                            <p className="text-sm font-bold text-gray-900">${group.totalSpent.toLocaleString(undefined, { minimumFractionDigits: 2 })}</p>
                                        </div>
                                    </div>
                                )}
                            </div>

                            <div className="p-4 space-y-3 bg-gray-50/50">
                                {group.labs.length === 0 ? (
                                    <p className="text-sm text-gray-400 italic text-center p-4">All individual labs within this group are healthy.</p>
                                ) : (
                                    group.labs.map(lab => {
                                        const labSev = getSeverity(lab.utilization);
                                        return (
                                            <div key={lab.id} className={`p-4 rounded-lg border bg-white shadow-sm flex items-center justify-between ${labSev.colors}`}>
                                                <div className="flex-1">
                                                    <div className="flex items-center gap-2 mb-1">
                                                        <AlertCircle className={`h-4 w-4 ${labSev.colors.split(' ')[2]}`} />
                                                        <h4 className="font-bold text-gray-900">{lab.labCode} — {lab.labName}</h4>
                                                        <span className={`text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded ${labSev.colors}`}>{labSev.label}</span>
                                                    </div>
                                                    <div className="flex items-center gap-6 mt-2 text-sm">
                                                        <div><span className="text-gray-500 text-xs">Allocated:</span> <span className="font-semibold text-gray-800">${lab.budget.toLocaleString()}</span></div>
                                                        <div><span className="text-gray-500 text-xs">Spent:</span> <span className="font-semibold text-gray-800">${lab.actual.toLocaleString()}</span></div>
                                                        <div><span className="text-gray-500 text-xs">Utilisation:</span> <span className={`font-bold ${labSev.colors.split(' ')[2]}`}>{lab.utilization}%</span></div>
                                                    </div>
                                                </div>
                                                <Button variant="outline" size="sm" className="bg-white h-8 text-xs font-semibold shrink-0 ml-4" onClick={() => setSelectedLabDetails(lab)}>
                                                    <FileText className="h-3.5 w-3.5 mr-1.5" /> Breakdown
                                                </Button>
                                            </div>
                                        )
                                    })
                                )}
                            </div>
                        </Card>
                    )
                })
            )}
        </div>
      </div>

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
                    const allocated = selectedLabDetails.budgets?.[cat.id] || 0;
                    const spent = selectedLabDetails.spentByCategory?.[cat.id] || 0;
                    if (allocated === 0 && spent === 0) return null;
                    const balance = allocated - spent;

                    return (
                      <tr key={cat.id} className="hover:bg-gray-50/50 transition-colors">
                        <td className="p-3 font-medium text-gray-800">{cat.name}</td>
                        <td className="p-3 text-right text-gray-600">${allocated.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                        <td className="p-3 text-right text-rose-600 font-medium">${spent.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                        <td className={`p-3 text-right font-bold ${balance < 0 ? 'text-red-600' : 'text-emerald-600'}`}>${balance.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}