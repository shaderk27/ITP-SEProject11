import { useState, useEffect } from "react";
import { Navigate } from "react-router";
import { Card } from "../components/ui/card";
import { ShieldAlert, Search, Eye, X } from "lucide-react";
import { Button } from "../components/ui/button";
import { useAuth } from "../context/AuthContext";

export function AuditLogPage() {
  const { user } = useAuth();
  const [logs, setLogs] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedLog, setSelectedLog] = useState<any | null>(null);

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/audit?limit=200`, { credentials: "include" });
        if (res.ok) setLogs(await res.json());
      } catch (err) {
        console.error(err);
      } finally {
        setIsLoading(false);
      }
    };
    if (user?.role === "admin") fetchLogs();
  }, [API_BASE_URL, user]);

  if (user?.role !== "admin") return <Navigate to="/403" replace />;

  const filteredLogs = logs.filter(log => 
    log.action_type.toLowerCase().includes(searchTerm.toLowerCase()) ||
    log.entity_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    log.user_name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="h-full overflow-auto bg-[#f8f9fa] relative">
      <div className="bg-white p-4 border-b border-border flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-3">
            <div className="p-2 bg-red-50 rounded-lg"><ShieldAlert className="h-5 w-5 text-red-600" /></div>
            <div>
                <h2 className="text-lg font-bold text-gray-900">System Audit Logs</h2>
                <p className="text-xs text-gray-500">Immutable record of system activities.</p>
            </div>
        </div>
        <div className="relative w-72">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <input type="text" placeholder="Search logs..." className="w-full pl-9 pr-4 py-2 border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-[#1e3a8a]/20" value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} />
        </div>
      </div>

      <div className="p-6">
        <Card className="bg-white border-gray-200 shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
                <table className="w-full text-sm text-left">
                    <thead className="bg-gray-50 border-b border-gray-200 text-gray-500 uppercase text-xs font-bold">
                        <tr>
                            <th className="p-4">Timestamp</th>
                            <th className="p-4">User</th>
                            <th className="p-4">Action</th>
                            <th className="p-4">Entity</th>
                            <th className="p-4">Record ID</th>
                            <th className="p-4 text-center">Changes</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                        {isLoading ? (
                            <tr><td colSpan={6} className="p-8 text-center text-gray-400">Loading logs...</td></tr>
                        ) : filteredLogs.length === 0 ? (
                            <tr><td colSpan={6} className="p-8 text-center text-gray-400">No logs found.</td></tr>
                        ) : (
                            filteredLogs.map(log => (
                                <tr key={log.audit_id} className="hover:bg-gray-50/50">
                                    <td className="p-4 text-gray-500 whitespace-nowrap">{new Date(log.created_at).toLocaleString()}</td>
                                    <td className="p-4 font-medium text-gray-900">{log.user_name}</td>
                                    <td className="p-4">
                                        <span className={`px-2 py-1 rounded text-xs font-bold ${log.action_type.includes('DELETE') ? 'bg-red-50 text-red-600' : log.action_type.includes('CREATE') ? 'bg-green-50 text-green-600' : 'bg-blue-50 text-blue-600'}`}>
                                            {log.action_type}
                                        </span>
                                    </td>
                                    <td className="p-4 text-gray-600">{log.entity_name}</td>
                                    <td className="p-4 text-gray-500 font-mono text-xs">{log.record_id}</td>
                                    <td className="p-4 text-center">
                                        {(log.old_value || log.new_value) && (
                                            <Button variant="ghost" size="sm" onClick={() => setSelectedLog(log)} className="h-8 text-[#1e3a8a]">
                                                <Eye className="h-4 w-4 mr-1.5" /> View
                                            </Button>
                                        )}
                                    </td>
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>
        </Card>
      </div>

      {selectedLog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <Card className="w-full max-w-3xl bg-white shadow-xl overflow-hidden flex flex-col max-h-[85vh]">
            <div className="flex justify-between items-center p-5 border-b border-gray-200 bg-gray-50 shrink-0">
              <div>
                <h3 className="text-lg font-bold text-gray-900">Change Details</h3>
                <p className="text-sm text-gray-500">{selectedLog.action_type} on {selectedLog.entity_name} ({selectedLog.record_id})</p>
              </div>
              <Button variant="ghost" size="sm" onClick={() => setSelectedLog(null)}><X className="h-5 w-5" /></Button>
            </div>
            <div className="p-6 overflow-y-auto grid grid-cols-2 gap-6 bg-gray-100/50">
                <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden flex flex-col">
                    <div className="bg-red-50 border-b border-red-100 p-2.5 text-xs font-bold text-red-800 uppercase tracking-wider text-center shrink-0">Old Value (Before)</div>
                    <pre className="p-4 text-xs font-mono text-gray-600 overflow-x-auto m-0 flex-1">
                        {selectedLog.old_value ? JSON.stringify(selectedLog.old_value, null, 2) : "None / Created"}
                    </pre>
                </div>
                <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden flex flex-col">
                    <div className="bg-green-50 border-b border-green-100 p-2.5 text-xs font-bold text-green-800 uppercase tracking-wider text-center shrink-0">New Value (After)</div>
                    <pre className="p-4 text-xs font-mono text-gray-800 overflow-x-auto m-0 flex-1">
                        {selectedLog.new_value ? JSON.stringify(selectedLog.new_value, null, 2) : "None / Deleted"}
                    </pre>
                </div>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}