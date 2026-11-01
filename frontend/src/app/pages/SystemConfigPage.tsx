import React, { useState, useEffect } from "react";
import { Card } from "../components/ui/card";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../components/ui/tabs";
import { Button } from "../components/ui/button";
import { UserManagement } from "../components/config/UserManagement";
import {
  Plus,
  Trash2,
  Edit,
  X,
  ChevronDown,
  ChevronRight,
  Beaker,
  Mail,
  CheckCircle2,
  UserPlus,
  Unlink,
  DollarSign,
  AlertTriangle,
  UserRound,
  Star,
} from "lucide-react";

const formatCurrency = (amount: number = 0) => {
  const absFormatted = Math.abs(amount).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return amount < 0 ? `-$${absFormatted}` : `$${absFormatted}`;
};

const generateVenueTags = (
  rawCode?: string | null,
  rawName?: string | null,
) => {
  try {
    const tags = new Set<string>();
    const code = rawCode ? String(rawCode).trim() : "";
    const name = rawName ? String(rawName).trim() : "";

    if (name) {
      tags.add(name);
      if (name.toLowerCase().endsWith(" lab"))
        tags.add(name.substring(0, name.length - 4).trim());
    }

    if (code) {
      const codeRegex = /^([A-Z]\d+)-(\d+)-([A-Z0-9]+)$/i;
      const match = code.match(codeRegex);
      if (match) {
        const block = match[1].toUpperCase();
        const levelRaw = match[2];
        const room = match[3].toUpperCase();
        const levelShort = parseInt(levelRaw, 10).toString();
        tags.add(`${block}L${levelShort}R${room}`);
        tags.add(`${block}-L${levelShort}-${room}`);
        tags.add(`${block}L${levelShort}${room}`);
        tags.add(code.toUpperCase());
        if (name) {
          const shortName = name.toLowerCase().endsWith(" lab")
            ? name.substring(0, name.length - 4).trim()
            : name;
          tags.add(`${block}L${levelShort} ${shortName}`);
        }
      } else {
        tags.add(code.toUpperCase());
      }
    }
    return Array.from(tags).join(", ");
  } catch {
    return "";
  }
};

