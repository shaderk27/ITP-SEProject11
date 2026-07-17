import { useState, useEffect } from "react";
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

interface Assignment {
  role_name: string;
  lab_group_id: number | null;
  lab_id: number | null;
}

interface FieldErrors {
  [key: string]: string;
}

const API = import.meta.env.VITE_API_URL ?? "/api";
const ALLOWED_EMAIL_DOMAINS = ["sit.edu.sg", "example.com", "test.com","outlook.com","singaporetech.edu.sg"];
const ROLES: Role[] = [
  { role_id: 1, role_name: "admin" },
  { role_id: 2, role_name: "teamlead" },
  { role_id: 3, role_name: "labic" },
];
export function CreateUserPage() {
  const [roles, setRoles] = useState<Role[]>(ROLES);
  const [labGroups, setLabGroups] = useState<LabGroup[]>([]);
  const [labs, setLabs] = useState<Lab[]>([]);
  const [assignments, setAssignments] = useState<Assignment[]>([]);
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

    fetch(`${API}/auth/assignments`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then(setAssignments)
      .catch(() => setAssignments([]));
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
    const emailDomain = email.split("@")[1] ?? "";

    if (!form.full_name.trim()) errors.full_name = "Full name is required.";
    if (!email) errors.email = "Email is required.";
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email))
      errors.email = "Enter a valid email address.";
    else if (!ALLOWED_EMAIL_DOMAINS.includes(emailDomain))
      errors.email = `Email must end with ${ALLOWED_EMAIL_DOMAINS.join(", ")}.`;
    if (!form.password) errors.password = "Password is required.";
    else if (form.password.length < 8)
      errors.password = "Password must be at least 8 characters.";
    if (form.password !== form.confirm_password)
      errors.confirm_password = "Passwords do not match.";
    if (!form.role_id) errors.role_id = "Role is required.";
    if (
      selectedRoleName === "teamlead" &&
      !form.lab_group_id
    ) {
      errors.lab_group_id = "Lab group is required for Team Lead.";
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

    const payload = {
      role_id: Number(form.role_id),
      full_name: form.full_name.trim(),
      email: form.email.trim(),
      password: form.password,
      ...(form.lab_group_id && { lab_group_id: Number(form.lab_group_id) }),
      ...(form.lab_id && { lab_id: Number(form.lab_id) }),
    };

    setIsSubmitting(true);
    try {
      const res = await fetch(`${API}/auth/users`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) {
        setServerError(data?.detail ?? "Failed to create user. Please try again.");
        return;
      }
      setSuccessMessage(`User "${data.full_name ?? form.full_name}" created successfully.`);
      const createdRole = roles.find((r) => r.role_id === Number(form.role_id));
      if ((form.lab_group_id || form.lab_id) && createdRole) {
        setAssignments((prev) => [
          ...prev,
          {
            role_name: createdRole.role_name,
            lab_group_id: form.lab_group_id ? Number(form.lab_group_id) : null,
            lab_id: form.lab_id ? Number(form.lab_id) : null,
          },
        ]);
      }
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
  const isLabGroupAssigned = (labGroupId: number) =>
    assignments.some(
      (assignment) =>
        assignment.lab_group_id === labGroupId &&
        assignment.role_name.toLowerCase() === selectedRoleName
    );
  const isLabAssigned = (labId: number) =>
    assignments.some(
      (assignment) =>
        assignment.lab_id === labId &&
        assignment.role_name.toLowerCase() === "labic"
    );

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
          {/* Success banner */}
          {successMessage && (
            <div className="flex items-center gap-2 rounded-md bg-green-50 border border-green-200 px-4 py-3 text-sm text-green-700">
              <CheckCircle2 className="h-4 w-4 shrink-0" />
              {successMessage}
            </div>
          )}

          {/* Server error banner */}
          {serverError && (
            <div className="flex items-center gap-2 rounded-md bg-destructive/10 border border-destructive/20 px-4 py-3 text-sm text-destructive">
              <AlertCircle className="h-4 w-4 shrink-0" />
              {serverError}
            </div>
          )}

          {/* Full Name */}
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

          {/* Email */}
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

          {/* Password + Confirm */}
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

          {/* Role */}
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

          {/* Lab Group shown for teamlead only */}
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
                {labGroups.map((g) => (
                  <option key={g.id} value={g.id} disabled={isLabGroupAssigned(g.id)}>
                    {g.name} - {g.wbs_code}
                    {isLabGroupAssigned(g.id) ? " (assigned)" : ""}
                  </option>
                ))}
              </select>
              {fieldErrors.lab_group_id && (
                <p className="text-xs text-destructive">{fieldErrors.lab_group_id}</p>
              )}
            </div>
          )}

          {/* Lab shown for Lab IC only */}
          {showLab && (
            <div className="space-y-1.5">
              <Label htmlFor="lab_id">Lab</Label>
              <p className="text-xs text-muted-foreground">Required for Lab ICs</p>
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
                  <option key={lab.id} value={lab.id} disabled={isLabAssigned(lab.id)}>
                    {lab.name} - {lab.code}
                    {isLabAssigned(lab.id) ? " (assigned)" : ""}
                  </option>
                ))}
              </select>
              {fieldErrors.lab_id && (
                <p className="text-xs text-destructive">{fieldErrors.lab_id}</p>
              )}
            </div>
          )}

          {/* Submit */}
          <Button
            className="w-full"
            onClick={handleSubmit}
            disabled={isSubmitting}
          >
            {isSubmitting ? "Creating user..." : "Create User"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
