import { useState, useEffect } from "react";
import { Card } from "../components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Button } from "../components/ui/button";
import { Plus, Trash2, Edit, X } from "lucide-react";
import { UserManagement } from "../components/config/UserManagement";

const mockAliases = [{ id: 1, lab: "W3L1", alias: "Food PP" }];

export function SystemConfigPage() {
  const [labGroups, setLabGroups] = useState<any[]>([]);
  const [labs, setLabs] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  
  // --- NEW: MODAL & FORM STATE ---
  const [isGroupModalOpen, setIsGroupModalOpen] = useState(false);
  const [newGroupForm, setNewGroupForm] = useState({ name: "", wbs_code: "", description: "" });

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

  // 1. Fetch Data (Read)
  const fetchConfigData = async () => {
    try {
      const [groupsRes, labsRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/config/labgroups`),
        fetch(`${API_BASE_URL}/api/config/labs`)
      ]);
      setLabGroups(await groupsRes.json());
      setLabs(await labsRes.json());
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchConfigData();
  }, []);

  // 2. Create Data (POST)
  const handleCreateGroup = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch(`${API_BASE_URL}/api/config/labgroups`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newGroupForm),
      });
      
      if (res.ok) {
        setIsGroupModalOpen(false);
        setNewGroupForm({ name: "", wbs_code: "", description: "" });
        fetchConfigData(); // Refresh the table
      }
    } catch (error) {
      console.error("Failed to create lab group", error);
    }
  };

  // 3. Delete Data (DELETE)
  const handleDeleteGroup = async (id: number, name: string) => {
    // Standard browser confirmation prompt
    if (!window.confirm(`Are you sure you want to delete "${name}"?`)) return;

    try {
      const res = await fetch(`${API_BASE_URL}/api/config/labgroups/${id}`, {
        method: "DELETE",
      });
      if (res.ok) {
        fetchConfigData(); // Refresh the table to remove the deleted row
      }
    } catch (error) {
      console.error("Failed to delete lab group", error);
    }
  };

  if (isLoading) return <div className="p-8 text-center text-muted-foreground">Loading system configuration...</div>;

  return (
    <div className="h-full overflow-auto bg-[#f8f9fa] relative">
      <div className="p-6">
        <div className="mb-6">
          <h2 className="text-2xl font-semibold text-foreground">System Configuration</h2>
          <p className="text-sm text-muted-foreground mt-1">Manage lab groups, labs, mappings, and budgets</p>
        </div>

        <Tabs defaultValue="labgroups" className="w-full">
          <TabsList className="bg-white border border-border mb-6">
            <TabsTrigger value="labgroups">Lab Groups</TabsTrigger>
            <TabsTrigger value="labs">Labs</TabsTrigger>
            <TabsTrigger value="users">Users</TabsTrigger>
            <TabsTrigger value="aliases">Lab Aliases</TabsTrigger>
          </TabsList>

          {/* Lab Groups Tab */}
          <TabsContent value="labgroups">
            <Card className="bg-white border-border">
              <div className="p-6 border-b border-border flex items-center justify-between">
                <h3 className="text-lg font-semibold text-foreground">Lab Groups</h3>
                {/* OPEN MODAL BUTTON */}
                <Button onClick={() => setIsGroupModalOpen(true)} className="bg-[#1e3a8a] hover:bg-[#1e40af] text-white">
                  <Plus className="h-4 w-4 mr-2" /> Add Lab Group
                </Button>
              </div>
              
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-[#f8f9fa]">
                    <tr className="border-b border-border">
                      <th className="text-left p-4 text-sm font-medium text-muted-foreground">Name</th>
                      <th className="text-right p-4 text-sm font-medium text-muted-foreground">Annual Budget</th>
                      <th className="text-center p-4 text-sm font-medium text-muted-foreground">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {labGroups.map((group) => (
                      <tr key={group.id} className="border-b border-border last:border-0 hover:bg-[#f8f9fa]">
                        <td className="p-4 text-sm font-medium text-foreground">{group.name}</td>
                        <td className="p-4 text-sm text-right text-foreground">${group.budget.toLocaleString()}</td>
                        <td className="p-4 text-center">
                          <div className="flex items-center justify-center gap-2">
                            <Button size="sm" variant="outline"><Edit className="h-3 w-3" /></Button>
                            {/* DELETE BUTTON CONNECTED HERE */}
                            <Button 
                              size="sm" 
                              variant="outline" 
                              onClick={() => handleDeleteGroup(group.id, group.name)}
                              className="text-[#dc2626] hover:text-[#dc2626]"
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

          {/* Labs Tab (Buttons not wired yet, follow the blueprint above!) */}
          <TabsContent value="labs">
            <Card className="bg-white border-border">
               {/* Content hidden for brevity - kept exactly the same as your previous code */}
               <div className="p-6 text-center text-muted-foreground">Labs Table...</div>
            </Card>
          </TabsContent>

          <TabsContent value="users">
            <UserManagement />
          </TabsContent>
        </Tabs>
      </div>

      {/* --- NEW: TAILWIND MODAL OVERLAY FOR ADDING LAB GROUPS --- */}
      {isGroupModalOpen && (
        <div className="absolute inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card className="w-full max-w-md bg-white p-6 shadow-xl">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-bold">Add New Lab Group</h3>
              <Button variant="ghost" size="sm" onClick={() => setIsGroupModalOpen(false)}>
                <X className="h-4 w-4" />
              </Button>
            </div>
            
            <form onSubmit={handleCreateGroup} className="space-y-4">
              <div>
                <label className="text-sm font-medium">Group Name</label>
                <input 
                  type="text" 
                  required
                  className="w-full mt-1 p-2 border rounded-md" 
                  placeholder="e.g. W1 - Advanced Robotics"
                  value={newGroupForm.name}
                  onChange={(e) => setNewGroupForm({...newGroupForm, name: e.target.value})}
                />
              </div>
              <div>
                <label className="text-sm font-medium">WBS Code Prefix</label>
                <input 
                  type="text" 
                  className="w-full mt-1 p-2 border rounded-md" 
                  placeholder="e.g. W1"
                  value={newGroupForm.wbs_code}
                  onChange={(e) => setNewGroupForm({...newGroupForm, wbs_code: e.target.value})}
                />
              </div>
              <div>
                <label className="text-sm font-medium">Description</label>
                <textarea 
                  className="w-full mt-1 p-2 border rounded-md" 
                  rows={3}
                  value={newGroupForm.description}
                  onChange={(e) => setNewGroupForm({...newGroupForm, description: e.target.value})}
                />
              </div>
              
              <div className="flex justify-end gap-2 pt-4">
                <Button type="button" variant="outline" onClick={() => setIsGroupModalOpen(false)}>Cancel</Button>
                <Button type="submit" className="bg-[#1e3a8a] text-white">Save Lab Group</Button>
              </div>
            </form>
          </Card>
        </div>
      )}
    </div>
  );
}