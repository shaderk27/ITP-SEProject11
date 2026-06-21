import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { Label } from "../components/ui/label";
import { AlertCircle, UserPlus, CheckCircle2 } from "lucide-react";

// ── Types ─────────────────────────────────────────────────────────────────────
interface Role {
  role_id: number;
  role_name: string;
}

interface LabGroup {
  lab_group_id: number;
  lab_group_name: string;
  wbs_code: string;
}

interface FieldErrors {
  [key: string]: string;
}

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8080";;
const ROLES: Role[] = [
  { role_id: 1, role_name: "admin" },
  { role_id: 2, role_name: "teamlead" },
  { role_id: 3, role_name: "labic" },
];
// ── Page ──────────────────────────────────────────────────────────────────────
export function CreateUserPage() {
  const [roles] = useState<Role[]>(ROLES);
  const [labGroups, setLabGroups] = useState<LabGroup[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});

  const [form, setForm] = useState({
    full_name: "",
    email: "",
    password: "",
    confirm_password: "",
    staff_id: "",
    role_id: "",
    lab_group_id: "",
  });

useEffect(() => {


  fetch(`${API}/api/config/lab-groups`, { credentials: "include" })
    .then((r) => (r.ok ? r.json() : []))
    .then(setLabGroups)
    .catch(() => setLabGroups([]));
}, []);
  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>
  ) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
    if (fieldErrors[name]) {
      setFieldErrors((prev) => ({ ...prev, [name]: "" }));
    }
  };

  const validate = (): boolean => {
    const errors: FieldErrors = {};
    if (!form.full_name.trim()) errors.full_name = "Full name is required.";
    if (!form.email.trim()) errors.email = "Email is required.";
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email))
      errors.email = "Enter a valid email address.";
    if (!form.password) errors.password = "Password is required.";
    if (form.password !== form.confirm_password)
      errors.confirm_password = "Passwords do not match.";
    if (!form.role_id) errors.role_id = "Role is required.";
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
      ...(form.staff_id.trim() && { staff_id: form.staff_id.trim() }),
      ...(form.lab_group_id && { lab_group_id: Number(form.lab_group_id) }),
    };

    setIsSubmitting(true);
    try {
      const res = await fetch(`${API}/api/auth/users`, {
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
      setForm({
        full_name: "",
        email: "",
        password: "",
        confirm_password: "",
        staff_id: "",
        role_id: "",
        lab_group_id: "",
      });
    } catch {
      setServerError("Network error. Check your connection and try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const selectedRole = roles.find((r) => r.role_id === Number(form.role_id));
  const showLabGroup =
    selectedRole?.role_name === "teamlead" || selectedRole?.role_name === "labic";

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

          {/* Full Name + Staff ID */}
          <div className="grid grid-cols-2 gap-4">
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
              <Label htmlFor="staff_id">Staff ID</Label>
              <Input
                id="staff_id"
                name="staff_id"
                value={form.staff_id}
                onChange={handleChange}
                placeholder="e.g. S12345 (optional)"
              />
            </div>
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
              <option value="">Select a role…</option>
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

          {/* Lab Group — shown for teamlead / labic only */}
          {showLabGroup && (
            <div className="space-y-1.5">
              <Label htmlFor="lab_group_id">Lab Group</Label>
              <p className="text-xs text-muted-foreground">Required for Team Leads and Lab ICs</p>
              <select
                id="lab_group_id"
                name="lab_group_id"
                value={form.lab_group_id}
                onChange={handleChange}
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                <option value="">Select a lab group…</option>
                {labGroups.map((g) => (
                  <option key={g.lab_group_id} value={g.lab_group_id}>
                    {g.lab_group_name} — {g.wbs_code}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Submit */}
          <Button
            className="w-full"
            onClick={handleSubmit}
            disabled={isSubmitting}
          >
            {isSubmitting ? "Creating user…" : "Create User"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
