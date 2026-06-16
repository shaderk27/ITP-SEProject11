import { useState } from "react";
import { useNavigate } from "react-router";
import { Card } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { Label } from "../components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { useAuth } from "../context/AuthContext";
import type { UserRole } from "../context/AuthContext";

export function LoginPage() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("admin");

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();

    // Mock user data based on role
    const userData = {
      name: role === "admin" ? "John Doe" : role === "teamlead" ? "Sarah Chen" : "Alice Johnson",
      email: email,
      role: role,
      assignedLabs: role === "teamlead" ? ["W3L1", "W3L2", "W3L3"] : role === "labic" ? ["W3L1"] : undefined,
    };

    login(userData);
    navigate("/");
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
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="role">Role (Demo)</Label>
            <Select value={role} onValueChange={(val) => setRole(val as UserRole)}>
              <SelectTrigger id="role">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="admin">Admin</SelectItem>
                <SelectItem value="teamlead">Team Lead</SelectItem>
                <SelectItem value="labic">Lab IC</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Select role for demonstration purposes
            </p>
          </div>

          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="rounded border-border text-[#1e3a8a] focus:ring-[#1e3a8a]"
              />
              <span className="text-muted-foreground">Remember me</span>
            </label>
            <a
              href="#"
              className="text-sm text-[#1e3a8a] hover:underline"
            >
              Forgot password?
            </a>
          </div>

          <Button
            type="submit"
            className="w-full bg-[#1e3a8a] hover:bg-[#1e40af] text-white"
          >
            Sign In
          </Button>
        </form>

        <div className="mt-6 text-center text-xs text-muted-foreground">
          <p>Demo login for frontend integration</p>
          <p className="mt-1">© 2026 SIT. All rights reserved.</p>
        </div>
      </Card>
    </div>
  );
}
