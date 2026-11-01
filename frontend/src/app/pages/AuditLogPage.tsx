import { useState, useEffect } from "react";
import { Navigate } from "react-router";
import { Card } from "../components/ui/card";
import { ShieldAlert, Search, Eye, RotateCcw, X } from "lucide-react";
import { Button } from "../components/ui/button";
import { useAuth } from "../context/AuthContext";

// --- HELPER FUNCTIONS FOR CLEAN FORMATTING ---
const formatKeyName = (key: string) => {
  return key
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
};

const RenderData = ({
  data,
  compareData,
  type,
  categories,
  labs,
  labGroups,
  roles,
}: {
  data: any;
  compareData: any;
  type: "old" | "new";
  categories: Record<string, string>;
  labs: Record<string, string>;
  labGroups: Record<string, string>;
  roles: Record<string, string>;
}) => {
  if (!data || Object.keys(data).length === 0) {
    return (
      <div className="p-6 text-sm text-gray-400 italic text-center flex-1 flex items-center justify-center">
        {type === "old" ? "None / Newly Created" : "None / Deleted"}
      </div>
    );
  }

  const hasComparison = compareData && Object.keys(compareData).length > 0;

  return (
    <div className="p-4 space-y-3 flex-1 overflow-y-auto m-0">
      {Object.entries(data).map(([key, value]) => {
        // --- TRANSLATE RAW IDs TO HUMAN-READABLE NAMES ---
        let label = formatKeyName(key);
        let displayValue = String(value);

        if ((key === "assigned_lab_id" || key === "suggested_lab_id") && value) {
          label = key === "assigned_lab_id" ? "Assigned Lab" : "Suggested Lab";
          displayValue = labs[String(value)] || `Lab ID: ${value}`;
        } else if (
          (key === "assigned_lab_group_id" || key === "suggested_lab_group_id") &&
          value
        ) {
          label =
            key === "assigned_lab_group_id"
              ? "Assigned Lab Group"
              : "Suggested Lab Group";
          displayValue = labGroups[String(value)] || `Group ID: ${value}`;
        } else if (key === "suggested_category_id" && value) {
          label = "Suggested Category";
          displayValue = categories[String(value)] || `Category ID: ${value}`;
        } else if (key === "role_id" && value) {
          label = "Role";
          displayValue = roles[String(value)] || `Role ID: ${value}`;
        } else if (key === "is_primary" && typeof value === "boolean") {
          label = "IC Assignment Type";
          displayValue = value ? "Primary Lab IC" : "Secondary Lab IC";
        } else if (key === "is_active" && typeof value === "boolean") {
          label = "Account Status";
          displayValue = value ? "Active" : "Deactivated";
        } else if (key === "budget" && typeof value === "number") {
          displayValue = `$${Number(value).toLocaleString(undefined, {
            minimumFractionDigits: 2,
          })}`;
        }

        const isNestedObject = typeof value === "object" && value !== null;

        // Determine if top-level field changed
        const otherVal = hasComparison ? compareData[key] : undefined;
        const isKeyMissingInOther = hasComparison && !(key in compareData);
        const isScalarChanged =
          !isNestedObject &&
          hasComparison &&
          (isKeyMissingInOther || String(value) !== String(otherVal));

        const isNestedChanged =
          isNestedObject &&
          hasComparison &&
          JSON.stringify(value) !== JSON.stringify(otherVal);

        const isHighlighted = isScalarChanged || isNestedChanged;

        const containerClasses = isHighlighted
          ? type === "old"
            ? "bg-red-50/70 border border-red-200 border-l-4 border-l-red-500 rounded-md p-3"
            : "bg-green-50/70 border border-green-200 border-l-4 border-l-green-500 rounded-md p-3"
          : "border-b border-gray-100 pb-3 px-1 last:border-0 last:pb-0";

        const badgeText = isKeyMissingInOther
          ? type === "old"
            ? "Removed"
            : "Added"
          : "Changed";

        return (
          <div
            key={key}
            className={`flex flex-col transition-colors ${containerClasses}`}
          >
            <div className="flex items-center justify-between mb-1.5">
              <span
                className={`text-[10px] font-bold uppercase tracking-wider ${
                  isHighlighted
                    ? type === "old"
                      ? "text-red-700"
                      : "text-green-700"
                    : "text-gray-400"
                }`}
              >
                {label}
              </span>
              {isHighlighted && (
                <span
                  className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded ${
                    type === "old"
                      ? "bg-red-100 text-red-700"
                      : "bg-green-100 text-green-700"
                  }`}
                >
                  {badgeText}
                </span>
              )}
            </div>

            <div className="text-sm font-medium text-gray-800 break-words">
              {isNestedObject ? (
                <div className="flex flex-col gap-1.5 mt-1">
                  {Object.entries(value).map(([k, v]) => {
                    const isBudget =
                      key === "budgets" || key === "spent_by_category";
                    const innerLabel = isBudget
                      ? categories[k] || `Category ID ${k}`
                      : formatKeyName(k);

                    const innerDisplayValue = isBudget
                      ? `$${Number(v).toLocaleString(undefined, {
                          minimumFractionDigits: 2,
                        })}`
                      : String(v);

                    const otherNestedObj =
                      hasComparison &&
                      typeof otherVal === "object" &&
                      otherVal !== null
                        ? otherVal
                        : null;
                    const isInnerMissing =
                      otherNestedObj !== null && !(k in otherNestedObj);
                    const isInnerModified =
                      otherNestedObj !== null &&
                      !isInnerMissing &&
                      String(v) !== String(otherNestedObj[k]);
                    const isInnerChanged = isInnerMissing || isInnerModified;

                    const innerBoxClasses = isInnerChanged
                      ? type === "old"
                        ? "bg-red-100/80 border-red-300 text-red-900 ring-1 ring-red-200"
                        : "bg-green-100/80 border-green-300 text-green-900 ring-1 ring-green-200"
                      : "bg-white border-gray-200 text-gray-700";

                    const innerBadge = isInnerMissing
                      ? type === "old"
                        ? "Removed"
                        : "New"
                      : isInnerModified
                      ? "Updated"
                      : null;

                    return (
                      <div
                        key={k}
                        className={`flex justify-between items-center px-3 py-2 rounded-md border shadow-sm ${innerBoxClasses}`}
                      >
                        <div className="flex items-center gap-2">
                          <span
                            className={`text-xs font-medium ${
                              isInnerChanged
                                ? type === "old"
                                  ? "text-red-800 font-semibold"
                                  : "text-green-800 font-semibold"
                                : "text-gray-500"
                            }`}
                          >
                            {innerLabel}
                          </span>
                          {innerBadge && (
                            <span
                              className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded ${
                                type === "old"
                                  ? "bg-red-200/80 text-red-800"
                                  : "bg-green-200/80 text-green-800"
                              }`}
                            >
                              {innerBadge}
                            </span>
                          )}
                        </div>
                        <span
                          className={`text-xs font-bold ${
                            isInnerChanged
                              ? type === "old"
                                ? "text-red-900 line-through decoration-red-400/70"
                                : "text-green-900"
                              : "text-gray-900"
                          }`}
                        >
                          {innerDisplayValue}
                        </span>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <span
                  className={`capitalize ${
                    isScalarChanged
                      ? type === "old"
                        ? "text-red-900 font-bold line-through decoration-red-400/70"
                        : "text-green-900 font-bold"
                      : "text-gray-800"
                  }`}
                >
                  {displayValue}
                </span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};

export function AuditLogPage() {
  const { user } = useAuth();
  const [logs, setLogs] = useState<any[]>([]);
  const [categories, setCategories] = useState<Record<string, string>>({});
  const [labs, setLabs] = useState<Record<string, string>>({});
  const [labGroups, setLabGroups] = useState<Record<string, string>>({});
  const [roles, setRoles] = useState<Record<string, string>>({});
  const [users, setUsers] = useState<Record<string, string>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedLog, setSelectedLog] = useState<any | null>(null);
  const [userFilter, setUserFilter] = useState("all");
  const [actionFilter, setActionFilter] = useState("");
  const [moduleFilter, setModuleFilter] = useState("");
  const [debouncedActionFilter, setDebouncedActionFilter] = useState("");
  const [debouncedModuleFilter, setDebouncedModuleFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [sortOrder, setSortOrder] = useState<"newest" | "oldest">("newest");
  const [loadError, setLoadError] = useState("");

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      setDebouncedActionFilter(actionFilter);
      setDebouncedModuleFilter(moduleFilter);
    }, 300);
    return () => window.clearTimeout(timeoutId);
  }, [actionFilter, moduleFilter]);

  useEffect(() => {
    const fetchReferences = async () => {
      try {
        const [catRes, labRes, groupRes, roleRes, userRes] = await Promise.all([
            fetch(`${API_BASE_URL}/api/config/categories`, {
              credentials: "include",
            }),
            fetch(`${API_BASE_URL}/api/config/labs`, {
              credentials: "include",
            }),
            fetch(`${API_BASE_URL}/api/config/labgroups`, {
              credentials: "include",
            }),
            fetch(`${API_BASE_URL}/api/auth/roles`, {
              credentials: "include",
            }),
            fetch(`${API_BASE_URL}/api/auth/users`, {
              credentials: "include",
            }),
          ]);

        if (catRes.ok) {
          const data = await catRes.json();
          const map: Record<string, string> = {};
          data.forEach((item: any) => (map[String(item.id)] = item.name));
          setCategories(map);
        }
        if (labRes.ok) {
          const data = await labRes.json();
          const map: Record<string, string> = {};
          data.forEach((item: any) => (map[String(item.id)] = item.name));
          setLabs(map);
        }
        if (groupRes.ok) {
          const data = await groupRes.json();
          const map: Record<string, string> = {};
          data.forEach((item: any) => (map[String(item.id)] = item.name));
          setLabGroups(map);
        }
        if (roleRes.ok) {
          const data = await roleRes.json();
          const map: Record<string, string> = {};
          data.forEach((item: any) => (map[String(item.id)] = item.name));
          setRoles(map);
        }
        if (userRes.ok) {
          const data = await userRes.json();
          const map: Record<string, string> = {};
          data.forEach((item: any) => {
            const uid = item.user_id || item.id;
            if (uid) {
              map[String(uid)] = item.full_name || item.email;
            }
          });
          setUsers(map);
        }
      } catch (err) {
        console.error(err);
      }
    };

    if (user?.role === "admin") void fetchReferences();
  }, [API_BASE_URL, user]);

  useEffect(() => {
    if (user?.role !== "admin") return;
    const controller = new AbortController();
    const fetchLogs = async () => {
      setIsLoading(true);
      setLoadError("");
      const params = new URLSearchParams({ limit: "500", sort: sortOrder });
      if (userFilter !== "all") params.set("user_id", userFilter);
      if (debouncedActionFilter.trim())
        params.set("action", debouncedActionFilter.trim());
      if (debouncedModuleFilter.trim())
        params.set("module", debouncedModuleFilter.trim());
      if (dateFrom) params.set("date_from", dateFrom);
      if (dateTo) params.set("date_to", dateTo);
      try {
        const response = await fetch(`${API_BASE_URL}/api/audit/?${params}`, {
          credentials: "include",
          signal: controller.signal,
        });
        if (!response.ok) throw new Error("Could not load audit logs.");
        setLogs(await response.json());
      } catch (err) {
        if (!controller.signal.aborted) {
          setLoadError(err instanceof Error ? err.message : "Could not load audit logs.");
        }
      } finally {
        if (!controller.signal.aborted) setIsLoading(false);
      }
    };
    void fetchLogs();
    return () => controller.abort();
  }, [
    API_BASE_URL,
    debouncedActionFilter,
    dateFrom,
    dateTo,
    debouncedModuleFilter,
    sortOrder,
    user,
    userFilter,
  ]);

  if (user?.role !== "admin") return <Navigate to="/403" replace />;

  // --- SMART TARGET RESOLVER ---
  const getTargetName = (log: any) => {
    const entityLower = (log.entity_name || "").toLowerCase();
    if (log.entity_name === "Lab" && labs[log.record_id])
      return labs[log.record_id];
    if (log.entity_name === "LabGroup" && labGroups[log.record_id])
      return labGroups[log.record_id];
    if (log.entity_name === "SpendingCategory" && categories[log.record_id])
      return categories[log.record_id];

    if (entityLower.includes("user") || log.entity_name === "Authentication") {
      if (users[log.record_id]) return users[log.record_id];
      if (log.record_id.includes("@")) return log.record_id;
    }
    if (log.entity_name === "FiscalYear")
      return log.new_value?.name || `ID: ${log.record_id}`;

    const payload = log.new_value || log.old_value;
    if (payload) {
      if (payload.name) return payload.name;
      if (payload.filename) return payload.filename;
      if (payload.lab_name) return payload.lab_name;
      if (payload.category_name) return payload.category_name;
      if (payload.code) return payload.code;
      if (payload.email) return payload.email;
    }

    return `ID: ${log.record_id}`;
  };

  const filteredLogs = logs.filter((log) => {
    const targetMatch = getTargetName(log)
      .toLowerCase()
      .includes(searchTerm.toLowerCase());
    return (
      targetMatch ||
      log.action_type.toLowerCase().includes(searchTerm.toLowerCase()) ||
      log.entity_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      log.user_name.toLowerCase().includes(searchTerm.toLowerCase())
    );
  });

  return (
    <div className="h-full overflow-auto bg-[#f8f9fa] relative">
      <div className="bg-white p-4 border-b border-border flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-red-50 rounded-lg">
            <ShieldAlert className="h-5 w-5 text-red-600" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-gray-900">
              System Audit Logs
            </h2>
            <p className="text-xs text-gray-500">
              Immutable record of system activities.
            </p>
          </div>
        </div>
        <div className="relative w-72">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search logs..."
            className="w-full pl-9 pr-4 py-2 border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-[#1e3a8a]/20"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
      </div>

      <div className="p-6">
        <div className="mb-4 border-y border-gray-200 bg-white px-4 py-3">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
            <label className="text-xs font-medium text-gray-600">
              User
              <select
                value={userFilter}
                onChange={(event) => setUserFilter(event.target.value)}
                className="mt-1 h-9 w-full border border-border bg-white px-2 text-sm"
              >
                <option value="all">All users</option>
                {Object.entries(users)
                  .sort(([, a], [, b]) => a.localeCompare(b))
                  .map(([id, name]) => (
                    <option key={id} value={id}>{name}</option>
                  ))}
              </select>
            </label>
            <label className="text-xs font-medium text-gray-600">
              Action
              <input
                value={actionFilter}
                onChange={(event) => setActionFilter(event.target.value)}
                placeholder="e.g. update"
                className="mt-1 h-9 w-full border border-border px-2 text-sm"
              />
            </label>
            <label className="text-xs font-medium text-gray-600">
              Module
              <input
                value={moduleFilter}
                onChange={(event) => setModuleFilter(event.target.value)}
                placeholder="e.g. user or lab"
                className="mt-1 h-9 w-full border border-border px-2 text-sm"
              />
            </label>
            <label className="text-xs font-medium text-gray-600">
              From
              <input
                type="date"
                value={dateFrom}
                max={dateTo || undefined}
                onChange={(event) => setDateFrom(event.target.value)}
                className="mt-1 h-9 w-full border border-border px-2 text-sm"
              />
            </label>
            <label className="text-xs font-medium text-gray-600">
              To
              <input
                type="date"
                value={dateTo}
                min={dateFrom || undefined}
                onChange={(event) => setDateTo(event.target.value)}
                className="mt-1 h-9 w-full border border-border px-2 text-sm"
              />
            </label>
            <div className="flex items-end gap-2">
              <label className="min-w-0 flex-1 text-xs font-medium text-gray-600">
                Timestamp
                <select
                  value={sortOrder}
                  onChange={(event) => setSortOrder(event.target.value as "newest" | "oldest")}
                  className="mt-1 h-9 w-full border border-border bg-white px-2 text-sm"
                >
                  <option value="newest">Newest first</option>
                  <option value="oldest">Oldest first</option>
                </select>
              </label>
              <Button
                type="button"
                variant="outline"
                size="icon"
                title="Reset audit filters"
                onClick={() => {
                  setUserFilter("all");
                  setActionFilter("");
                  setModuleFilter("");
                  setDateFrom("");
                  setDateTo("");
                  setSortOrder("newest");
                  setSearchTerm("");
                }}
              >
                <RotateCcw className="h-4 w-4" />
              </Button>
            </div>
          </div>
          <div className="mt-2 text-xs text-gray-500">
            {isLoading ? "Loading filtered logs..." : `${filteredLogs.length} matching log${filteredLogs.length === 1 ? "" : "s"}`}
          </div>
        </div>
        {loadError && (
          <div className="mb-4 border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {loadError}
          </div>
        )}
        <Card className="bg-white border-gray-200 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-gray-50 border-b border-gray-200 text-gray-500 uppercase text-xs font-bold">
                <tr>
                  <th className="p-4">Timestamp</th>
                  <th className="p-4">User</th>
                  <th className="p-4">Action</th>
                  <th className="p-4">Entity</th>
                  <th className="p-4">Target</th>
                  <th className="p-4 text-center">Changes</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {isLoading ? (
                  <tr>
                    <td colSpan={6} className="p-8 text-center text-gray-400">
                      Loading logs...
                    </td>
                  </tr>
                ) : filteredLogs.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="p-8 text-center text-gray-400">
                      No logs found.
                    </td>
                  </tr>
                ) : (
                  filteredLogs.map((log) => {
                    const actionUpper = (log.action_type || "").toUpperCase();
                    return (
                      <tr key={log.audit_id} className="hover:bg-gray-50/50">
                        <td className="p-4 text-gray-500 whitespace-nowrap">
                          {new Date(log.created_at).toLocaleString()}
                        </td>
                        <td className="p-4 font-medium text-gray-900">
                          {log.user_name}
                        </td>
                        <td className="p-4">
                          <span
                            className={`px-2 py-1 rounded text-[10px] font-bold uppercase tracking-wider ${
                              actionUpper.includes("DELETE") ||
                              actionUpper.includes("DEACTIVATE") ||
                              actionUpper.includes("FAILED")
                                ? "bg-red-50 text-red-600 border border-red-100"
                                : actionUpper.includes("CREATE") ||
                                  actionUpper.includes("ACTIVATE") ||
                                  actionUpper.includes("SUCCESS")
                                ? "bg-green-50 text-green-600 border border-green-100"
                                : "bg-blue-50 text-blue-600 border border-blue-100"
                            }`}
                          >
                            {log.action_type.replace(/_/g, " ")}
                          </span>
                        </td>
                        <td className="p-4 text-gray-600 font-medium">
                          {log.entity_name}
                        </td>
                        <td className="p-4 text-gray-900 font-medium">
                          {getTargetName(log)}
                        </td>
                        <td className="p-4 text-center">
                          {(log.old_value || log.new_value) && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setSelectedLog(log)}
                              className="h-8 text-[#1e3a8a] hover:bg-blue-50"
                            >
                              <Eye className="h-4 w-4 mr-1.5" /> View
                            </Button>
                          )}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      {selectedLog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <Card className="w-full max-w-3xl bg-white shadow-xl overflow-hidden flex flex-col max-h-[85vh]">
            <div className="flex justify-between items-center p-5 border-b border-gray-200 bg-gray-50 shrink-0">
              <div>
                <h3 className="text-lg font-bold text-gray-900">
                  Change Details
                </h3>
                <p className="text-sm text-gray-500">
                  {selectedLog.action_type.replace(/_/g, " ")} on{" "}
                  {selectedLog.entity_name} ({getTargetName(selectedLog)})
                </p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setSelectedLog(null)}
              >
                <X className="h-5 w-5 text-gray-500" />
              </Button>
            </div>

            <div className="p-6 overflow-y-auto grid grid-cols-2 gap-6 bg-gray-50/50">
              {/* Left Column: Old Value */}
              <div className="bg-white rounded-lg border border-red-100 shadow-sm overflow-hidden flex flex-col">
                <div className="bg-red-50/80 border-b border-red-100 p-2.5 text-xs font-bold text-red-700 uppercase tracking-wider text-center shrink-0">
                  Old Value (Before)
                </div>
                <RenderData
                  data={selectedLog.old_value}
                  compareData={selectedLog.new_value}
                  type="old"
                  categories={categories}
                  labs={labs}
                  labGroups={labGroups}
                  roles={roles}
                />
              </div>

              {/* Right Column: New Value */}
              <div className="bg-white rounded-lg border border-green-100 shadow-sm overflow-hidden flex flex-col">
                <div className="bg-green-50/80 border-b border-green-100 p-2.5 text-xs font-bold text-green-700 uppercase tracking-wider text-center shrink-0">
                  New Value (After)
                </div>
                <RenderData
                  data={selectedLog.new_value}
                  compareData={selectedLog.old_value}
                  type="new"
                  categories={categories}
                  labs={labs}
                  labGroups={labGroups}
                  roles={roles}
                />
              </div>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