export function SystemConfigPage() {
  const [labGroups, setLabGroups] = useState<any[]>([]);
  const [labs, setLabs] = useState<any[]>([]);
  const [categories, setCategories] = useState<any[]>([]);
  const [orphanedLabs, setOrphanedLabs] = useState<any[]>([]);
  const [labicUsers, setLabicUsers] = useState<any[]>([]);
  const [teamleadUsers, setTeamleadUsers] = useState<any[]>([]);
  const [selectedLabIds, setSelectedLabIds] = useState<number[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [expandedGroups, setExpandedGroups] = useState<number[]>([]);

  const [editingGroupId, setEditingGroupId] = useState<number | null>(null);
  const [editingGroupFloor, setEditingGroupFloor] = useState<{
    allocated: number;
    spent: number;
  } | null>(null);

  const [editingLabId, setEditingLabId] = useState<number | null>(null);
  const [editingCategoryId, setEditingCategoryId] = useState<number | null>(
    null,
  );

  const [isGroupModalOpen, setIsGroupModalOpen] = useState(false);
  const [newGroupForm, setNewGroupForm] = useState({
    name: "",
    wbs_code: "",
    description: "",
    budget: "" as string | number,
  });

  const [isCategoryModalOpen, setIsCategoryModalOpen] = useState(false);
  const [newCategoryForm, setNewCategoryForm] = useState({
    name: "",
    description: "",
  });

  const [isLabModalOpen, setIsLabModalOpen] = useState(false);
  const [newLabForm, setNewLabForm] = useState({
    lab_code: "",
    lab_name: "",
    lab_group_id: "",
    ic_name: "",
    ic_email: "",
    venue: "",
    budgets: {} as Record<string, number>,
  });

  // Track which group's unallocated balance and category spend locks to validate against
  const [activeGroupValidation, setActiveGroupValidation] = useState<{
    id: number;
    unallocated: number;
    name: string;
    spentByCategory: Record<string, number>;
    originalBudgets: Record<string, number>;
  } | null>(null);

  const [isAssignLabICModalOpen, setIsAssignLabICModalOpen] = useState(false);
  const [assignTargetLab, setAssignTargetLab] = useState<any | null>(null);
  const [selectedLabICUserId, setSelectedLabICUserId] = useState<number | "">(
    "",
  );

  const [isAssignTeamLeadModalOpen, setIsAssignTeamLeadModalOpen] =
    useState(false);
  const [assignTargetGroup, setAssignTargetGroup] = useState<any | null>(null);
  const [selectedTeamLeadUserId, setSelectedTeamLeadUserId] = useState<
    number | ""
  >("");

  const [periods, setPeriods] = useState<any[]>([]);
  const [selectedPeriodId, setSelectedPeriodId] = useState<number | null>(null);
  const [isPeriodModalOpen, setIsPeriodModalOpen] = useState(false);
  const [newPeriodYear, setNewPeriodYear] = useState("");

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

  const fetchConfigData = async (periodId?: number | null) => {
    const pid = periodId ?? selectedPeriodId;
    const q = pid ? `?period_id=${pid}` : "";
    try {
      const [groupsRes, labsRes, catsRes, orphanedRes, labicRes, teamleadRes] =
        await Promise.all([
          fetch(`${API_BASE_URL}/api/config/labgroups${q}`, {
            credentials: "include",
          }),
          fetch(`${API_BASE_URL}/api/config/labs${q}`, {
            credentials: "include",
          }),
          fetch(`${API_BASE_URL}/api/config/categories`, {
            credentials: "include",
          }),
          fetch(`${API_BASE_URL}/api/config/labs/orphaned`, {
            credentials: "include",
          }),
          fetch(`${API_BASE_URL}/api/auth/users?role=labic`, {
            credentials: "include",
          }),
          fetch(`${API_BASE_URL}/api/auth/users?role=teamlead`, {
            credentials: "include",
          }),
        ]);
      setLabGroups(await groupsRes.json());
      setLabs(await labsRes.json());
      setCategories(await catsRes.json());
      setOrphanedLabs(await orphanedRes.json());
      setLabicUsers(await labicRes.json());
      setTeamleadUsers(await teamleadRes.json());
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/config/periods`, {
          credentials: "include",
        });
        const data = await res.json();
        setPeriods(data);
        if (data.length) setSelectedPeriodId(data[0].id);
      } catch (err) {
        console.error(err);
      }
    })();
  }, [API_BASE_URL]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (selectedPeriodId != null) fetchConfigData(selectedPeriodId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedPeriodId]);

  const handleAddPeriod = async () => {
    const year = parseInt(newPeriodYear, 10);
    if (!year) return;
    try {
      const res = await fetch(`${API_BASE_URL}/api/config/periods`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ year }),
      });
      if (res.ok) {
        const created = await res.json();
        const listRes = await fetch(`${API_BASE_URL}/api/config/periods`, {
          credentials: "include",
        });
        setPeriods(await listRes.json());
        setSelectedPeriodId(created.id);
        setIsPeriodModalOpen(false);
        setNewPeriodYear("");
      } else {
        const err = await res.json().catch(() => ({}));
        alert(err.detail || "Failed to create fiscal year.");
      }
    } catch (err) {
      console.error(err);
    }
  };

  const toggleGroupExpand = (groupId: number) => {
    if (expandedGroups.includes(groupId)) {
      setExpandedGroups(expandedGroups.filter((id) => id !== groupId));
    } else {
      setExpandedGroups([...expandedGroups, groupId]);
    }
  };

  const toggleOrphanedLab = (labId: number) => {
    setSelectedLabIds((prev) =>
      prev.includes(labId)
        ? prev.filter((id) => id !== labId)
        : [...prev, labId],
    );
  };

  const handleSave = async (
    endpoint: string,
    method: string,
    payload: any,
    onSuccess: () => void,
  ) => {
    try {
      const res = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: method,
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        onSuccess();
        fetchConfigData();
      } else {
        alert(await readErrorDetail(res, "Failed to save."));
      }
    } catch (error) {
      console.error(error);
    }
  };

  const handleDelete = async (endpoint: string, name: string) => {
    if (
      !window.confirm(
        `Are you sure you want to permanently delete "${name}"? This action cannot be undone.`,
      )
    )
      return;
    try {
      const res = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: "DELETE",
        credentials: "include",
      });
      if (res.ok) fetchConfigData();
      else alert(await readErrorDetail(res, `Failed to delete ${name}.`));
    } catch {
      alert("A network error occurred while trying to delete.");
    }
  };

  const openEditGroup = (group: any) => {
    setEditingGroupId(group.id);
    setEditingGroupFloor({
      allocated: Number(group.allocated_to_labs || 0),
      spent: Number(group.spent || 0),
    });
    setNewGroupForm({
      name: group.name,
      wbs_code: group.wbs_code || "",
      description: group.description || "",
      budget: group.budget || 0,
    });
    setIsGroupModalOpen(true);
  };

  const openEditCategory = (cat: any) => {
    setEditingCategoryId(cat.id);
    setNewCategoryForm({ name: cat.name, description: cat.description || "" });
    setIsCategoryModalOpen(true);
  };

  const openAddLabToGroup = (group: any) => {
    setEditingLabId(null);
    setActiveGroupValidation({
      id: group.id,
      unallocated: group.unallocated,
      name: group.name,
      spentByCategory: {},
      originalBudgets: {},
    });
    setNewLabForm({
      lab_code: "",
      lab_name: "",
      lab_group_id: group.id,
      ic_name: "",
      ic_email: "",
      venue: "",
      budgets: {},
    });
    setIsLabModalOpen(true);
  };

  const openEditLab = (lab: any) => {
    setEditingLabId(lab.id);
    const parentGroup = labGroups.find((g) => g.id === lab.group_id);
    const labCurrentTotal = Object.values(
      (lab.budgets || {}) as Record<string, number>,
    ).reduce((a, b) => a + b, 0);
    setActiveGroupValidation(
      parentGroup
        ? {
            id: parentGroup.id,
            unallocated: parentGroup.unallocated + labCurrentTotal,
            name: parentGroup.name,
            spentByCategory: lab.spent_by_category || {},
            originalBudgets: lab.budgets || {},
          }
        : null,
    );

    setNewLabForm({
      lab_code: lab.code || "",
      lab_name: lab.name || "",
      lab_group_id: lab.group_id || "",
      ic_name: lab.ic_name || "",
      ic_email: lab.ic_email || "",
      venue: lab.venue || "",
      budgets: lab.budgets || {},
    });
    setIsLabModalOpen(true);
  };

  const resetGroupModal = () => {
    setIsGroupModalOpen(false);
    setEditingGroupId(null);
    setEditingGroupFloor(null);
    setNewGroupForm({ name: "", wbs_code: "", description: "", budget: "" });
    setSelectedLabIds([]);
  };
  const resetCategoryModal = () => {
    setIsCategoryModalOpen(false);
    setEditingCategoryId(null);
    setNewCategoryForm({ name: "", description: "" });
  };
  const resetLabModal = () => {
    setIsLabModalOpen(false);
    setEditingLabId(null);
    setActiveGroupValidation(null);
    setNewLabForm({
      lab_code: "",
      lab_name: "",
      lab_group_id: "",
      ic_name: "",
      ic_email: "",
      venue: "",
      budgets: {},
    });
  };

  const openAssignLabICModal = (lab: any) => {
    setAssignTargetLab(lab);

    const primaryUser = labicUsers.find((u) =>
      u.lab_assignments?.some((a: any) => a.lab_id === lab.id && a.is_primary),
    );

    setSelectedLabICUserId(primaryUser?.user_id ?? "");
    setIsAssignLabICModalOpen(true);
  };
  const resetAssignLabICModal = () => {
    setIsAssignLabICModalOpen(false);
    setAssignTargetLab(null);
    setSelectedLabICUserId("");
  };
  const handleTogglePrimary = async (
    userId: number,
    labId: number,
    newIsPrimary: boolean,
  ) => {
    try {
      const res = await fetch(
        `${API_BASE_URL}/api/auth/users/${userId}/assign-lab`,
        {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
          },
          credentials: "include",
          body: JSON.stringify({
            lab_id: labId,
            is_primary: newIsPrimary,
          }),
        },
      );

      if (res.ok) {
        fetchConfigData();
      } else {
        alert(await readErrorDetail(res, "Failed to update primary status."));
      }
    } catch (error) {
      console.error("Error updating primary status:", error);
      alert("Failed to update primary status.");
    }
  };
  const handleAssignLabIC = async () => {
    if (!assignTargetLab || selectedLabICUserId === "") return;
    try {
      const res = await fetch(
        `${API_BASE_URL}/api/auth/users/${selectedLabICUserId}/assign-lab`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({
            lab_id: assignTargetLab.id,
          }),
        },
      );
      if (res.ok) {
        resetAssignLabICModal();
        fetchConfigData();
      } else {
        alert(await readErrorDetail(res, "Failed to assign Lab IC."));
      }
    } catch (error) {
      console.error(error);
    }
  };

  const handleUnassignLabIC = async (labic: any, labId: number) => {
    const targetUser = labic?.user ?? labic;
    const userId = targetUser?.id ?? targetUser?.user_id;

    if (!userId) {
      alert("Invalid user ID.");
      return;
    }

    const userName = targetUser.full_name || targetUser.name || "this user";

    if (!window.confirm(`Unassign ${userName} from this lab?`)) {
      return;
    }

    try {
      const res = await fetch(
        `${API_BASE_URL}/api/auth/users/${userId}/labs/${labId}`,
        {
          method: "DELETE",
          credentials: "include",
        },
      );

      if (res.ok) {
        fetchConfigData();
      } else {
        alert(await readErrorDetail(res, "Failed to unassign lab."));
      }
    } catch (error) {
      console.error("Error unassigning lab:", error);
      alert("Failed to unassign lab.");
    }
  };
  const openAssignTeamLeadModal = (group: any) => {
    setAssignTargetGroup(group);
    const current = teamleadUsers.find((u) => u.lab_group_id === group.id);
    setSelectedTeamLeadUserId(current?.user_id ?? "");
    setIsAssignTeamLeadModalOpen(true);
  };

  const resetAssignTeamLeadModal = () => {
    setIsAssignTeamLeadModalOpen(false);
    setAssignTargetGroup(null);
    setSelectedTeamLeadUserId("");
  };

  const handleAssignTeamLead = async () => {
    const userId = Number(selectedTeamLeadUserId);

    if (!assignTargetGroup || !userId || isNaN(userId)) {
      alert("Please select a valid Team Lead user.");
      return;
    }

    const labGroupId = assignTargetGroup.id ?? assignTargetGroup.lab_group_id;

    try {
      const res = await fetch(
        `${API_BASE_URL}/api/auth/users/${userId}/assign-labgroup`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ lab_group_id: labGroupId }),
        },
      );

      if (res.ok) {
        resetAssignTeamLeadModal();
        fetchConfigData();
      } else {
        alert(await readErrorDetail(res, "Failed to assign Team Lead."));
      }
    } catch (error) {
      console.error("Error assigning team lead:", error);
      alert("Failed to assign Team Lead.");
    }
  };

  const handleUnassignTeamLead = async (teamlead: any) => {
    if (!teamlead) return;

    const userId = teamlead.id ?? teamlead.user_id;

    if (!userId) {
      console.error("Missing user ID in teamlead object:", teamlead);
      alert("Invalid user ID.");
      return;
    }

    const name = teamlead.full_name || teamlead.name || "this user";

    if (!window.confirm(`Clear Team Lead assignment for ${name}?`)) {
      return;
    }

    try {
      const res = await fetch(
        `${API_BASE_URL}/api/auth/users/${userId}/unassign-scope`,
        {
          method: "PUT",
          credentials: "include",
        },
      );

      if (res.ok) {
        fetchConfigData();
      } else {
        alert(
          await readErrorDetail(res, "Failed to clear Team Lead assignment."),
        );
      }
    } catch (error) {
      console.error("Error unassigning team lead:", error);
      alert("Failed to clear Team Lead assignment.");
    }
  };

  const readErrorDetail = async (res: Response, fallback: string) => {
    try {
      const body = await res.json();
      return typeof body?.detail === "string" ? body.detail : fallback;
    } catch {
      return fallback;
    }
  };

  const currentRequestedTotal = Object.values(newLabForm.budgets).reduce(
    (acc, curr) => acc + (curr || 0),
    0,
  );
  const isBudgetExceeded = activeGroupValidation
    ? currentRequestedTotal > activeGroupValidation.unallocated + 1e-6
    : false;

  // Check if any category budget is being reduced below its already-spent amount
  const violatedCategories = activeGroupValidation
    ? categories.filter((cat) => {
        const key = String(cat.id);
        const spent = Number(activeGroupValidation.spentByCategory?.[key] || 0);
        if (spent <= 0) return false;
        const orig = Number(activeGroupValidation.originalBudgets?.[key] || 0);
        const minAllowed = orig >= spent ? spent : orig;
        const requested = Number(newLabForm.budgets?.[cat.id] || 0);
        return requested + 1e-6 < minAllowed;
      })
    : [];
  const isCategorySpendViolated = violatedCategories.length > 0;

  // Check if Lab Group budget is being reduced below allocated or spent amounts
  const enteredGroupBudget = Number(newGroupForm.budget || 0);
  const minAllowedGroupBudget = editingGroupFloor
    ? Math.max(editingGroupFloor.allocated, editingGroupFloor.spent)
    : 0;
  const isGroupBudgetBelowFloor =
    editingGroupId !== null &&
    editingGroupFloor !== null &&
    enteredGroupBudget + 1e-6 < minAllowedGroupBudget;

  if (isLoading)
    return (
      <div className="p-8 text-center text-muted-foreground">
        Loading system configuration...
      </div>
    );

  return (
    <div className="h-full overflow-auto bg-[#f8f9fa] relative">
      <div className="p-6">
        <div className="mb-6 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold text-foreground">
              System Configuration
            </h2>
            <p className="text-sm text-muted-foreground mt-1">
              Manage lab groups, budgets, categories, and users
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <label className="text-sm font-medium text-muted-foreground">
              Fiscal Year:
            </label>
            <select
              className="border border-border rounded-md px-3 py-2 text-sm bg-white"
              value={selectedPeriodId ?? ""}
              onChange={(e) => {
                if (e.target.value === "__add__") {
                  setIsPeriodModalOpen(true);
                  return;
                }
                setSelectedPeriodId(Number(e.target.value));
              }}
            >
              {periods.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
              <option value="__add__">+ Add Fiscal Year</option>
            </select>
          </div>
        </div>

        <Tabs defaultValue="labgroups" className="w-full">
          <TabsList className="bg-white border border-border mb-6">
            <TabsTrigger
              value="labgroups"
              className="data-[state=active]:bg-gray-900 data-[state=active]:text-white"
            >
              Lab Groups & Budgets
            </TabsTrigger>
            <TabsTrigger
              value="categories"
              className="data-[state=active]:bg-gray-900 data-[state=active]:text-white"
            >
              Categories
            </TabsTrigger>
            <TabsTrigger
              value="users"
              className="data-[state=active]:bg-gray-900 data-[state=active]:text-white"
            >
              Users
            </TabsTrigger>
          </TabsList>

          <TabsContent value="labgroups">
            <Card className="bg-white border-border">
              <div className="p-6 border-b border-border flex items-center justify-between bg-blue-50/30">
                <div>
                  <h3 className="text-lg font-semibold text-foreground">
                    Lab Group Overview
                  </h3>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Define lab group budgets here, then expand a group to
                    allocate funds to specific labs.
                  </p>
                </div>
                <Button
                  onClick={() => {
                    resetGroupModal();
                    setIsGroupModalOpen(true);
                  }}
                  className="bg-[#1e3a8a] hover:bg-[#1e40af] text-white"
                >
                  <Plus className="h-4 w-4 mr-2" /> Add Lab Group
                </Button>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-[#f8f9fa]">
                    <tr className="border-b border-border text-xs uppercase tracking-wider font-semibold text-muted-foreground">
                      <th className="w-12 p-4"></th>
                      <th className="text-left p-4">Group Name</th>
                      <th className="text-left p-4">WBS</th>
                      <th className="text-left p-4">Team Lead</th>
                      <th className="text-right p-4 text-[#1e3a8a]">
                        Total Budget
                      </th>
                      <th className="text-right p-4">Allocated to Labs</th>
                      <th className="text-right p-4 text-[#16a34a]">
                        Unallocated Balance
                      </th>
                      <th className="text-center p-4">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {labGroups.map((group) => {
                      const isExpanded = expandedGroups.includes(group.id);
                      const groupLabs = labs.filter(
                        (l) => l.group_id === group.id,
                      );
                      const teamlead = teamleadUsers.find(
                        (u) => u.lab_group_id === group.id,
                      );
                      const unallocatedVal = Number(group.unallocated ?? 0);

                      return (
                        <React.Fragment key={group.id}>
                          <tr
                            className={`border-b border-border hover:bg-[#f8f9fa] ${isExpanded ? "bg-blue-50/40 border-l-4 border-l-[#1e3a8a]" : "border-l-4 border-l-transparent"}`}
                          >
                            <td className="p-4 text-center">
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-8 w-8 p-0"
                                onClick={() => toggleGroupExpand(group.id)}
                              >
                                {isExpanded ? (
                                  <ChevronDown className="h-4 w-4 text-gray-600" />
                                ) : (
                                  <ChevronRight className="h-4 w-4 text-gray-400" />
                                )}
                              </Button>
                            </td>
                            <td className="p-4 text-sm font-bold text-gray-900">
                              {group.name}
                            </td>
                            <td className="p-4 text-sm text-gray-500 font-mono bg-gray-50 px-2 py-1 rounded inline-block mt-3">
                              {group.wbs_code || "-"}
                            </td>
                            <td className="p-4 text-sm text-muted-foreground">
                              {teamlead ? (
                                <div className="flex items-center gap-2">
                                  <div className="text-left">
                                    <p className="font-medium text-gray-900">
                                      {teamlead.full_name}
                                    </p>
                                  </div>
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    type="button"
                                    className="h-6 w-6 p-0 shrink-0"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleUnassignTeamLead(teamlead);
                                    }}
                                  >
                                    <Unlink className="h-3 w-3 text-gray-400 hover:text-red-600" />
                                  </Button>
                                </div>
                              ) : (
                                <Button
                                  size="sm"
                                  variant="outline"
                                  onClick={() => openAssignTeamLeadModal(group)}
                                  className="h-8 px-2.5 border-[#1e3a8a]/30 text-[#1e3a8a] hover:bg-[#eff6ff] hover:text-[#1e40af]"
                                >
                                  <UserPlus className="mr-1.5 h-3.5 w-3.5" />{" "}
                                  Assign
                                </Button>
                              )}
                            </td>
                            <td className="p-4 text-sm text-right font-bold text-[#1e3a8a]">
                              {formatCurrency(group.budget ?? 0)}
                            </td>
                            <td className="p-4 text-sm text-right text-gray-500">
                              {formatCurrency(group.allocated_to_labs ?? 0)}
                            </td>
                            <td
                              className={`p-4 text-sm text-right font-bold ${
                                unallocatedVal < 0
                                  ? "text-[#dc2626]"
                                  : "text-[#16a34a]"
                              }`}
                            >
                              {formatCurrency(unallocatedVal)}
                            </td>
                            <td className="p-4 text-center">
                              <div className="flex items-center justify-center gap-2">
                                <Button
                                  size="sm"
                                  variant="outline"
                                  onClick={() => openEditGroup(group)}
                                >
                                  <Edit className="h-3 w-3" />
                                </Button>
                                <Button
                                  size="sm"
                                  variant="outline"
                                  onClick={() =>
                                    handleDelete(
                                      `/api/config/labgroups/${group.id}`,
                                      group.name,
                                    )
                                  }
                                  className="text-[#dc2626]"
                                >
                                  <Trash2 className="h-3 w-3" />
                                </Button>
                              </div>
                            </td>
                          </tr>

                          {isExpanded && (
                            <tr className="bg-white border-b border-border shadow-inner">
                              <td colSpan={8} className="p-0">
                                <div className="p-5 pl-16 pr-8 border-l-4 border-l-[#1e3a8a]">
                                  <div className="flex items-center justify-between mb-4">
                                    <div className="flex items-center">
                                      <Beaker className="h-4 w-4 text-gray-400 mr-2" />
                                      <h4 className="text-sm font-bold text-gray-700">
                                        Labs under {group.name}
                                      </h4>
                                    </div>
                                    <Button
                                      size="sm"
                                      onClick={() => openAddLabToGroup(group)}
                                      className="bg-white border border-[#1e3a8a] text-[#1e3a8a] hover:bg-blue-50 h-8"
                                    >
                                      <Plus className="h-3.5 w-3.5 mr-1" /> Add
                                      Lab
                                    </Button>
                                  </div>

                                  {groupLabs.length === 0 ? (
                                    <p className="text-sm text-gray-400 italic bg-gray-50 p-6 text-center rounded-lg border border-dashed border-gray-200">
                                      No labs exist in this group yet. Click
                                      "Add Lab" to allocate funds from the{" "}
                                      {formatCurrency(group.unallocated ?? 0)}{" "}
                                      remaining budget.
                                    </p>
                                  ) : (
                                    <table className="w-full bg-white rounded-lg border border-gray-200 overflow-hidden shadow-sm">
                                      <thead className="bg-gray-50 border-b border-gray-200">
                                        <tr className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                                          <th className="text-left p-3 pl-4">
                                            Lab Location
                                          </th>
                                          <th className="text-left p-3">
                                            Lab Name
                                          </th>
                                          <th className="text-left p-3">
                                            Lab IC
                                          </th>
                                          <th className="text-right p-3">
                                            Allocated Budget
                                          </th>
                                          <th className="text-center p-3">
                                            Actions
                                          </th>
                                        </tr>
                                      </thead>
                                      <tbody>
                                        {groupLabs.map((lab) => {
                                          const assignedUsers =
                                            labicUsers.filter((u) =>
                                              u.lab_assignments?.some(
                                                (a: any) => a.lab_id === lab.id,
                                              ),
                                            );

                                          return (
                                            <tr
                                              key={lab.id}
                                              className="border-b border-gray-100 last:border-0 hover:bg-blue-50/30 transition-colors"
                                            >
                                              <td className="p-3 pl-4 text-sm font-bold text-gray-800">
                                                {lab.code}
                                              </td>
                                              <td className="p-3 text-sm font-medium text-gray-600">
                                                {lab.name}
                                              </td>
                                              <td className="p-3 text-sm">
                                                {assignedUsers.length > 0 ? (
                                                  <div className="flex flex-col gap-1.5">
                                                    {assignedUsers.map((u) => {
                                                      const assignment =
                                                        u.lab_assignments?.find(
                                                          (a: any) =>
                                                            a.lab_id === lab.id,
                                                        );
                                                      const isPrimary =
                                                        assignment?.is_primary;

                                                      return (
                                                        <div
                                                          key={u.user_id}
                                                          className="flex items-center justify-between gap-2 p-1.5 rounded border border-gray-100 bg-gray-50/60"
                                                        >
                                                          <div className="text-left">
                                                            <div className="flex items-center gap-1.5">
                                                              <span className="font-medium text-gray-800 text-xs">
                                                                {u.full_name}
                                                              </span>
                                                              {isPrimary ? (
                                                                <span className="px-1.5 py-0.2 text-[10px] font-semibold bg-blue-100 text-blue-800 rounded">
                                                                  Primary
                                                                </span>
                                                              ) : (
                                                                <span className="px-1.5 py-0.2 text-[10px] font-medium bg-gray-200 text-gray-700 rounded">
                                                                  Secondary
                                                                </span>
                                                              )}
                                                            </div>
                                                            <p className="text-[11px] text-gray-400">
                                                              {u.email}
                                                            </p>
                                                          </div>

                                                          <div className="flex items-center gap-1 shrink-0">
                                                            <Button
                                                              size="sm"
                                                              variant="ghost"
                                                              type="button"
                                                              className="h-6 w-6 p-0"
                                                              title={
                                                                isPrimary
                                                                  ? "Set as Secondary"
                                                                  : "Set as Primary"
                                                              }
                                                              onClick={(e) => {
                                                                e.stopPropagation();
                                                                const resolvedUser =
                                                                  u?.user ?? u;
                                                                const userId =
                                                                  resolvedUser?.id ??
                                                                  resolvedUser?.user_id ??
                                                                  u?.user_id;

                                                                if (!userId) {
                                                                  alert(
                                                                    "Error: Missing User ID.",
                                                                  );
                                                                  return;
                                                                }

                                                                handleTogglePrimary(
                                                                  userId,
                                                                  lab.id,
                                                                  !isPrimary,
                                                                );
                                                              }}
                                                            >
                                                              <Star
                                                                className={`h-3.5 w-3.5 ${
                                                                  isPrimary
                                                                    ? "fill-yellow-400 text-yellow-500 hover:text-gray-400"
                                                                    : "text-gray-400 hover:text-yellow-500"
                                                                }`}
                                                              />
                                                            </Button>

                                                            <Button
                                                              size="sm"
                                                              variant="ghost"
                                                              type="button"
                                                              className="h-6 w-6 p-0"
                                                              title="Unassign user"
                                                              onClick={(e) => {
                                                                e.stopPropagation();
                                                                const resolvedUser =
                                                                  u?.user ?? u;
                                                                const userId =
                                                                  resolvedUser?.id ??
                                                                  resolvedUser?.user_id ??
                                                                  u?.user_id;

                                                                if (!userId) {
                                                                  alert(
                                                                    "Error: Missing User ID.",
                                                                  );
                                                                  return;
                                                                }

                                                                handleUnassignLabIC(
                                                                  resolvedUser,
                                                                  lab.id,
                                                                );
                                                              }}
                                                            >
                                                              <Unlink className="h-3 w-3 text-gray-400 hover:text-red-600" />
                                                            </Button>
                                                          </div>
                                                        </div>
                                                      );
                                                    })}
                                                    <Button
                                                      size="sm"
                                                      variant="ghost"
                                                      onClick={() =>
                                                        openAssignLabICModal(
                                                          lab,
                                                        )
                                                      }
                                                      className="h-6 text-xs text-[#1e3a8a] self-start hover:bg-blue-50"
                                                    >
                                                      + Add IC
                                                    </Button>
                                                  </div>
                                                ) : (
                                                  <Button
                                                    size="sm"
                                                    variant="outline"
                                                    onClick={() =>
                                                      openAssignLabICModal(lab)
                                                    }
                                                    className="h-8 px-2.5 border-[#1e3a8a]/30 text-[#1e3a8a] hover:bg-[#eff6ff] hover:text-[#1e40af]"
                                                  >
                                                    <UserPlus className="mr-1.5 h-3.5 w-3.5" />{" "}
                                                    Assign Lab IC
                                                  </Button>
                                                )}
                                              </td>
                                              <td className="p-3 text-sm text-right font-semibold text-gray-800">
                                                {formatCurrency(
                                                  lab.budget ?? 0,
                                                )}
                                              </td>
                                              <td className="p-3 text-center">
                                                <div className="flex items-center justify-center gap-2">
                                                  <Button
                                                    size="sm"
                                                    variant="outline"
                                                    onClick={() =>
                                                      openEditLab(lab)
                                                    }
                                                  >
                                                    <Edit className="h-3 w-3" />
                                                  </Button>
                                                  <Button
                                                    size="sm"
                                                    variant="outline"
                                                    onClick={() =>
                                                      handleDelete(
                                                        `/api/config/labs/${lab.id}`,
                                                        lab.name,
                                                      )
                                                    }
                                                    className="text-[#dc2626]"
                                                  >
                                                    <Trash2 className="h-3 w-3" />
                                                  </Button>
                                                </div>
                                              </td>
                                            </tr>
                                          );
                                        })}
                                      </tbody>
                                      <tfoot className="bg-gray-50 border-t border-gray-200">
                                        <tr>
                                          <td
                                            colSpan={3}
                                            className="p-3 text-right text-xs font-bold text-gray-500 uppercase"
                                          >
                                            Total Allocated to Labs:
                                          </td>
                                          <td className="p-3 text-right text-sm font-bold text-gray-800">
                                            {formatCurrency(
                                              group.allocated_to_labs ?? 0,
                                            )}
                                          </td>
                                          <td></td>
                                        </tr>
                                      </tfoot>
                                    </table>
                                  )}
                                </div>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Card>
          </TabsContent>

          <TabsContent value="categories">
            <Card className="bg-white border-border">
              <div className="p-6 border-b border-border flex items-center justify-between">
                <h3 className="text-lg font-semibold text-foreground">
                  Spending Categories
                </h3>
                <Button
                  onClick={() => {
                    resetCategoryModal();
                    setIsCategoryModalOpen(true);
                  }}
                  className="bg-[#1e3a8a] hover:bg-[#1e40af] text-white"
                >
                  <Plus className="h-4 w-4 mr-2" /> Add Category
                </Button>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-[#f8f9fa]">
                    <tr className="border-b border-border text-sm font-medium text-muted-foreground">
                      <th className="text-left p-4">Category Name</th>
                      <th className="text-left p-4">Description</th>
                      <th className="text-center p-4">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {categories.map((cat) => (
                      <tr
                        key={cat.id}
                        className="border-b border-border hover:bg-[#f8f9fa]"
                      >
                        <td className="p-4 text-sm font-medium text-foreground">
                          {cat.name}
                        </td>
                        <td className="p-4 text-sm text-muted-foreground">
                          {cat.description}
                        </td>
                        <td className="p-4 text-center">
                          <div className="flex items-center justify-center gap-2">
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => openEditCategory(cat)}
                            >
                              <Edit className="h-3 w-3" />
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() =>
                                handleDelete(
                                  `/api/config/categories/${cat.id}`,
                                  cat.name,
                                )
                              }
                              className="text-[#dc2626]"
                            >
                              <Trash2 className="h-3 w-3" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </TabsContent>

          <TabsContent value="users">
            <UserManagement onUsersChanged={fetchConfigData} />
          </TabsContent>
        </Tabs>
      </div>

      {isGroupModalOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <Card className="w-full max-w-xl bg-white shadow-xl overflow-hidden">
            <div className="flex justify-between items-start gap-4 p-6 border-b border-border bg-[#f8f9fa]">
              <div>
                <h3 className="text-lg font-bold">
                  {editingGroupId ? "Edit Lab Group" : "Add Lab Group"}
                </h3>
                <p className="text-xs text-muted-foreground mt-1">
                  Set the total budget for this lab group.
                </p>
              </div>
              <Button variant="ghost" size="sm" onClick={resetGroupModal}>
                <X className="h-4 w-4" />
              </Button>
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (isGroupBudgetBelowFloor) return;
                const endpoint = editingGroupId
                  ? `/api/config/labgroups/${editingGroupId}?period_id=${selectedPeriodId}`
                  : `/api/config/labgroups?period_id=${selectedPeriodId}`;
                const method = editingGroupId ? "PUT" : "POST";
                handleSave(
                  endpoint,
                  method,
                  { ...newGroupForm, assigned_lab_ids: selectedLabIds },
                  resetGroupModal,
                );
              }}
              className="space-y-4 p-6"
            >
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium">Group Name</label>
                  <input
                    type="text"
                    required
                    className="w-full mt-1 p-2 border rounded-md"
                    placeholder="e.g. ICT"
                    value={newGroupForm.name}
                    onChange={(e) =>
                      setNewGroupForm({ ...newGroupForm, name: e.target.value })
                    }
                  />
                </div>
                <div>
                  <label className="text-sm font-medium">WBS</label>
                  <input
                    type="text"
                    required
                    className="w-full mt-1 p-2 border rounded-md"
                    placeholder="e.g. WBS-ICT"
                    value={newGroupForm.wbs_code}
                    onChange={(e) =>
                      setNewGroupForm({
                        ...newGroupForm,
                        wbs_code: e.target.value,
                      })
                    }
                  />
                </div>
              </div>

              <div
                className={`mt-4 p-4 border rounded-md ${
                  isGroupBudgetBelowFloor
                    ? "bg-red-50/70 border-red-200"
                    : "bg-blue-50/50 border-blue-100"
                }`}
              >
                <label className="text-sm font-bold text-[#1e3a8a] flex items-center mb-2">
                  <DollarSign className="h-4 w-4 mr-1" /> Total Lab Group Budget
                </label>
                <p className="text-xs text-blue-800/70 mb-3">
                  This is the absolute maximum that can be distributed to labs
                  within this group.
                </p>
                {editingGroupFloor && minAllowedGroupBudget > 0 && (
                  <p className="text-xs font-medium text-gray-600 mb-2">
                    Currently Allocated to Labs:{" "}
                    <span className="font-bold text-gray-900">
                      {formatCurrency(editingGroupFloor.allocated)}
                    </span>{" "}
                    | Utilised/Spent:{" "}
                    <span className="font-bold text-gray-900">
                      {formatCurrency(editingGroupFloor.spent)}
                    </span>
                  </p>
                )}
                <div className="relative">
                  <span className="absolute left-3 top-2.5 text-gray-500 font-bold">
                    $
                  </span>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    required
                    className={`w-full pl-7 p-2 border rounded-md font-bold text-lg text-gray-800 ${
                      isGroupBudgetBelowFloor
                        ? "border-red-400 bg-white focus:ring-red-200"
                        : "border-blue-200"
                    }`}
                    placeholder="0.00"
                    value={newGroupForm.budget}
                    onChange={(e) =>
                      setNewGroupForm({
                        ...newGroupForm,
                        budget: e.target.value
                          ? parseFloat(e.target.value)
                          : "",
                      })
                    }
                  />
                </div>
                {isGroupBudgetBelowFloor && (
                  <div className="mt-3 p-2.5 bg-red-100 text-red-700 text-xs font-semibold rounded flex items-center">
                    <AlertTriangle className="h-4 w-4 mr-2 shrink-0" />
                    Cannot set Lab Group budget below{" "}
                    {formatCurrency(minAllowedGroupBudget)} because that amount
                    is already allocated to labs or spent. Reduce lab
                    allocations first.
                  </div>
                )}
              </div>

              {orphanedLabs.length > 0 && (
                <div className="mt-4 p-4 border rounded-md bg-gray-50 border-gray-200">
                  <h4 className="text-sm font-semibold text-gray-900 mb-1">
                    Unassigned Labs Detected ({orphanedLabs.length})
                  </h4>
                  <p className="text-xs text-gray-500 mb-3">
                    Select labs to assign to this group (Requires budget
                    allocation later).
                  </p>
                  <div className="max-h-36 overflow-y-auto space-y-2 pr-2">
                    {orphanedLabs.map((lab) => (
                      <div
                        key={lab.lab_id}
                        className="flex items-center space-x-2"
                      >
                        <input
                          type="checkbox"
                          id={`lab-${lab.lab_id}`}
                          checked={selectedLabIds.includes(lab.lab_id)}
                          onChange={() => toggleOrphanedLab(lab.lab_id)}
                          className="rounded border-gray-300 text-[#1e3a8a] focus:ring-[#1e3a8a] h-4 w-4"
                        />
                        <label
                          htmlFor={`lab-${lab.lab_id}`}
                          className="text-sm cursor-pointer text-gray-700 font-medium"
                        >
                          {lab.lab_name}{" "}
                          <span className="text-xs text-gray-400 font-normal">
                            ({lab.lab_code})
                          </span>
                        </label>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="flex justify-end gap-2 pt-4 border-t border-gray-100">
                <Button
                  type="button"
                  variant="outline"
                  onClick={resetGroupModal}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={isGroupBudgetBelowFloor}
                  className="bg-[#1e3a8a] text-white disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {editingGroupId ? "Save Changes" : "Create Lab Group"}
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}

      {isLabModalOpen && activeGroupValidation && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <Card className="w-full max-w-2xl bg-white shadow-xl max-h-[90vh] overflow-y-auto">
            <div className="flex justify-between items-center p-6 border-b border-border bg-[#f8f9fa]">
              <div>
                <h3 className="text-xl font-bold">
                  {editingLabId ? "Edit Lab Allocation" : "Allocate New Lab"}
                </h3>
                <p className="text-sm text-[#1e3a8a] font-medium mt-1">
                  Belongs to: {activeGroupValidation.name}
                </p>
              </div>
              <Button variant="ghost" size="sm" onClick={resetLabModal}>
                <X className="h-5 w-5" />
              </Button>
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (isBudgetExceeded || isCategorySpendViolated) return;
                const base = editingLabId
                  ? `/api/config/labs/${editingLabId}`
                  : "/api/config/labs";
                const endpoint = `${base}?period_id=${selectedPeriodId}`;
                const method = editingLabId ? "PUT" : "POST";
                handleSave(
                  endpoint,
                  method,
                  {
                    ...newLabForm,
                    lab_group_id: Number(newLabForm.lab_group_id),
                  },
                  resetLabModal,
                );
              }}
              className="p-6"
            >
              <div className="grid grid-cols-2 gap-5">
                <div>
                  <label className="text-sm font-medium text-gray-700">
                    Lab Location
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. E2-02-14"
                    className="w-full mt-1.5 p-2 border rounded-md uppercase focus:ring-2 focus:ring-[#1e3a8a] outline-none"
                    value={newLabForm.lab_code || ""}
                    onChange={(e) => {
                      const code = String(e.target.value).toUpperCase();
                      const autoVenue = generateVenueTags(
                        code,
                        newLabForm.lab_name,
                      );
                      setNewLabForm({
                        ...newLabForm,
                        lab_code: code,
                        venue: autoVenue,
                      });
                    }}
                  />
                </div>
                <div>
                  <label className="text-sm font-medium text-gray-700">
                    Lab Name
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Embedded Systems Lab"
                    className="w-full mt-1.5 p-2 border rounded-md focus:ring-2 focus:ring-[#1e3a8a] outline-none"
                    value={newLabForm.lab_name || ""}
                    onChange={(e) => {
                      const name = String(e.target.value);
                      const autoVenue = generateVenueTags(
                        newLabForm.lab_code,
                        name,
                      );
                      setNewLabForm({
                        ...newLabForm,
                        lab_name: name,
                        venue: autoVenue,
                      });
                    }}
                  />
                </div>

                <div className="col-span-2">
                  <label className="text-sm font-medium text-gray-700 flex justify-between">
                    <span>Venue / Location Tags</span>
                    <span className="text-xs text-gray-400 font-normal">
                      Separate tags with commas
                    </span>
                  </label>
                  <textarea
                    rows={2}
                    className="w-full mt-1.5 p-2 border rounded-md focus:ring-2 focus:ring-[#1e3a8a] outline-none resize-y text-sm"
                    placeholder="e.g. Block W2, Level 05, Room 12, SR4A..."
                    value={newLabForm.venue || ""}
                    onChange={(e) =>
                      setNewLabForm({
                        ...newLabForm,
                        venue: String(e.target.value),
                      })
                    }
                  />
                </div>

                <div className="col-span-2 mt-2 pt-5 border-t border-gray-200">
                  <div className="flex justify-between items-end mb-4">
                    <h4 className="font-bold text-gray-900 text-lg">
                      Distribute Budgets
                    </h4>

                    <div
                      className={`text-right p-3 rounded-lg border ${
                        isBudgetExceeded
                          ? "bg-red-50 border-red-200"
                          : "bg-green-50 border-green-200"
                      }`}
                    >
                      <p className="text-xs text-gray-500 uppercase font-bold tracking-wider mb-1">
                        Unallocated Group Budget
                      </p>
                      <p
                        className={`text-lg font-black ${
                          isBudgetExceeded ? "text-red-600" : "text-green-700"
                        }`}
                      >
                        {formatCurrency(
                          activeGroupValidation.unallocated -
                            currentRequestedTotal,
                        )}
                      </p>
                    </div>
                  </div>

                  {isBudgetExceeded && (
                    <div className="mb-4 p-3 bg-red-100 text-red-700 text-sm font-semibold rounded-md flex items-center">
                      <AlertTriangle className="h-4 w-4 mr-2 flex-shrink-0" />
                      Requested allocation exceeds the Lab Group's available
                      budget! Reduce category budgets.
                    </div>
                  )}

                  {isCategorySpendViolated && (
                    <div className="mb-4 p-3 bg-red-100 text-red-700 text-sm font-semibold rounded-md flex items-center">
                      <AlertTriangle className="h-4 w-4 mr-2 flex-shrink-0" />
                      Cannot shift/reduce budget for{" "}
                      {violatedCategories.map((c) => c.name).join(", ")} below
                      the amount already utilised/spent in this fiscal year.
                    </div>
                  )}

                  {categories.length === 0 ? (
                    <p className="text-sm text-red-500 italic">
                      Please add Spending Categories first!
                    </p>
                  ) : (
                    <div className="grid grid-cols-2 gap-4 bg-gray-50 p-4 rounded-lg border border-gray-100">
                      {categories.map((cat) => {
                        const key = String(cat.id);
                        const catSpent = Number(
                          activeGroupValidation.spentByCategory?.[key] || 0,
                        );
                        const origBudget = Number(
                          activeGroupValidation.originalBudgets?.[key] || 0,
                        );
                        const minAllowed =
                          origBudget >= catSpent ? catSpent : origBudget;
                        const requested = Number(
                          newLabForm.budgets[cat.id] || 0,
                        );
                        const isThisCatViolated =
                          catSpent > 0 && requested + 1e-6 < minAllowed;

                        return (
                          <div key={cat.id}>
                            <div className="flex items-center justify-between">
                              <label className="text-xs font-bold text-gray-600 uppercase">
                                {cat.name}
                              </label>
                              {catSpent > 0 && (
                                <span
                                  className={`text-[11px] font-semibold ${
                                    isThisCatViolated
                                      ? "text-red-600"
                                      : "text-gray-500"
                                  }`}
                                >
                                  Utilised: {formatCurrency(catSpent)}
                                </span>
                              )}
                            </div>
                            <div className="relative mt-1.5">
                              <span className="absolute left-3 top-2.5 text-gray-500 font-medium">
                                $
                              </span>
                              <input
                                type="number"
                                min="0"
                                step="0.01"
                                className={`w-full pl-7 p-2 border rounded-md focus:ring-2 outline-none transition-colors ${
                                  isBudgetExceeded || isThisCatViolated
                                    ? "border-red-400 focus:ring-red-200 bg-red-50"
                                    : "border-gray-300 focus:ring-[#1e3a8a]/20 focus:border-[#1e3a8a]"
                                }`}
                                placeholder="0.00"
                                value={newLabForm.budgets[cat.id] ?? ""}
                                onChange={(e) =>
                                  setNewLabForm({
                                    ...newLabForm,
                                    budgets: {
                                      ...newLabForm.budgets,
                                      [cat.id]:
                                        e.target.value === ""
                                          ? 0
                                          : parseFloat(e.target.value) || 0,
                                    },
                                  })
                                }
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-6 mt-6 border-t border-gray-100">
                <Button type="button" variant="outline" onClick={resetLabModal}>
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={isBudgetExceeded || isCategorySpendViolated}
                  className="bg-[#1e3a8a] text-white disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {editingLabId ? "Save Allocation" : "Confirm Allocation"}
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}

      {isCategoryModalOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <Card className="w-full max-w-xl bg-white shadow-xl overflow-hidden">
            <div className="flex justify-between items-start gap-4 p-6 border-b border-border bg-[#f8f9fa]">
              <h3 className="text-lg font-bold">
                {editingCategoryId ? "Edit Category" : "Add Spending Category"}
              </h3>
              <Button variant="ghost" size="sm" onClick={resetCategoryModal}>
                <X className="h-4 w-4" />
              </Button>
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const endpoint = editingCategoryId
                  ? `/api/config/categories/${editingCategoryId}`
                  : "/api/config/categories";
                const method = editingCategoryId ? "PUT" : "POST";
                handleSave(
                  endpoint,
                  method,
                  newCategoryForm,
                  resetCategoryModal,
                );
              }}
              className="space-y-4 p-6"
            >
              <div>
                <label className="text-sm font-medium">Category Name</label>
                <input
                  type="text"
                  required
                  className="w-full mt-1 p-2 border rounded-md"
                  placeholder="e.g. Consumables"
                  value={newCategoryForm.name}
                  onChange={(e) =>
                    setNewCategoryForm({
                      ...newCategoryForm,
                      name: e.target.value,
                    })
                  }
                />
              </div>
              <div>
                <label className="text-sm font-medium">Description</label>
                <textarea
                  className="w-full mt-1 p-2 border rounded-md"
                  rows={3}
                  value={newCategoryForm.description}
                  onChange={(e) =>
                    setNewCategoryForm({
                      ...newCategoryForm,
                      description: e.target.value,
                    })
                  }
                />
              </div>
              <div className="flex justify-end gap-2 pt-4">
                <Button
                  type="button"
                  variant="outline"
                  onClick={resetCategoryModal}
                >
                  Cancel
                </Button>
                <Button type="submit" className="bg-[#1e3a8a] text-white">
                  {editingCategoryId ? "Save Changes" : "Create"}
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}

      {isPeriodModalOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <Card className="w-full max-w-sm bg-white shadow-xl">
            <div className="flex justify-between items-center p-6 border-b border-border bg-[#f8f9fa]">
              <h3 className="text-xl font-bold">Add Fiscal Year</h3>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setIsPeriodModalOpen(false);
                  setNewPeriodYear("");
                }}
              >
                <X className="h-5 w-5" />
              </Button>
            </div>
            <div className="p-6 space-y-3">
              <label className="text-sm font-medium text-gray-700">Year</label>
              <input
                type="number"
                autoFocus
                className="w-full mt-1 p-2 border rounded-md"
                placeholder="e.g. 2025"
                value={newPeriodYear}
                onChange={(e) => setNewPeriodYear(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                Creates FY{newPeriodYear || "…"} (Apr 1 → Mar 31 the next year).
              </p>
              <div className="flex justify-end gap-2 pt-2">
                <Button
                  variant="outline"
                  onClick={() => {
                    setIsPeriodModalOpen(false);
                    setNewPeriodYear("");
                  }}
                >
                  Cancel
                </Button>
                <Button
                  className="bg-[#1e3a8a] text-white"
                  onClick={handleAddPeriod}
                >
                  Create
                </Button>
              </div>
            </div>
          </Card>
        </div>
      )}

      {isAssignLabICModalOpen && assignTargetLab && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <Card className="w-full max-w-md bg-white shadow-xl overflow-hidden">
            <div className="flex justify-between items-center p-6 border-b border-border bg-[#f8f9fa]">
              <div>
                <h3 className="text-lg font-semibold text-foreground">
                  Assign Lab IC
                </h3>
                <p className="text-sm text-muted-foreground mt-0.5">
                  {assignTargetLab.code} — {assignTargetLab.name}
                </p>
              </div>
              <Button variant="ghost" size="sm" onClick={resetAssignLabICModal}>
                <X className="h-4 w-4" />
              </Button>
            </div>

            <div className="p-6 space-y-5">
              <div className="rounded-md border border-border bg-white p-4">
                <div className="mb-3 flex items-center gap-2">
                  <UserRound className="h-4 w-4 text-[#1e3a8a]" />
                  <label className="text-sm font-medium text-foreground">
                    Available Lab IC users
                  </label>
                </div>
                <select
                  className="w-full rounded-md border border-input bg-input-background px-3 py-2 text-sm outline-none transition-colors focus:border-[#1e3a8a] focus:ring-2 focus:ring-[#1e3a8a]/20"
                  value={selectedLabICUserId ?? ""}
                  onChange={(e) => {
                    const val = e.target.value;
                    if (!val) {
                      setSelectedLabICUserId("");
                      return;
                    }
                    const parsedId = Number(val);
                    setSelectedLabICUserId(isNaN(parsedId) ? "" : parsedId);
                  }}
                >
                  <option value="" disabled>
                    Select a user...
                  </option>
                  {(() => {
                    const availableUsers = labicUsers.filter(
                      (u) =>
                        !u.lab_assignments?.some(
                          (a: any) => a.lab_id === assignTargetLab.id,
                        ),
                    );

                    return availableUsers.map((u: any) => {
                      const userId = u.id ?? u.user_id;

                      const assignmentCount = u.lab_assignments?.length || 0;
                      const assignmentLabel =
                        assignmentCount > 0
                          ? ` (${assignmentCount} active lab ${assignmentCount === 1 ? "assignment" : "assignments"})`
                          : "";

                      return (
                        <option key={userId} value={userId}>
                          {u.full_name} — {u.email}
                          {assignmentLabel}
                        </option>
                      );
                    });
                  })()}
                </select>
                <p className="text-xs text-muted-foreground mt-1">
                  Users already assigned to this lab are hidden. Users assigned
                  to other labs can still be added here.
                </p>
                {selectedLabICUserId !== "" && (
                  <div className="mt-3 rounded-md border border-[#1e3a8a]/20 bg-[#eff6ff] p-3 text-sm">
                    <div className="flex items-start gap-2">
                      <CheckCircle2 className="mt-0.5 h-4 w-4 text-[#1e3a8a]" />
                      <div className="min-w-0">
                        {(() => {
                          const selectedUser = labicUsers.find(
                            (u: any) =>
                              (u.id ?? u.user_id) === selectedLabICUserId,
                          );
                          return (
                            <>
                              <p className="font-medium text-foreground">
                                {selectedUser?.full_name}
                              </p>
                              <p className="mt-0.5 flex items-center gap-1 text-xs text-muted-foreground">
                                <Mail className="h-3.5 w-3.5" />
                                {selectedUser?.email}
                              </p>
                            </>
                          );
                        })()}
                      </div>
                    </div>
                  </div>
                )}
              </div>

              <div className="flex justify-end gap-2 pt-5 border-t">
                <Button variant="outline" onClick={resetAssignLabICModal}>
                  Cancel
                </Button>
                <Button
                  onClick={handleAssignLabIC}
                  disabled={selectedLabICUserId === ""}
                  className="bg-[#1e3a8a] text-white disabled:opacity-50"
                >
                  Confirm Assignment
                </Button>
              </div>
            </div>
          </Card>
        </div>
      )}

      {isAssignTeamLeadModalOpen && assignTargetGroup && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <Card className="w-full max-w-md bg-white shadow-xl overflow-hidden">
            <div className="flex justify-between items-center p-6 border-b border-border bg-[#f8f9fa]">
              <div>
                <h3 className="text-lg font-semibold text-foreground">
                  Assign Team Lead
                </h3>
                <p className="text-sm text-muted-foreground mt-0.5">
                  {assignTargetGroup.name}
                </p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={resetAssignTeamLeadModal}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>

            <div className="p-6 space-y-5">
              <div className="rounded-md border border-border bg-white p-4">
                <div className="mb-3 flex items-center gap-2">
                  <UserRound className="h-4 w-4 text-[#1e3a8a]" />
                  <label className="text-sm font-medium text-foreground">
                    Available Team Leads
                  </label>
                </div>
                <select
                  className="w-full rounded-md border border-input bg-input-background px-3 py-2 text-sm"
                  value={selectedTeamLeadUserId ?? ""}
                  onChange={(e) => {
                    const val = e.target.value;
                    if (!val) {
                      setSelectedTeamLeadUserId("");
                      return;
                    }
                    const parsedId = Number(val);
                    setSelectedTeamLeadUserId(isNaN(parsedId) ? "" : parsedId);
                  }}
                >
                  <option value="" disabled>
                    Select a Team Lead...
                  </option>
                  {teamleadUsers.map((u: any) => {
                    const userId = u.id ?? u.user_id;
                    return (
                      <option key={userId} value={userId}>
                        {u.full_name || u.email}
                      </option>
                    );
                  })}
                </select>
                <p className="text-xs text-muted-foreground mt-1">
                  Only unassigned Team Leads are shown. To reassign from another
                  group, unassign them first via User Management.
                </p>
                {selectedTeamLeadUserId !== "" && (
                  <div className="mt-3 rounded-md border border-[#1e3a8a]/20 bg-[#eff6ff] p-3 text-sm">
                    <div className="flex items-start gap-2">
                      <CheckCircle2 className="mt-0.5 h-4 w-4 text-[#1e3a8a]" />
                      <div className="min-w-0">
                        <p className="font-medium text-foreground">
                          {
                            teamleadUsers.find(
                              (u) => u.user_id === selectedTeamLeadUserId,
                            )?.full_name
                          }
                        </p>
                        <p className="mt-0.5 flex items-center gap-1 text-xs text-muted-foreground">
                          <Mail className="h-3.5 w-3.5" />
                          {
                            teamleadUsers.find(
                              (u) => u.user_id === selectedTeamLeadUserId,
                            )?.email
                          }
                        </p>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              <div className="flex justify-end gap-2 pt-5 border-t">
                <Button variant="outline" onClick={resetAssignTeamLeadModal}>
                  Cancel
                </Button>
                <Button
                  type="button"
                  onClick={handleAssignTeamLead}
                  disabled={
                    !selectedTeamLeadUserId ||
                    isNaN(Number(selectedTeamLeadUserId))
                  }
                  className="bg-[#1e3a8a] text-white disabled:opacity-50"
                >
                  Confirm Assignment
                </Button>
              </div>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}