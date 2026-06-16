import { Card } from "../components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Plus, Trash2, Edit } from "lucide-react";
import { UserManagement } from "../components/config/UserManagement";

const mockLabGroups = [
  { id: 1, name: "W3 - Food Processing", budget: 180000, threshold: 80 },
  { id: 2, name: "W4 - Materials Testing", budget: 150000, threshold: 80 },
  { id: 3, name: "W5 - Analytics", budget: 120000, threshold: 80 },
  { id: 4, name: "General", budget: 90000, threshold: 80 },
];

const mockLabs = [
  { id: 1, code: "W3L1", name: "Food Pilot Plant", group: "W3 - Food Processing", budget: 65000, ic: "Alice Johnson" },
  { id: 2, code: "W3L2", name: "Food Chemistry", group: "W3 - Food Processing", budget: 45000, ic: "Bob Smith" },
  { id: 3, code: "W3L3", name: "Food Microbiology", group: "W3 - Food Processing", budget: 40000, ic: "Carol Davis" },
  { id: 4, code: "W4L1", name: "Tensile Testing", group: "W4 - Materials Testing", budget: 55000, ic: "David Lee" },
  { id: 5, code: "W4L2", name: "Materials Analysis", group: "W4 - Materials Testing", budget: 50000, ic: "Emily Wong" },
];

const mockAliases = [
  { id: 1, lab: "W3L1", alias: "Food PP" },
  { id: 2, lab: "W3L1", alias: "Food Pilot Plant" },
  { id: 3, lab: "W3L1", alias: "W3-01-08" },
  { id: 4, lab: "W3L2", alias: "Food Chem" },
  { id: 5, lab: "W3L2", alias: "W3-02-05" },
  { id: 6, lab: "W4L1", alias: "Tensile Lab" },
  { id: 7, lab: "W4L1", alias: "W4-01-12" },
];

const mockCategories = [
  { id: 1, name: "General", description: "Fallback category requiring review when classification is unclear" },
  { id: 2, name: "Consumables", description: "Consumable lab materials and recurring items" },
  { id: 3, name: "Supplies", description: "General supplies for lab operations" },
  { id: 4, name: "Maintenance", description: "Calibration, repair, servicing, and maintenance work" },
  { id: 5, name: "Others", description: "Configured catch-all category after review" },
];

