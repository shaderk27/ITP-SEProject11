import { useState } from "react";
import { useNavigate } from "react-router";
import { Card } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { Label } from "../components/ui/label";
import { AlertCircle, CheckCircle2, ArrowLeft } from "lucide-react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export function ForgotPasswordPage() {
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      const res = await fetch(`${API_BASE_URL}/api/auth/forgot-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });

      if (res.ok) {
        setSubmitted(true);
      } else {
        setError("Something went wrong. Please try again.");
      }
    } catch (err) {
      setError("Unable to connect to the server. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#1e3a8a] to-[#0f172a] flex items-center justify-center p-4 ">
      <Card className="w-full max-w-md p-4 bg-white">
        <div className="mb-2 text-center">
          <h1 className="text-3xl font-semibold text-[#1e3a8a] mb-2">
            Lab Budget Monitor
          </h1>
          <p className="text-sm text-muted-foreground">
            SIT POD lab spending and budget tracking
          </p>
        </div>

        {submitted ? (
          // Success state
          <div className="space-y-6">
            <div className="flex flex-col items-center gap-3 rounded-lg border border-green-200 bg-green-50 p-6 text-center">
              <CheckCircle2 className="size-8 text-green-600" />
              <div>
                <p className="text-sm text-green-700 mt-1">
                  If <span className="font-medium">{email}</span> is registered,
                  a temporary password has been sent.
                </p>
              </div>
            </div>
            <p className="text-xs text-center text-muted-foreground">
              It expires in 1 hour.<br/>
              Check your spam folder if you don't see it within a few minutes.
            </p>
            <Button
              className="w-full bg-[#1e3a8a] hover:bg-[#1e40af] text-white"
              onClick={() => navigate("/login")}
            >
              Back to Sign In
            </Button>
          </div>
        ) : (
          // Form state
          <>
            <div className="mb-6">
              <h2 className="text-lg font-semibold text-foreground">
                Reset your password
              </h2>
              <p className="text-sm text-muted-foreground mt-1">
                Enter your SIT email address and we'll send you a temporary
                password.
              </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-6">
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

              {error && (
                <div className="flex items-start gap-3 rounded-lg border border-[#fecaca] bg-[#fef2f2] p-3">
                  <AlertCircle className="h-4 w-4 text-[#dc2626] flex-shrink-0 mt-0.5" />
                  <p className="text-sm text-[#dc2626]">{error}</p>
                </div>
              )}

              <Button
                type="submit"
                className="w-full bg-[#1e3a8a] hover:bg-[#1e40af] text-white"
                disabled={isSubmitting}
              >
                {isSubmitting ? "Sending..." : "Send Temporary Password"}
              </Button>

              <button
                type="button"
                onClick={() => navigate("/login")}
                className="w-full flex items-center justify-center gap-2 text-sm text-[#1e3a8a] hover:underline"
              >
                <ArrowLeft className="h-3 w-3" />
                Back to Sign In
              </button>
            </form>
          </>
        )}

        <div className="mt-6 text-center text-xs text-muted-foreground">
          <p>(c) 2026 SIT. All rights reserved.</p>
        </div>
      </Card>
    </div>
  );
}
