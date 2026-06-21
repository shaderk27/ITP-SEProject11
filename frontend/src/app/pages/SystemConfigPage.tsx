import React, { useState, useEffect } from "react";
import { Card } from "../components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Button } from "../components/ui/button";
import { Plus, Trash2, Edit, X, ChevronDown, ChevronRight, Beaker } from "lucide-react";
import { UserManagement } from "../components/config/UserManagement";

export function SystemConfigPage() {
  const [labGroups, setLabGroups] = useState<any[]>([]);
  const [labs, setLabs] = useState<any[]>([]);
  const [categories, setCategories] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  
  // --- NEW: EXPANDING ROWS STATE ---
  const [expandedGroups, setExpandedGroups] = useState<number[]>([]);

  // --- EDITING STATES ---
  const [editingGroupId, setEditingGroupId] = useState<number | null>(null);
  const [editingLabId, setEditingLabId] = useState<number | null>(null);
  const [editingCategoryId, setEditingCategoryId] = useState<number | null>(null);

  // --- MODAL & FORM STATES ---
  const [isGroupModalOpen, setIsGroupModalOpen] = useState(false);
  const [newGroupForm, setNewGroupForm] = useState({ name: "", wbs_code: "", description: "" });

  const [isCategoryModalOpen, setIsCategoryModalOpen] = useState(false);
  const [newCategoryForm, setNewCategoryForm] = useState({ name: "", description: "" });

  const [isLabModalOpen, setIsLabModalOpen] = useState(false);
  const [newLabForm, setNewLabForm] = useState({ lab_code: "", lab_name: "", lab_group_id: "", ic_name: "", ic_email: "", venue: "", budgets: {} as Record<string, number> });

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

  // --- DATA FETCHING ---
  const fetchConfigData = async () => {
    try {
      const [groupsRes, labsRes, catsRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/config/labgroups`),
        fetch(`${API_BASE_URL}/api/config/labs`),
        fetch(`${API_BASE_URL}/api/config/categories`)
      ]);
      setLabGroups(await groupsRes.json());
      setLabs(await labsRes.json());
      setCategories(await catsRes.json());
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchConfigData();
  }, []);

  // --- NEW: TOGGLE ROW HELPER ---
  const toggleGroupExpand = (groupId: number) => {
    if (expandedGroups.includes(groupId)) {
      setExpandedGroups(expandedGroups.filter(id => id !== groupId));
    } else {
      setExpandedGroups([...expandedGroups, groupId]);
    }
  };

  // --- GENERIC CRUD HANDLERS ---
  const handleSave = async (endpoint: string, method: string, payload: any, onSuccess: () => void) => {
    try {
      const res = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      });
      if (res.ok) { onSuccess(); fetchConfigData(); }
    } catch (error) { console.error(error); }
  };

  const handleDelete = async (endpoint: string, name: string) => {
    if (!window.confirm(`Are you sure you want to delete "${name}"?`)) return;
    try {
      const res = await fetch(`${API_BASE_URL}${endpoint}`, { method: "DELETE" });
      if (res.ok) fetchConfigData();
    } catch (error) { console.error(error); }
  };

  // --- OPEN EDIT MODAL HELPERS ---
  const openEditGroup = (group: any) => {
    setEditingGroupId(group.id);
    setNewGroupForm({ name: group.name, wbs_code: group.wbs_code || "", description: group.description || "" });
    setIsGroupModalOpen(true);
  };

  const openEditCategory = (cat: any) => {
    setEditingCategoryId(cat.id);
    setNewCategoryForm({ name: cat.name, description: cat.description || "" });
    setIsCategoryModalOpen(true);
  };

  const openEditLab = (lab: any) => {
    setEditingLabId(lab.id);
    setNewLabForm({ 
      lab_code: lab.code, lab_name: lab.name, lab_group_id: lab.group_id, 
      ic_name: lab.ic_name || "", ic_email: lab.ic_email || "", venue: lab.venue || "", budgets: lab.budgets || {} 
    });
    setIsLabModalOpen(true);
  };

  // --- CLOSE MODAL HELPERS ---
  const resetGroupModal = () => { setIsGroupModalOpen(false); setEditingGroupId(null); setNewGroupForm({ name: "", wbs_code: "", description: "" }); };
  const resetCategoryModal = () => { setIsCategoryModalOpen(false); setEditingCategoryId(null); setNewCategoryForm({ name: "", description: "" }); };
  const resetLabModal = () => { setIsLabModalOpen(false); setEditingLabId(null); setNewLabForm({ lab_code: "", lab_name: "", lab_group_id: "", ic_name: "", ic_email: "", venue: "", budgets: {} }); };

  if (isLoading) return <div className="p-8 text-center text-muted-foreground">Loading system configuration...</div>;

  return (
    <div className="h-full overflow-auto bg-[#f8f9fa] relative">
      <div className="p-6">
        <div className="mb-6">
          <h2 className="text-2xl font-semibold text-foreground">System Configuration</h2>
          <p className="text-sm text-muted-foreground mt-1">Manage lab groups, labs, categories, and budgets</p>
        </div>

        <Tabs defaultValue="labgroups" className="w-full">
          <TabsList className="bg-white border border-border mb-6">
            <TabsTrigger value="labgroups">Lab Groups</TabsTrigger>
            <TabsTrigger value="labs">Labs</TabsTrigger>
            <TabsTrigger value="categories">Categories</TabsTrigger>
            <TabsTrigger value="users">Users</TabsTrigger>
          </TabsList>

          {/* ======================= LAB GROUPS TAB ======================= */}
          <TabsContent value="labgroups">
            <Card className="bg-white border-border">
              <div className="p-6 border-b border-border flex items-center justify-between">
                <h3 className="text-lg font-semibold text-foreground">Lab Groups Overview</h3>
                <Button onClick={() => { resetGroupModal(); setIsGroupModalOpen(true); }} className="bg-[#1e3a8a] hover:bg-[#1e40af] text-white">
                  <Plus className="h-4 w-4 mr-2" /> Add Lab Group
                </Button>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-[#f8f9fa]">
                    <tr className="border-b border-border text-sm font-medium text-muted-foreground">
                      <th className="w-12 p-4"></th> {/* Blank header for expand button */}
                      <th className="text-left p-4">Lab Group Name</th>
                      <th className="text-left p-4">Lab Group Code</th>
                      <th className="text-right p-4">Allocated Budget</th>
                      <th className="text-right p-4 text-[#16a34a]">Available Balance</th>
                      <th className="text-center p-4">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {labGroups.map((group) => {
                      const isExpanded = expandedGroups.includes(group.id);
                      // Dynamically find all labs that belong to this group
                      const groupLabs = labs.filter(l => l.group_id === group.id);
                      // Future-proofing: spent is mocked to 0 right now
                      const spent = 0; 
                      const availableBalance = group.budget - spent;

                      return (
                        <React.Fragment key={group.id}>
                          <tr className={`border-b border-border hover:bg-[#f8f9fa] ${isExpanded ? 'bg-[#f8f9fa]' : ''}`}>
                            <td className="p-4 text-center">
                              <Button variant="ghost" size="sm" className="h-8 w-8 p-0" onClick={() => toggleGroupExpand(group.id)}>
                                {isExpanded ? <ChevronDown className="h-4 w-4 text-gray-600" /> : <ChevronRight className="h-4 w-4 text-gray-400" />}
                              </Button>
                            </td>
                            <td className="p-4 text-sm font-semibold text-foreground">{group.name}</td>
                            <td className="p-4 text-sm text-muted-foreground">{group.wbs_code || "-"}</td>
                            <td className="p-4 text-sm text-right text-gray-600">
                              ${group.budget?.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                            </td>
                            <td className="p-4 text-sm text-right font-bold text-[#16a34a]">
                              ${availableBalance.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                            </td>
                            <td className="p-4 text-center">
                              <div className="flex items-center justify-center gap-2">
                                <Button size="sm" variant="outline" onClick={() => openEditGroup(group)}><Edit className="h-3 w-3" /></Button>
                                <Button size="sm" variant="outline" onClick={() => handleDelete(`/api/config/labgroups/${group.id}`, group.name)} className="text-[#dc2626]"><Trash2 className="h-3 w-3" /></Button>
                              </div>
                            </td>
                          </tr>
                          
                          {/* THE EXPANDING NESTED LABS TABLE */}
                          {isExpanded && (
                            <tr className="bg-gray-50 border-b border-border shadow-inner">
                              <td colSpan={6} className="p-0">
                                <div className="p-4 pl-16 pr-8">
                                  <div className="flex items-center mb-3">
                                    <Beaker className="h-4 w-4 text-gray-400 mr-2" />
                                    <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wider">Assigned Labs</h4>
                                  </div>
                                  
                                  {groupLabs.length === 0 ? (
                                    <p className="text-sm text-gray-400 italic bg-white p-4 rounded-md border border-gray-200">No labs currently assigned to this group.</p>
                                  ) : (
                                    <table className="w-full bg-white rounded-md border border-gray-200 overflow-hidden shadow-sm">
                                      <thead className="bg-gray-100 border-b border-gray-200">
                                        <tr className="text-xs font-semibold text-gray-500">
                                          <th className="text-left p-3">Lab Code</th>
                                          <th className="text-left p-3">Lab Name</th>
                                          <th className="text-right p-3">Allocated Budget</th>
                                          <th className="text-right p-3 text-[#16a34a]">Available</th>
                                          <th className="text-center p-3">Edit</th>
                                        </tr>
                                      </thead>
                                      <tbody>
                                        {groupLabs.map(lab => (
                                          <tr key={lab.id} className="border-b border-gray-100 last:border-0 hover:bg-gray-50">
                                            <td className="p-3 text-sm font-medium text-[#1e3a8a]">{lab.code}</td>
                                            <td className="p-3 text-sm text-gray-700">{lab.name}</td>
                                            <td className="p-3 text-sm text-right text-gray-500">${lab.budget?.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                                            <td className="p-3 text-sm text-right font-semibold text-[#16a34a]">${(lab.budget - 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                                            <td className="p-3 text-center">
                                              <Button size="sm" variant="ghost" className="h-6 w-6 p-0" onClick={() => openEditLab(lab)}><Edit className="h-3 w-3 text-gray-400 hover:text-gray-700" /></Button>
                                            </td>
                                          </tr>
                                        ))}
                                      </tbody>
                                    </table>
                                  )}
                                </div>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Card>
          </TabsContent>

          {/* ======================= LABS TAB ======================= */}
          <TabsContent value="labs">
            <Card className="bg-white border-border">
              <div className="p-6 border-b border-border flex items-center justify-between">
                <h3 className="text-lg font-semibold text-foreground">Labs Overview</h3>
                <Button onClick={() => { resetLabModal(); setIsLabModalOpen(true); }} className="bg-[#1e3a8a] hover:bg-[#1e40af] text-white">
                  <Plus className="h-4 w-4 mr-2" /> Add Lab
                </Button>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-[#f8f9fa]">
                    <tr className="border-b border-border text-sm font-medium text-muted-foreground">
                      <th className="text-left p-4">Code</th>
                      <th className="text-left p-4">Name</th>
                      <th className="text-left p-4">Parent Group</th>
                      <th className="text-right p-4">Allocated Budget</th>
                      <th className="text-right p-4 text-[#16a34a]">Available Balance</th>
                      <th className="text-center p-4">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {labs.map((lab) => {
                      const labAvailable = lab.budget - 0; // Mocked until expenses are tracked
                      return (
                        <tr key={lab.id} className="border-b border-border hover:bg-[#f8f9fa]">
                          <td className="p-4 text-sm font-bold text-[#1e3a8a]">{lab.code}</td>
                          <td className="p-4 text-sm font-medium text-foreground">{lab.name}</td>
                          <td className="p-4 text-sm text-muted-foreground">{lab.group}</td>
                          <td className="p-4 text-sm text-right text-gray-600">${lab.budget?.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                          <td className="p-4 text-sm text-right font-bold text-[#16a34a]">${labAvailable.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                          <td className="p-4 text-center">
                            <div className="flex items-center justify-center gap-2">
                              <Button size="sm" variant="outline" onClick={() => openEditLab(lab)}><Edit className="h-3 w-3" /></Button>
                              <Button size="sm" variant="outline" onClick={() => handleDelete(`/api/config/labs/${lab.id}`, lab.name)} className="text-[#dc2626]"><Trash2 className="h-3 w-3" /></Button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Card>
          </TabsContent>

          {/* ======================= CATEGORIES TAB ======================= */}
          <TabsContent value="categories">
            <Card className="bg-white border-border">
              <div className="p-6 border-b border-border flex items-center justify-between">
                <h3 className="text-lg font-semibold text-foreground">Spending Categories</h3>
                <Button onClick={() => { resetCategoryModal(); setIsCategoryModalOpen(true); }} className="bg-[#1e3a8a] hover:bg-[#1e40af] text-white">
                  <Plus className="h-4 w-4 mr-2" /> Add Category
                </Button>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-[#f8f9fa]">
                    <tr className="border-b border-border text-sm font-medium text-muted-foreground">
                      <th className="text-left p-4">Category Name</th>
                      <th className="text-left p-4">Description</th>
                      <th className="text-center p-4">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {categories.map((cat) => (
                      <tr key={cat.id} className="border-b border-border hover:bg-[#f8f9fa]">
                        <td className="p-4 text-sm font-medium text-foreground">{cat.name}</td>
                        <td className="p-4 text-sm text-muted-foreground">{cat.description}</td>
                        <td className="p-4 text-center">
                          <div className="flex items-center justify-center gap-2">
                            <Button size="sm" variant="outline" onClick={() => openEditCategory(cat)}><Edit className="h-3 w-3" /></Button>
                            <Button size="sm" variant="outline" onClick={() => handleDelete(`/api/config/categories/${cat.id}`, cat.name)} className="text-[#dc2626]"><Trash2 className="h-3 w-3" /></Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </TabsContent>

          <TabsContent value="users"><UserManagement /></TabsContent>
        </Tabs>
      </div>

      {/* --- MODALS --- */}
      
      {/* LAB GROUP MODAL */}
      {isGroupModalOpen && (
        <div className="absolute inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card className="w-full max-w-md bg-white p-6 shadow-xl">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-bold">{editingGroupId ? "Edit Lab Group" : "Add New Lab Group"}</h3>
              <Button variant="ghost" size="sm" onClick={resetGroupModal}><X className="h-4 w-4" /></Button>
            </div>
            <form onSubmit={(e) => { 
              e.preventDefault(); 
              const endpoint = editingGroupId ? `/api/config/labgroups/${editingGroupId}` : "/api/config/labgroups";
              const method = editingGroupId ? "PUT" : "POST";
              handleSave(endpoint, method, newGroupForm, resetGroupModal); 
            }} className="space-y-4">
              <div><label className="text-sm font-medium">Group Name</label><input type="text" required className="w-full mt-1 p-2 border rounded-md" value={newGroupForm.name} onChange={(e) => setNewGroupForm({...newGroupForm, name: e.target.value})} /></div>
              <div><label className="text-sm font-medium">WBS Prefix</label><input type="text" className="w-full mt-1 p-2 border rounded-md" value={newGroupForm.wbs_code} onChange={(e) => setNewGroupForm({...newGroupForm, wbs_code: e.target.value})} /></div>
              <div><label className="text-sm font-medium">Description</label><textarea className="w-full mt-1 p-2 border rounded-md" rows={3} value={newGroupForm.description} onChange={(e) => setNewGroupForm({...newGroupForm, description: e.target.value})} /></div>
              <div className="flex justify-end gap-2 pt-4"><Button type="button" variant="outline" onClick={resetGroupModal}>Cancel</Button><Button type="submit" className="bg-[#1e3a8a] text-white">{editingGroupId ? "Save Changes" : "Create"}</Button></div>
            </form>
          </Card>
        </div>
      )}

      {/* CATEGORY MODAL */}
      {isCategoryModalOpen && (
        <div className="absolute inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card className="w-full max-w-md bg-white p-6 shadow-xl">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-bold">{editingCategoryId ? "Edit Category" : "Add Spending Category"}</h3>
              <Button variant="ghost" size="sm" onClick={resetCategoryModal}><X className="h-4 w-4" /></Button>
            </div>
            <form onSubmit={(e) => { 
              e.preventDefault(); 
              const endpoint = editingCategoryId ? `/api/config/categories/${editingCategoryId}` : "/api/config/categories";
              const method = editingCategoryId ? "PUT" : "POST";
              handleSave(endpoint, method, newCategoryForm, resetCategoryModal); 
            }} className="space-y-4">
              <div><label className="text-sm font-medium">Category Name</label><input type="text" required className="w-full mt-1 p-2 border rounded-md" placeholder="e.g. Consumables" value={newCategoryForm.name} onChange={(e) => setNewCategoryForm({...newCategoryForm, name: e.target.value})} /></div>
              <div><label className="text-sm font-medium">Description</label><textarea className="w-full mt-1 p-2 border rounded-md" rows={3} value={newCategoryForm.description} onChange={(e) => setNewCategoryForm({...newCategoryForm, description: e.target.value})} /></div>
              <div className="flex justify-end gap-2 pt-4"><Button type="button" variant="outline" onClick={resetCategoryModal}>Cancel</Button><Button type="submit" className="bg-[#1e3a8a] text-white">{editingCategoryId ? "Save Changes" : "Create"}</Button></div>
            </form>
          </Card>
        </div>
      )}

      {/* LAB MODAL */}
      {isLabModalOpen && (
        <div className="absolute inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card className="w-full max-w-2xl bg-white p-6 shadow-xl max-h-[90vh] overflow-y-auto">
            <div className="flex justify-between items-center mb-6">
              <h3 className="text-xl font-bold">{editingLabId ? "Edit Lab" : "Add New Lab"}</h3>
              <Button variant="ghost" size="sm" onClick={resetLabModal}><X className="h-5 w-5" /></Button>
            </div>
            <form onSubmit={(e) => { 
              e.preventDefault(); 
              const endpoint = editingLabId ? `/api/config/labs/${editingLabId}` : "/api/config/labs";
              const method = editingLabId ? "PUT" : "POST";
              handleSave(endpoint, method, { ...newLabForm, lab_group_id: Number(newLabForm.lab_group_id) }, resetLabModal); 
            }} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium text-gray-700">Lab Code</label>
                  <input type="text" required className="w-full mt-1 p-2 border rounded-md uppercase" value={newLabForm.lab_code} onChange={(e) => { const code = e.target.value.toUpperCase(); const parts = code.split('-'); let autoVenue = newLabForm.venue; if (parts.length === 3) { autoVenue = `Block ${parts[0]}, Level ${parts[1]}, Room ${parts[2]}`; } setNewLabForm({...newLabForm, lab_code: code, venue: autoVenue}); }} />
                </div>
                <div><label className="text-sm font-medium text-gray-700">Lab Name</label><input type="text" required className="w-full mt-1 p-2 border rounded-md" value={newLabForm.lab_name} onChange={(e) => setNewLabForm({...newLabForm, lab_name: e.target.value})} /></div>
                <div className="col-span-2">
                  <label className="text-sm font-medium text-gray-700">Lab Group</label>
                  <select required className="w-full mt-1 p-2 border rounded-md bg-white" value={newLabForm.lab_group_id} onChange={(e) => setNewLabForm({...newLabForm, lab_group_id: e.target.value})}>
                    <option value="" disabled>Select a Lab Group</option>
                    {labGroups.map(group => <option key={group.id} value={group.id}>{group.name}</option>)}
                  </select>
                </div>
                <div className="col-span-2"><label className="text-sm font-medium text-gray-700">Venue</label><input type="text" readOnly className="w-full mt-1 p-2 border rounded-md bg-gray-100 text-gray-500" value={newLabForm.venue} /></div>
                
                <div className="col-span-2 mt-4 pt-4 border-t border-gray-200">
                  <h4 className="font-semibold text-gray-800 mb-4">Set Lab Budgets by Category</h4>
                  {categories.length === 0 ? (
                    <p className="text-sm text-red-500 italic">Please add Spending Categories first!</p>
                  ) : (
                    <div className="grid grid-cols-2 gap-4">
                      {categories.map(cat => (
                        <div key={cat.id}>
                          <label className="text-sm font-medium text-gray-700">{cat.name}</label>
                          <div className="relative mt-1">
                            <span className="absolute left-3 top-2.5 text-gray-500">$</span>
                            <input type="number" min="0" step="0.01" className="w-full pl-7 p-2 border rounded-md" placeholder="0.00" value={newLabForm.budgets[cat.id] || ""} onChange={(e) => setNewLabForm({...newLabForm, budgets: { ...newLabForm.budgets, [cat.id]: parseFloat(e.target.value) || 0 }})} />
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
              
              <div className="flex justify-end gap-3 pt-6 mt-4 border-t">
                <Button type="button" variant="outline" onClick={resetLabModal}>Cancel</Button>
                <Button type="submit" className="bg-[#1e3a8a] text-white">{editingLabId ? "Save Changes" : "Create Lab"}</Button>
              </div>
            </form>
          </Card>
        </div>
      )}
    </div>
  );
}