export function SystemConfigPage() {
  return (
    <div className="h-full overflow-auto bg-[#f8f9fa]">
      <div className="p-6">
        <div className="mb-6">
          <h2 className="text-2xl font-semibold text-foreground">
            System Configuration
          </h2>
          <p className="text-sm text-muted-foreground mt-1">
            Manage lab groups, labs, mappings, and budgets
          </p>
        </div>

        <Tabs defaultValue="labgroups" className="w-full">
          <TabsList className="bg-white border border-border mb-6">
            <TabsTrigger value="labgroups">Lab Groups</TabsTrigger>
            <TabsTrigger value="labs">Labs</TabsTrigger>
            <TabsTrigger value="users">Users</TabsTrigger>
            <TabsTrigger value="aliases">Lab Aliases</TabsTrigger>
            <TabsTrigger value="categories">Categories</TabsTrigger>
            <TabsTrigger value="budgets">Budgets</TabsTrigger>
          </TabsList>

          {/* Lab Groups Tab */}
          <TabsContent value="labgroups">
            <Card className="bg-white border-border">
              <div className="p-6 border-b border-border flex items-center justify-between">
                <h3 className="text-lg font-semibold text-foreground">
                  Lab Groups
                </h3>
                <Button className="bg-[#1e3a8a] hover:bg-[#1e40af] text-white">
                  <Plus className="h-4 w-4 mr-2" />
                  Add Lab Group
                </Button>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-[#f8f9fa]">
                    <tr className="border-b border-border">
                      <th className="text-left p-4 text-sm font-medium text-muted-foreground">
                        Name
                      </th>
                      <th className="text-right p-4 text-sm font-medium text-muted-foreground">
                        Annual Budget
                      </th>
                      <th className="text-right p-4 text-sm font-medium text-muted-foreground">
                        Threshold (%)
                      </th>
                      <th className="text-center p-4 text-sm font-medium text-muted-foreground">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {mockLabGroups.map((group) => (
                      <tr
                        key={group.id}
                        className="border-b border-border last:border-0 hover:bg-[#f8f9fa]"
                      >
                        <td className="p-4 text-sm font-medium text-foreground">
                          {group.name}
                        </td>
                        <td className="p-4 text-sm text-right text-foreground">
                          ${group.budget.toLocaleString()}
                        </td>
                        <td className="p-4 text-sm text-right text-foreground">
                          {group.threshold}%
                        </td>
                        <td className="p-4 text-center">
                          <div className="flex items-center justify-center gap-2">
                            <Button size="sm" variant="outline">
                              <Edit className="h-3 w-3" />
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
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

          {/* Labs Tab */}
          <TabsContent value="labs">
            <Card className="bg-white border-border">
              <div className="p-6 border-b border-border flex items-center justify-between">
                <h3 className="text-lg font-semibold text-foreground">Labs</h3>
                <Button className="bg-[#1e3a8a] hover:bg-[#1e40af] text-white">
                  <Plus className="h-4 w-4 mr-2" />
                  Add Lab
                </Button>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-[#f8f9fa]">
                    <tr className="border-b border-border">
                      <th className="text-left p-4 text-sm font-medium text-muted-foreground">
                        Code
                      </th>
                      <th className="text-left p-4 text-sm font-medium text-muted-foreground">
                        Name
                      </th>
                      <th className="text-left p-4 text-sm font-medium text-muted-foreground">
                        Lab Group
                      </th>
                      <th className="text-left p-4 text-sm font-medium text-muted-foreground">
                        Lab IC
                      </th>
                      <th className="text-right p-4 text-sm font-medium text-muted-foreground">
                        Budget
                      </th>
                      <th className="text-center p-4 text-sm font-medium text-muted-foreground">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {mockLabs.map((lab) => (
                      <tr
                        key={lab.id}
                        className="border-b border-border last:border-0 hover:bg-[#f8f9fa]"
                      >
                        <td className="p-4 text-sm font-medium text-[#1e3a8a]">
                          {lab.code}
                        </td>
                        <td className="p-4 text-sm font-medium text-foreground">
                          {lab.name}
                        </td>
                        <td className="p-4 text-sm text-muted-foreground">
                          {lab.group}
                        </td>
                        <td className="p-4 text-sm text-foreground">
                          {lab.ic}
                        </td>
                        <td className="p-4 text-sm text-right text-foreground">
                          ${lab.budget.toLocaleString()}
                        </td>
                        <td className="p-4 text-center">
                          <div className="flex items-center justify-center gap-2">
                            <Button size="sm" variant="outline">
                              <Edit className="h-3 w-3" />
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
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

          {/* Users Tab */}
          <TabsContent value="users">
            <UserManagement />
          </TabsContent>

          {/* Lab Aliases Tab */}
          <TabsContent value="aliases">
            <Card className="bg-white border-border">
              <div className="p-6 border-b border-border flex items-center justify-between">
                <div>
                  <h3 className="text-lg font-semibold text-foreground">
                    Lab Aliases
                  </h3>
                  <p className="text-sm text-muted-foreground mt-1">
                    Alternative names and WBS codes for lab matching
                  </p>
                </div>
                <Button className="bg-[#1e3a8a] hover:bg-[#1e40af] text-white">
                  <Plus className="h-4 w-4 mr-2" />
                  Add Alias
                </Button>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-[#f8f9fa]">
                    <tr className="border-b border-border">
                      <th className="text-left p-4 text-sm font-medium text-muted-foreground">
                        Lab Code
                      </th>
                      <th className="text-left p-4 text-sm font-medium text-muted-foreground">
                        Alias
                      </th>
                      <th className="text-center p-4 text-sm font-medium text-muted-foreground">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {mockAliases.map((alias) => (
                      <tr
                        key={alias.id}
                        className="border-b border-border last:border-0 hover:bg-[#f8f9fa]"
                      >
                        <td className="p-4 text-sm font-medium text-[#1e3a8a]">
                          {alias.lab}
                        </td>
                        <td className="p-4 text-sm text-foreground">
                          {alias.alias}
                        </td>
                        <td className="p-4 text-center">
                          <div className="flex items-center justify-center gap-2">
                            <Button size="sm" variant="outline">
                              <Edit className="h-3 w-3" />
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
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

          {/* Categories Tab */}
          <TabsContent value="categories">
            <Card className="bg-white border-border">
              <div className="p-6 border-b border-border flex items-center justify-between">
                <h3 className="text-lg font-semibold text-foreground">
                  Expense Categories
                </h3>
                <Button className="bg-[#1e3a8a] hover:bg-[#1e40af] text-white">
                  <Plus className="h-4 w-4 mr-2" />
                  Add Category
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
                        Description
                      </th>
                      <th className="text-center p-4 text-sm font-medium text-muted-foreground">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {mockCategories.map((category) => (
                      <tr
                        key={category.id}
                        className="border-b border-border last:border-0 hover:bg-[#f8f9fa]"
                      >
                        <td className="p-4 text-sm font-medium text-foreground">
                          {category.name}
                        </td>
                        <td className="p-4 text-sm text-muted-foreground">
                          {category.description}
                        </td>
                        <td className="p-4 text-center">
                          <div className="flex items-center justify-center gap-2">
                            <Button size="sm" variant="outline">
                              <Edit className="h-3 w-3" />
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
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

          {/* Budgets Tab */}
          <TabsContent value="budgets">
            <Card className="bg-white border-border">
              <div className="p-6 border-b border-border">
                <h3 className="text-lg font-semibold text-foreground">
                  Budget & Threshold Settings
                </h3>
                <p className="text-sm text-muted-foreground mt-1">
                  Set annual budgets and alert thresholds
                </p>
              </div>
              <div className="p-6 space-y-6">
                <Card className="p-4 bg-[#fef3c7] border-[#fde68a] mb-6">
                  <h4 className="text-sm font-semibold text-[#92400e] mb-2">
                    Budget Alert Thresholds
                  </h4>
                  <ul className="text-xs text-[#92400e] space-y-1">
                    <li>- 50% = Warning threshold sent to the assigned Team Lead</li>
                    <li>- 80% = Alert threshold sent to the assigned Team Lead</li>
                    <li>- 95% = Critical threshold sent to the assigned Team Lead</li>
                  </ul>
                </Card>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  <div>
                    <Label>Warning Threshold (%)</Label>
                    <Input
                      type="number"
                      defaultValue="50"
                      className="mt-1"
                    />
                    <p className="text-xs text-muted-foreground mt-1">
                      Initial warning level
                    </p>
                  </div>
                  <div>
                    <Label>Alert Threshold (%)</Label>
                    <Input
                      type="number"
                      defaultValue="80"
                      className="mt-1"
                    />
                    <p className="text-xs text-muted-foreground mt-1">
                      Escalated alert level
                    </p>
                  </div>
                  <div>
                    <Label>Critical Threshold (%)</Label>
                    <Input
                      type="number"
                      defaultValue="95"
                      className="mt-1"
                    />
                    <p className="text-xs text-muted-foreground mt-1">
                      Critical over-expenditure risk
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <Label>Email Notification Recipients</Label>
                    <Input
                      type="email"
                      placeholder="team.leads@company.com"
                      className="mt-1"
                    />
                    <p className="text-xs text-muted-foreground mt-1">
                      Comma-separated email addresses
                    </p>
                  </div>
                  <div>
                    <Label>Fiscal Year Start</Label>
                    <Input
                      type="date"
                      defaultValue="2026-04-01"
                      className="mt-1"
                    />
                    <p className="text-xs text-muted-foreground mt-1">
                      Budget cycle start date
                    </p>
                  </div>
                </div>

                <div className="flex justify-end gap-4 pt-4">
                  <Button variant="outline">Reset to Defaults</Button>
                  <Button className="bg-[#1e3a8a] hover:bg-[#1e40af] text-white">
                    Save Changes
                  </Button>
                </div>
              </div>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
