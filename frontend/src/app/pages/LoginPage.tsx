import { useState } from "react";
import { useNavigate, useLocation, Link } from "react-router";
import { Card } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { Label } from "../components/ui/label";
import { AlertCircle } from "lucide-react";
import { useAuth } from "../context/AuthContext";

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ProtectedRoute sends inactive users here with state.reason = "inactive"
  const inactiveRedirect = (location.state as any)?.reason === "inactive";

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      await login(email, password);
      // Redirect back to the page they were trying to reach, or home
      const from = (location.state as any)?.from ?? "/";
      navigate(from, { replace: true });
    } catch (err: any) {
      // Map backend detail strings to user-facing copy.
      setError("Invalid email or password. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#1e3a8a] to-[#0f172a] flex items-center justify-center p-4">
      <Card className="w-full max-w-md p-8 bg-white">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-semibold text-[#1e3a8a] mb-2">
            Lab Budget Monitor
          </h1>
          <p className="text-sm text-muted-foreground">
            SIT POD lab spending and budget tracking
          </p>
        </div>

        {/* Shown when ProtectedRoute redirects a deactivated user here */}
        {inactiveRedirect && !error && (
          <div className="mb-6 flex items-start gap-3 rounded-lg border border-[#fecaca] bg-[#fef2f2] p-4">
            <AlertCircle className="h-5 w-5 text-[#dc2626] flex-shrink-0 mt-0.5" />
            <p className="text-sm text-[#dc2626]">
              Your account has been deactivated. Please contact your
              administrator.
            </p>
          </div>
        )}

        <form onSubmit={handleLogin} className="space-y-6">
          <div className="space-y-2">
            <Label htmlFor="email">SIT Email</Label>
            <Input
              id="email"
              type="email"
              placeholder="john.doe@sit.edu.sg"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              disabled={isSubmitting}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              placeholder="Enter your password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              disabled={isSubmitting}
            />
          </div>

          {error && (
            <div className="flex items-start gap-3 rounded-lg border border-[#fecaca] bg-[#fef2f2] p-3">
              <AlertCircle className="h-4 w-4 text-[#dc2626] flex-shrink-0 mt-0.5" />
              <p className="text-sm text-[#dc2626]">{error}</p>
            </div>
          )}

          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="rounded border-border text-[#1e3a8a] focus:ring-[#1e3a8a]"
              />
              <span className="text-muted-foreground">Remember me</span>
            </label>
            <Link
              to="/forgot-password"
              className="text-sm text-[#1e3a8a] hover:underline"
            >
              Forgot password?
            </Link>
          </div>

          <Button
            type="submit"
            className="w-full bg-[#1e3a8a] hover:bg-[#1e40af] text-white"
            disabled={isSubmitting}
          >
            {isSubmitting ? "Signing in..." : "Sign In"}
          </Button>
        </form>

        <div className="mt-6 text-center text-xs text-muted-foreground">
          <p>(c) 2026 SIT. All rights reserved.</p>
        </div>
      </Card>
    </div>
  );
}
