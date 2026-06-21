import { useState } from "react";
import { Card } from "../ui/card";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Plus, Edit, Trash2, User } from "lucide-react";
import { StatusBadge } from "../shared/StatusBadge";

interface UserData {
  id: number;
  name: string;
  email: string;
  role: "admin" | "teamlead" | "labic";
  assignedLabs: string[];
  status: "active" | "inactive";
}

const mockUsers: UserData[] = [
  { id: 1, name: "John Doe", email: "john.doe@sit.edu.sg", role: "admin", assignedLabs: [], status: "active" },
  { id: 2, name: "Sarah Chen", email: "sarah.chen@sit.edu.sg", role: "teamlead", assignedLabs: ["W3L1", "W3L2", "W3L3"], status: "active" },
  { id: 3, name: "Michael Tan", email: "michael.tan@sit.edu.sg", role: "teamlead", assignedLabs: ["W4L1", "W4L2"], status: "active" },
  { id: 4, name: "Alice Johnson", email: "alice.johnson@sit.edu.sg", role: "labic", assignedLabs: ["W3L1"], status: "active" },
  { id: 5, name: "Bob Smith", email: "bob.smith@sit.edu.sg", role: "labic", assignedLabs: ["W3L2"], status: "active" },
  { id: 6, name: "Carol Davis", email: "carol.davis@sit.edu.sg", role: "labic", assignedLabs: ["W3L3"], status: "inactive" },
];

const availableLabs = [
  { value: "W3L1", label: "W3L1 - Food Pilot Plant" },
  { value: "W3L2", label: "W3L2 - Food Chemistry" },
  { value: "W3L3", label: "W3L3 - Food Microbiology" },
  { value: "W4L1", label: "W4L1 - Tensile Testing" },
  { value: "W4L2", label: "W4L2 - Materials Analysis" },
];

