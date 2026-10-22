import { useState, useEffect } from "react";
import { useNavigate } from "react-router";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { Label } from "../components/ui/label";
import { AlertCircle, UserPlus, CheckCircle2 } from "lucide-react";

interface Role {
  role_id: number;
  role_name: string;
}

interface LabGroup {
  id: number;
  name: string;
  wbs_code: string;
}

interface Lab {
  id: number;
  code: string;
  name: string;
  group: string;
}

interface FieldErrors {
  [key: string]: string;
}

const API = import.meta.env.VITE_API_URL ?? "/api";
const ROLES: Role[] = [
  { role_id: 1, role_name: "admin" },
  { role_id: 2, role_name: "teamlead" },
  { role_id: 3, role_name: "labic" },
];

async function fetchUsersByRole(role: string): Promise<any[]> {
  try {
    const r = await fetch(`${API}/auth/users?role=${role}`, { credentials: "include" });
    return r.ok ? await r.json() : [];
  } catch {
    return [];
  }
}

const fetchLabicUsers = () => fetchUsersByRole("labic");
const fetchTeamLeadUsers = () => fetchUsersByRole("teamlead");

export function CreateUserPage() {
  const navigate = useNavigate();
  const [roles, setRoles] = useState<Role[]>(ROLES);
  const [labGroups, setLabGroups] = useState<LabGroup[]>([]);
  const [labs, setLabs] = useState<Lab[]>([]);
  const [labicUsers, setLabicUsers] = useState<any[]>([]);
  const [teamLeadUsers, setTeamLeadUsers] = useState<any[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});

  const [form, setForm] = useState({
    full_name: "",
    email: "",
    password: "",
    confirm_password: "",
    role_id: "",
    lab_group_id: "",
    lab_id: "",
  });

  useEffect(() => {
    fetch(`${API}/auth/roles`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : ROLES))
      .then(setRoles)
      .catch(() => setRoles(ROLES));

    fetch(`${API}/config/labgroups`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then(setLabGroups)
      .catch(() => setLabGroups([]));

    fetch(`${API}/config/labs`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then(setLabs)
      .catch(() => setLabs([]));

    fetchLabicUsers().then(setLabicUsers);
    fetchTeamLeadUsers().then(setTeamLeadUsers);
  }, []);

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>
  ) => {
    const { name, value } = e.target;
    setForm((prev) => ({
      ...prev,
      [name]: value,
      ...(name === "role_id" ? { lab_group_id: "", lab_id: "" } : {}),
    }));
    if (fieldErrors[name]) {
      setFieldErrors((prev) => ({ ...prev, [name]: "" }));
    }
  };

  const validate = (): boolean => {
    const errors: FieldErrors = {};
    const selectedRole = roles.find((r) => r.role_id === Number(form.role_id));
    const selectedRoleName = selectedRole?.role_name.toLowerCase();
    const email = form.email.trim().toLowerCase();

    if (!form.full_name.trim()) errors.full_name = "Full name is required.";
    if (!email) errors.email = "Email is required.";
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email))
      errors.email = "Enter a valid email address.";
    if (!form.password) errors.password = "Password is required.";
    else if (form.password.length < 8)
      errors.password = "Password must be at least 8 characters.";
    if (form.password !== form.confirm_password)
      errors.confirm_password = "Passwords do not match.";
    if (!form.role_id) errors.role_id = "Role is required.";
    if (selectedRoleName === "teamlead" && !form.lab_group_id) {
      errors.lab_group_id = "Lab group is required for Team Lead.";
    } else if (
      selectedRoleName === "teamlead" &&
      getTeamLeadForGroup(Number(form.lab_group_id))
    ) {
      errors.lab_group_id = "This lab group already has a Team Lead.";
    }
    if (selectedRoleName === "labic" && !form.lab_id) {
      errors.lab_id = "Lab is required for Lab IC.";
    }
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async () => {
    setSuccessMessage(null);
    setServerError(null);
    if (!validate()) return;

    const selectedLabId = form.lab_id ? Number(form.lab_id) : undefined;
    const selectedRole = roles.find((r) => r.role_id === Number(form.role_id));
    const selectedRoleName = selectedRole?.role_name.toLowerCase();

    // One request: the backend creates the user and assigns the lab in a single
    // transaction and decides Primary/Secondary itself (no client-side guessing).
    const userPayload = {
      role_id: Number(form.role_id),
      full_name: form.full_name.trim(),
      email: form.email.trim(),
      password: form.password,
      ...(form.lab_group_id && { lab_group_id: Number(form.lab_group_id) }),
      ...(selectedRoleName === "labic" &&
        selectedLabId && { lab_ids: [selectedLabId] }),
    };

    setIsSubmitting(true);
    try {
      const res = await fetch(`${API}/auth/users`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(userPayload),
      });
      const data = await res.json();
      if (!res.ok) {
        setServerError(data?.detail ?? "Failed to create user. Please try again.");
        if (res.status === 409 && selectedRoleName === "teamlead") {
          // Our list was stale; re-sync so the taken group is disabled.
          setTeamLeadUsers(await fetchTeamLeadUsers());
        }
        setIsSubmitting(false);
        return;
      }

      // Refresh existing assignments so the dropdown hints stay accurate.
      if (selectedRoleName === "labic") {
        setLabicUsers(await fetchLabicUsers());
      } else if (selectedRoleName === "teamlead") {
        setTeamLeadUsers(await fetchTeamLeadUsers());
      }

      let roleLabel: string;
      if (selectedRoleName === "labic") {
        // Primary/Secondary comes from the backend's decision, not the browser's.
        const assignedLab = (data.lab_assignments ?? []).find(
          (a: any) => a.lab_id === selectedLabId
        );
        roleLabel = assignedLab
          ? `${assignedLab.is_primary ? "Primary" : "Secondary"} Lab IC`
          : "Lab IC";
      } else if (selectedRoleName === "teamlead") {
        roleLabel = "Team Lead";
      } else if (selectedRoleName === "admin") {
        roleLabel = "Admin";
      } else {
        roleLabel = selectedRole?.role_name ?? "user";
      }

      setSuccessMessage(
        `User "${data.full_name ?? form.full_name}" created successfully as ${
          selectedRoleName === "admin" ? "an" : "a"
        } ${roleLabel}.`
      );
      setForm({
        full_name: "",
        email: "",
        password: "",
        confirm_password: "",
        role_id: "",
        lab_group_id: "",
        lab_id: "",
      });
    } catch {
      setServerError("Network error. Check your connection and try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const selectedRole = roles.find((r) => r.role_id === Number(form.role_id));
  const selectedRoleName = selectedRole?.role_name.toLowerCase();
  const showLabGroup = selectedRoleName === "teamlead";
  const showLab = selectedRoleName === "labic";

  // Mirrors the backend duplicate check: only ACTIVE team leads own a lab group.
  function getTeamLeadForGroup(groupId: number) {
    return teamLeadUsers.find(
      (u) => u.is_active !== false && Number(u.lab_group_id) === groupId
    );
  }

  const getLabAssignmentStatusText = (labId: number) => {
    const hasPrimary = labicUsers.some((u) =>
      u.lab_assignments?.some(
        (a: any) => a.lab_id === labId && a.is_primary
      )
    );
    return hasPrimary
      ? " (Primary IC exists → will be assigned as Secondary)"
      : " (No Primary IC → will be assigned as Primary)";
  };

  return (
    <div className="min-h-screen bg-muted/40 flex items-start justify-center p-8">
      <Card className="w-full max-w-lg">
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary/10 text-primary">
              <UserPlus className="h-5 w-5" />
            </div>
            <div>
              <CardTitle>Create User</CardTitle>
              <CardDescription>Add a new account to the system</CardDescription>
            </div>
          </div>
        </CardHeader>

        <CardContent className="space-y-5">
          {successMessage && (
            <div className="flex items-center gap-2 rounded-md bg-green-50 border border-green-200 px-4 py-3 text-sm text-green-700">
              <CheckCircle2 className="h-4 w-4 shrink-0" />
              {successMessage}
            </div>
          )}

          {serverError && (
            <div className="flex items-center gap-2 rounded-md bg-destructive/10 border border-destructive/20 px-4 py-3 text-sm text-destructive">
              <AlertCircle className="h-4 w-4 shrink-0" />
              {serverError}
            </div>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="full_name">
              Full Name <span className="text-destructive">*</span>
            </Label>
            <Input
              id="full_name"
              name="full_name"
              value={form.full_name}
              onChange={handleChange}
              placeholder="e.g. Jane Doe"
              className={fieldErrors.full_name ? "border-destructive" : ""}
            />
            {fieldErrors.full_name && (
              <p className="text-xs text-destructive">{fieldErrors.full_name}</p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="email">
              Email Address <span className="text-destructive">*</span>
            </Label>
            <Input
              id="email"
              name="email"
              type="email"
              value={form.email}
              onChange={handleChange}
              placeholder="e.g. jane@example.com"
              className={fieldErrors.email ? "border-destructive" : ""}
            />
            {fieldErrors.email && (
              <p className="text-xs text-destructive">{fieldErrors.email}</p>
            )}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="password">
                Password <span className="text-destructive">*</span>
              </Label>
              <Input
                id="password"
                name="password"
                type="password"
                value={form.password}
                onChange={handleChange}
                placeholder="Min. 8 characters"
                className={fieldErrors.password ? "border-destructive" : ""}
              />
              {fieldErrors.password && (
                <p className="text-xs text-destructive">{fieldErrors.password}</p>
              )}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="confirm_password">
                Confirm Password <span className="text-destructive">*</span>
              </Label>
              <Input
                id="confirm_password"
                name="confirm_password"
                type="password"
                value={form.confirm_password}
                onChange={handleChange}
                placeholder="Re-enter password"
                className={fieldErrors.confirm_password ? "border-destructive" : ""}
              />
              {fieldErrors.confirm_password && (
                <p className="text-xs text-destructive">{fieldErrors.confirm_password}</p>
              )}
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="role_id">
              Role <span className="text-destructive">*</span>
            </Label>
            <select
              id="role_id"
              name="role_id"
              value={form.role_id}
              onChange={handleChange}
              className={`flex h-9 w-full rounded-md border bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring ${
                fieldErrors.role_id ? "border-destructive" : "border-input"
              }`}
            >
              <option value="">Select a role...</option>
              {roles.map((r) => (
                <option key={r.role_id} value={r.role_id}>
                  {r.role_name}
                </option>
              ))}
            </select>
            {fieldErrors.role_id && (
              <p className="text-xs text-destructive">{fieldErrors.role_id}</p>
            )}
          </div>

          {showLabGroup && (
            <div className="space-y-1.5">
              <Label htmlFor="lab_group_id">Lab Group</Label>
              <p className="text-xs text-muted-foreground">Required for Team Leads</p>
              <select
                id="lab_group_id"
                name="lab_group_id"
                value={form.lab_group_id}
                onChange={handleChange}
                className={`flex h-9 w-full rounded-md border bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring ${
                  fieldErrors.lab_group_id ? "border-destructive" : "border-input"
                }`}
              >
                <option value="">Select a lab group...</option>
                {labGroups.map((g) => {
                  const lead = getTeamLeadForGroup(g.id);
                  return (
                    <option key={g.id} value={g.id} disabled={!!lead}>
                      {g.name} - {g.wbs_code}
                      {lead ? ` (Assigned to ${lead.full_name})` : ""}
                    </option>
                  );
                })}
              </select>
              {fieldErrors.lab_group_id && (
                <p className="text-xs text-destructive">{fieldErrors.lab_group_id}</p>
              )}
            </div>
          )}

          {showLab && (
            <div className="space-y-1.5">
              <Label htmlFor="lab_id">Lab</Label>
              <p className="text-xs text-muted-foreground">Required for Lab ICs (Multiple ICs supported)</p>
              <select
                id="lab_id"
                name="lab_id"
                value={form.lab_id}
                onChange={handleChange}
                className={`flex h-9 w-full rounded-md border bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring ${
                  fieldErrors.lab_id ? "border-destructive" : "border-input"
                }`}
              >
                <option value="">Select a lab...</option>
                {labs.map((lab) => (
                  <option key={lab.id} value={lab.id}>
                    {lab.name} - {lab.code}
                    {getLabAssignmentStatusText(lab.id)}
                  </option>
                ))}
              </select>
              {fieldErrors.lab_id && (
                <p className="text-xs text-destructive">{fieldErrors.lab_id}</p>
              )}
            </div>
          )}

          <div className="flex gap-2">
            <Button
              variant="outline"
              className="w-1/3"
              onClick={() => navigate(-1)}
            >
              Back
            </Button>
            <Button
              className="w-2/3"
              onClick={handleSubmit}
              disabled={isSubmitting}
            >
              {isSubmitting ? "Creating user..." : "Create User"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}