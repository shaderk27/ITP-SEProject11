import { useState, useEffect } from "react";
import { Card } from "../components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Button } from "../components/ui/button";
import { Plus, Trash2, Edit, X } from "lucide-react";
import { UserManagement } from "../components/config/UserManagement";

export function SystemConfigPage() {
  const [labGroups, setLabGroups] = useState<any[]>([]);
  const [labs, setLabs] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  
  // --- MODAL & FORM STATES ---
  const [isGroupModalOpen, setIsGroupModalOpen] = useState(false);
  const [newGroupForm, setNewGroupForm] = useState({ name: "", wbs_code: "", description: "" });

  const [isLabModalOpen, setIsLabModalOpen] = useState(false);
  const [newLabForm, setNewLabForm] = useState({ lab_code: "", lab_name: "", lab_group_id: "", ic_name: "", ic_email: "", venue: "" });

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

  // --- DATA FETCHING ---
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

  // --- LAB GROUP CRUD ---
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
        fetchConfigData();
      }
    } catch (error) { console.error(error); }
  };

  const handleDeleteGroup = async (id: number, name: string) => {
    if (!window.confirm(`Are you sure you want to delete Lab Group "${name}"?`)) return;
    try {
      const res = await fetch(`${API_BASE_URL}/api/config/labgroups/${id}`, { method: "DELETE" });
      if (res.ok) fetchConfigData();
    } catch (error) { console.error(error); }
  };

  // --- LAB CRUD ---
  const handleCreateLab = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch(`${API_BASE_URL}/api/config/labs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...newLabForm, lab_group_id: Number(newLabForm.lab_group_id) }),
      });
      if (res.ok) {
        setIsLabModalOpen(false);
        setNewLabForm({ lab_code: "", lab_name: "", lab_group_id: "", ic_name: "", ic_email: "", venue: "" });
        fetchConfigData();
      }
    } catch (error) { console.error(error); }
  };

  const handleDeleteLab = async (id: number, name: string) => {
    if (!window.confirm(`Are you sure you want to delete Lab "${name}"?`)) return;
    try {
      const res = await fetch(`${API_BASE_URL}/api/config/labs/${id}`, { method: "DELETE" });
      if (res.ok) fetchConfigData();
    } catch (error) { console.error(error); }
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
          </TabsList>

          {/* LAB GROUPS TAB */}
          <TabsContent value="labgroups">
            <Card className="bg-white border-border">
              <div className="p-6 border-b border-border flex items-center justify-between">
                <h3 className="text-lg font-semibold text-foreground">Lab Groups</h3>
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
                            <Button size="sm" variant="outline" onClick={() => handleDeleteGroup(group.id, group.name)} className="text-[#dc2626] hover:text-[#dc2626]">
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

          {/* LABS TAB */}
          <TabsContent value="labs">
            <Card className="bg-white border-border">
              <div className="p-6 border-b border-border flex items-center justify-between">
                <h3 className="text-lg font-semibold text-foreground">Labs</h3>
                <Button onClick={() => setIsLabModalOpen(true)} className="bg-[#1e3a8a] hover:bg-[#1e40af] text-white">
                  <Plus className="h-4 w-4 mr-2" /> Add Lab
                </Button>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-[#f8f9fa]">
                    <tr className="border-b border-border">
                      <th className="text-left p-4 text-sm font-medium text-muted-foreground">Code</th>
                      <th className="text-left p-4 text-sm font-medium text-muted-foreground">Name</th>
                      <th className="text-left p-4 text-sm font-medium text-muted-foreground">Lab Group</th>
                      <th className="text-left p-4 text-sm font-medium text-muted-foreground">Lab IC</th>
                      <th className="text-center p-4 text-sm font-medium text-muted-foreground">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {labs.map((lab) => (
                      <tr key={lab.id} className="border-b border-border last:border-0 hover:bg-[#f8f9fa]">
                        <td className="p-4 text-sm font-medium text-[#1e3a8a]">{lab.code}</td>
                        <td className="p-4 text-sm font-medium text-foreground">{lab.name}</td>
                        <td className="p-4 text-sm text-muted-foreground">{lab.group}</td>
                        <td className="p-4 text-sm text-foreground">{lab.ic}</td>
                        <td className="p-4 text-center">
                          <div className="flex items-center justify-center gap-2">
                            <Button size="sm" variant="outline"><Edit className="h-3 w-3" /></Button>
                            <Button size="sm" variant="outline" onClick={() => handleDeleteLab(lab.id, lab.name)} className="text-[#dc2626] hover:text-[#dc2626]">
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
            <UserManagement />
          </TabsContent>
        </Tabs>
      </div>

      {/* --- MODALS --- */}
      
      {/* LAB GROUP MODAL */}
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
                <label className="text-sm font-medium">Group Name <span className="text-red-500">*</span></label>
                <input type="text" required className="w-full mt-1 p-2 border rounded-md" placeholder="e.g. Robotics" value={newGroupForm.name} onChange={(e) => setNewGroupForm({...newGroupForm, name: e.target.value})} />
              </div>
              <div>
                <label className="text-sm font-medium">Lab Group Code</label>
                <input type="text" className="w-full mt-1 p-2 border rounded-md" placeholder="e.g. Rob1" value={newGroupForm.wbs_code} onChange={(e) => setNewGroupForm({...newGroupForm, wbs_code: e.target.value})} />
              </div>
              <div>
                <label className="text-sm font-medium">Description</label>
                <textarea className="w-full mt-1 p-2 border rounded-md" rows={3} value={newGroupForm.description} onChange={(e) => setNewGroupForm({...newGroupForm, description: e.target.value})} />
              </div>
              <div className="flex justify-end gap-2 pt-4">
                <Button type="button" variant="outline" onClick={() => setIsGroupModalOpen(false)}>Cancel</Button>
                <Button type="submit" className="bg-[#1e3a8a] text-white">Save Lab Group</Button>
              </div>
            </form>
          </Card>
        </div>
      )}

      {/* LAB MODAL */}
      {isLabModalOpen && (
        <div className="absolute inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card className="w-full max-w-2xl bg-white p-6 shadow-xl">
            <div className="flex justify-between items-center mb-6">
              <h3 className="text-xl font-bold">Add New Lab</h3>
              <Button variant="ghost" size="sm" onClick={() => setIsLabModalOpen(false)}>
                <X className="h-5 w-5" />
              </Button>
            </div>
            <form onSubmit={handleCreateLab} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium text-gray-700">Lab Code <span className="text-red-500">*</span></label>
                  <input type="text" required className="w-full mt-1 p-2 border rounded-md" placeholder="e.g. W3-05-22" value={newLabForm.lab_code} onChange={(e) => setNewLabForm({...newLabForm, lab_code: e.target.value})} />
                </div>
                <div>
                  <label className="text-sm font-medium text-gray-700">Lab Name <span className="text-red-500">*</span></label>
                  <input type="text" required className="w-full mt-1 p-2 border rounded-md" placeholder="e.g. Food Pilot Plant" value={newLabForm.lab_name} onChange={(e) => setNewLabForm({...newLabForm, lab_name: e.target.value})} />
                </div>
                <div className="col-span-2">
                  <label className="text-sm font-medium text-gray-700">Lab Group <span className="text-red-500">*</span></label>
                  <select required className="w-full mt-1 p-2 border rounded-md bg-white" value={newLabForm.lab_group_id} onChange={(e) => setNewLabForm({...newLabForm, lab_group_id: e.target.value})}>
                    <option value="" disabled>Select a Lab Group</option>
                    {labGroups.map(group => (
                      <option key={group.id} value={group.id}>{group.name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-sm font-medium text-gray-700">IC Name</label>
                  <input type="text" className="w-full mt-1 p-2 border rounded-md" placeholder="e.g. Alice Johnson" value={newLabForm.ic_name} onChange={(e) => setNewLabForm({...newLabForm, ic_name: e.target.value})} />
                </div>
                <div>
                  <label className="text-sm font-medium text-gray-700">IC Email Address</label>
                  <input type="email" className="w-full mt-1 p-2 border rounded-md" placeholder="e.g. alice.j@sit.edu.sg" value={newLabForm.ic_email} onChange={(e) => setNewLabForm({...newLabForm, ic_email: e.target.value})} />
                </div>
                <div className="col-span-2">
                  <label className="text-sm font-medium text-gray-700">Venue</label>
                  <input type="text" className="w-full mt-1 p-2 border rounded-md" placeholder="e.g. Block A, Level 1, Room 05" value={newLabForm.venue} onChange={(e) => setNewLabForm({...newLabForm, venue: e.target.value})} />
                </div>
              </div>
              <div className="flex justify-end gap-3 pt-6 mt-4 border-t">
                <Button type="button" variant="outline" onClick={() => setIsLabModalOpen(false)}>Cancel</Button>
                <Button type="submit" className="bg-[#1e3a8a] text-white">Add Lab</Button>
              </div>
            </form>
          </Card>
        </div>
      )}
    </div>
  );
}