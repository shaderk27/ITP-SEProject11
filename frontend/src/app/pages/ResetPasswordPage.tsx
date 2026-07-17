import { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { Label } from "../components/ui/label";
import { AlertCircle, KeyRound, CheckCircle2 } from "lucide-react";
import { useAuth } from "../context/AuthContext";

interface FieldErrors {
  [key: string]: string;
}

const API = import.meta.env.VITE_API_URL ?? "/api";

export function ResetPasswordPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, clearResetFlag,isLoading } = useAuth();
  useEffect(() => { //if user not logged in
    if (!isLoading && !user) {
      navigate("/login", { replace: true });
    }
  }, [user, isLoading, navigate]);

  const isForced = (location.state as any)?.forced === true || user?.mustResetPassword === true;

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});

  const [form, setForm] = useState({
    current_password: "",
    new_password: "",
    confirm_password: "",
  });

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
    if (fieldErrors[name]) {
      setFieldErrors((prev) => ({ ...prev, [name]: "" }));
    }
  };

  const validate = (): boolean => {
    const errors: FieldErrors = {};

    // Current password is optional when user has an active temp password
    if (!isForced && !form.current_password)
      errors.current_password = "Current password is required.";

    if (!form.new_password)
      errors.new_password = "New password is required.";
    else if (form.new_password.length < 8)
      errors.new_password = "Password must be at least 8 characters.";
    else if (form.current_password && form.new_password === form.current_password)
      errors.new_password = "New password must differ from your current password.";

    if (!form.confirm_password)
      errors.confirm_password = "Please confirm your new password.";
    else if (form.new_password !== form.confirm_password)
      errors.confirm_password = "Passwords do not match.";

    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async () => {
    setSuccessMessage(null);
    setServerError(null);
    if (!validate()) return;

    setIsSubmitting(true);
    try {
      const res = await fetch(`${API}/auth/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          current_password: form.current_password || undefined,
          new_password: form.new_password,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        if (res.status === 400) {
          setFieldErrors({ current_password: "Current password is incorrect." });
        } else {
          setServerError(data?.detail ?? "Failed to reset password. Please try again.");
        }
        return;
      }

      // Clear forced reset flag and redirect to dashboard
      if (isForced) {
        clearResetFlag();
        navigate("/", { replace: true });
        return;
      }

      setSuccessMessage("Password reset successfully. Use your new password next time you sign in.");
      setForm({ current_password: "", new_password: "", confirm_password: "" });
    } catch {
      setServerError("Network error. Check your connection and try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-muted/40 flex items-start justify-center p-8">
      <Card className="w-full max-w-lg">
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary/10 text-primary">
              <KeyRound className="h-5 w-5" />
            </div>
            <div>
              <CardTitle>Reset Password</CardTitle>
              <CardDescription>
                {isForced
                  ? "You must set a new password before continuing."
                  : "Update your account password"}
              </CardDescription>
            </div>
          </div>
        </CardHeader>

        <CardContent className="space-y-5">
          {/* Forced reset banner */}
          {isForced && (
            <div className="flex items-center gap-2 rounded-md bg-amber-50 border border-amber-200 px-4 py-3 text-sm text-amber-700">
              <AlertCircle className="h-4 w-4 shrink-0" />
              You logged in with a temporary password. Please set a new password to continue.
            </div>
          )}

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

          {/* Current Password — hidden when forced (temp password flow) */}
          {!isForced && (
            <div className="space-y-1.5">
              <Label htmlFor="current_password">
                Current Password <span className="text-destructive">*</span>
              </Label>
              <Input
                id="current_password"
                name="current_password"
                type="password"
                autoComplete="current-password"
                value={form.current_password}
                onChange={handleChange}
                placeholder="Enter your current password"
                className={fieldErrors.current_password ? "border-destructive" : ""}
                disabled={isSubmitting}
              />
              {fieldErrors.current_password && (
                <p className="text-xs text-destructive">{fieldErrors.current_password}</p>
              )}
            </div>
          )}

          {/* New Password + Confirm */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="new_password">
                New Password <span className="text-destructive">*</span>
              </Label>
              <Input
                id="new_password"
                name="new_password"
                type="password"
                autoComplete="new-password"
                value={form.new_password}
                onChange={handleChange}
                placeholder="Min. 8 characters"
                className={fieldErrors.new_password ? "border-destructive" : ""}
                disabled={isSubmitting}
              />
              {fieldErrors.new_password && (
                <p className="text-xs text-destructive">{fieldErrors.new_password}</p>
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
                autoComplete="new-password"
                value={form.confirm_password}
                onChange={handleChange}
                placeholder="Re-enter new password"
                className={fieldErrors.confirm_password ? "border-destructive" : ""}
                disabled={isSubmitting}
              />
              {fieldErrors.confirm_password && (
                <p className="text-xs text-destructive">{fieldErrors.confirm_password}</p>
              )}
            </div>
          </div>

          {/* Submit */}
          <Button
            className="w-full"
            onClick={handleSubmit}
            disabled={isSubmitting}
          >
            {isSubmitting ? "Resetting password..." : "Reset Password"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