export function UserManagement() {
  const [users, setUsers] = useState<UserData[]>(mockUsers);
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [editingUser, setEditingUser] = useState<UserData | null>(null);
  const [formData, setFormData] = useState({
    name: "",
    email: "",
    role: "labic" as "admin" | "teamlead" | "labic",
    assignedLabs: [] as string[],
  });

  const handleAddUser = () => {
    const newUser: UserData = {
      id: users.length + 1,
      ...formData,
      status: "active",
    };
    setUsers([...users, newUser]);
    setShowAddDialog(false);
    resetForm();
  };

  const handleEditUser = (user: UserData) => {
    setEditingUser(user);
    setFormData({
      name: user.name,
      email: user.email,
      role: user.role,
      assignedLabs: user.assignedLabs,
    });
    setShowAddDialog(true);
  };

  const handleUpdateUser = () => {
    if (editingUser) {
      setUsers(users.map(u =>
        u.id === editingUser.id
          ? { ...u, ...formData }
          : u
      ));
      setShowAddDialog(false);
      setEditingUser(null);
      resetForm();
    }
  };

  const handleDeleteUser = (userId: number) => {
    if (confirm("Are you sure you want to delete this user?")) {
      setUsers(users.filter(u => u.id !== userId));
    }
  };

  const resetForm = () => {
    setFormData({
      name: "",
      email: "",
      role: "labic",
      assignedLabs: [],
    });
  };

  const toggleLabAssignment = (labCode: string) => {
    setFormData(prev => ({
      ...prev,
      assignedLabs: prev.assignedLabs.includes(labCode)
        ? prev.assignedLabs.filter(l => l !== labCode)
        : [...prev.assignedLabs, labCode]
    }));
  };

  const getRoleBadgeStatus = (role: string) => {
    switch (role) {
      case "admin": return "override";
      case "teamlead": return "healthy";
      case "labic": return "info";
      default: return "general";
    }
  };

  return (
    <>
      <Card className="bg-white border-border">
        <div className="p-6 border-b border-border flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold text-foreground">User Management</h3>
            <p className="text-sm text-muted-foreground mt-1">
              Manage users and assign them to lab groups
            </p>
          </div>
          <Button
            className="bg-[#1e3a8a] hover:bg-[#1e40af] text-white"
            onClick={() => {
              resetForm();
              setEditingUser(null);
              setShowAddDialog(true);
            }}
          >
            <Plus className="h-4 w-4 mr-2" />
            Add User
          </Button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-[#f8f9fa]">
              <tr className="border-b border-border">
                <th className="text-left p-4 text-sm font-medium text-muted-foreground">
                  Name
                </th>
                <th className="text-left p-4 text-sm font-medium text-muted-foreground">
                  Email
                </th>
                <th className="text-left p-4 text-sm font-medium text-muted-foreground">
                  Role
                </th>
                <th className="text-left p-4 text-sm font-medium text-muted-foreground">
                  Assigned Labs
                </th>
                <th className="text-left p-4 text-sm font-medium text-muted-foreground">
                  Status
                </th>
                <th className="text-center p-4 text-sm font-medium text-muted-foreground">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr
                  key={user.id}
                  className="border-b border-border last:border-0 hover:bg-[#f8f9fa]"
                >
                  <td className="p-4 text-sm font-medium text-foreground">
                    {user.name}
                  </td>
                  <td className="p-4 text-sm text-muted-foreground">
                    {user.email}
                  </td>
                  <td className="p-4">
                    <StatusBadge status={getRoleBadgeStatus(user.role) as any}>
                      {user.role === "teamlead" ? "Team Lead" : user.role === "labic" ? "Lab IC" : "Admin"}
                    </StatusBadge>
                  </td>
                  <td className="p-4 text-sm text-muted-foreground">
                    {user.assignedLabs.length > 0 ? user.assignedLabs.join(", ") : "—"}
                  </td>
                  <td className="p-4">
                    <StatusBadge status={user.status === "active" ? "approved" : "general"}>
                      {user.status}
                    </StatusBadge>
                  </td>
                  <td className="p-4 text-center">
                    <div className="flex items-center justify-center gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleEditUser(user)}
                      >
                        <Edit className="h-3 w-3" />
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="text-[#dc2626] hover:text-[#dc2626]"
                        onClick={() => handleDeleteUser(user.id)}
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

      {/* Add/Edit User Dialog */}
      <Dialog open={showAddDialog} onOpenChange={setShowAddDialog}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <User className="h-5 w-5 text-[#1e3a8a]" />
              {editingUser ? "Edit User" : "Add New User"}
            </DialogTitle>
            <DialogDescription>
              {editingUser
                ? "Update user details and lab assignments"
                : "Create a new user and assign them to labs"}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="name">Full Name</Label>
                <Input
                  id="name"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="John Doe"
                  className="mt-1"
                />
              </div>
              <div>
                <Label htmlFor="email">SIT Email</Label>
                <Input
                  id="email"
                  type="email"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  placeholder="john.doe@sit.edu.sg"
                  className="mt-1"
                />
              </div>
            </div>

            <div>
              <Label htmlFor="role">Role</Label>
              <Select
                value={formData.role}
                onValueChange={(val) => setFormData({ ...formData, role: val as any })}
              >
                <SelectTrigger id="role" className="mt-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="admin">Admin</SelectItem>
                  <SelectItem value="teamlead">Team Lead</SelectItem>
                  <SelectItem value="labic">Lab IC</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground mt-1">
                {formData.role === "admin" && "Full system access"}
                {formData.role === "teamlead" && "Can upload PRs and review records for assigned labs"}
                {formData.role === "labic" && "Read-only access to assigned lab"}
              </p>
            </div>

            {formData.role !== "admin" && (
              <div>
                <Label>Assigned Labs</Label>
                <div className="grid grid-cols-2 gap-3 mt-2">
                  {availableLabs.map((lab) => (
                    <label
                      key={lab.value}
                      className={`flex items-center gap-2 p-3 border rounded-lg cursor-pointer transition-colors ${
                        formData.assignedLabs.includes(lab.value)
                          ? "bg-[#1e3a8a]/10 border-[#1e3a8a]"
                          : "border-border hover:bg-[#f8f9fa]"
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={formData.assignedLabs.includes(lab.value)}
                        onChange={() => toggleLabAssignment(lab.value)}
                        className="rounded border-border text-[#1e3a8a] focus:ring-[#1e3a8a]"
                      />
                      <span className="text-sm">{lab.label}</span>
                    </label>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground mt-2">
                  {formData.role === "teamlead"
                    ? "Select multiple labs for Team Lead to manage"
                    : "Select one lab for Lab IC"}
                </p>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => {
              setShowAddDialog(false);
              setEditingUser(null);
              resetForm();
            }}>
              Cancel
            </Button>
            <Button
              className="bg-[#1e3a8a] hover:bg-[#1e40af] text-white"
              onClick={editingUser ? handleUpdateUser : handleAddUser}
              disabled={!formData.name || !formData.email || (formData.role !== "admin" && formData.assignedLabs.length === 0)}
            >
              {editingUser ? "Update User" : "Add User"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
