import { useState } from "react";
import { Card } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { Send, Sparkles, TrendingUp, DollarSign, AlertCircle, Shield } from "lucide-react";
import { StatusBadge } from "../components/shared/StatusBadge";
import { useAuth } from "../context/AuthContext";

const getSuggestedPrompts = (role?: string, assignedLabs?: string[]) => {
  if (role === "admin") {
    return [
      "Which labs are exceeding their budget?",
      "What is the total spending across all labs?",
      "Show me top spending categories",
      "How many records are pending review?",
    ];
  } else if (role === "teamlead") {
    return [
      "What is my team's total spending?",
      "Show budget status for my labs",
      "Which lab needs attention?",
      "How many PRs need my review?",
    ];
  } else if (role === "labic") {
    return [
      "What is my lab's budget utilization?",
      "Show spending by category for my lab",
      "Compare my lab to budget",
      "What is my lab's remaining budget?",
    ];
  }
  return [];
};

const getHardcodedResponse = (question: string, user: any) => {
  const normalizedQ = question.toLowerCase();

  // Admin responses
  if (user?.role === "admin") {
    if (normalizedQ.includes("exceed") || normalizedQ.includes("over budget")) {
      return {
        message: "I found **1 lab** currently exceeding their budget:\n\n**W3L1 - Food Pilot Plant**\n- Budget: $65,000\n- Actual Spend: $72,800\n- Utilization: 112%\n- Overage: $7,800\n\nThis lab exceeded the critical threshold (95%) on May 20, 2026. Email alerts have been sent to Team Lead Sarah Chen and Admin.",
        evidence: [
          { label: "Lab Code", value: "W3L1" },
          { label: "Utilization", value: "112%", status: "exceeded" },
          { label: "Overage", value: "$7,800" },
          { label: "Alert Sent", value: "Yes" },
        ],
      };
    } else if (normalizedQ.includes("total spending") || normalizedQ.includes("spending across")) {
      return {
        message: "**Total Spending Across All Labs**\n\nCurrent Period (YTD 2026):\n- Total Budget: $540,000\n- Actual Spend: $223,800\n- Overall Utilization: 41.4%\n- Remaining: $316,200\n\nBreakdown by Lab Group:\n• W3 - Food Processing: $98,500 (54.7%)\n• W4 - Materials Testing: $76,200 (50.8%)\n• W5 - Analytics: $42,100 (35.1%)\n• General: $7,000 (7.8%)",
        evidence: [
          { label: "Total Budget", value: "$540,000" },
          { label: "Actual Spend", value: "$223,800" },
          { label: "Utilization", value: "41.4%", status: "healthy" },
          { label: "Active Alerts", value: "3" },
        ],
      };
    } else if (normalizedQ.includes("top") && normalizedQ.includes("categor")) {
      return {
        message: "**Top Spending Categories**\n\n1. **Equipment** - $98,500 (44.0%)\n   Lab equipment, instruments, machinery\n\n2. **Supplies** - $67,200 (30.0%)\n   Consumables, chemicals, materials\n\n3. **Services** - $42,100 (18.8%)\n   External testing, calibration\n\n4. **Training** - $15,800 (7.1%)\n   Courses, workshops\n\n5. **Other** - $200 (0.1%)\n   Miscellaneous expenses",
        evidence: [
          { label: "Top Category", value: "Equipment" },
          { label: "Amount", value: "$98,500" },
          { label: "Percentage", value: "44.0%" },
        ],
      };
    } else if (normalizedQ.includes("pending") || normalizedQ.includes("review")) {
      return {
        message: "**Records Pending Review**\n\nCurrent Review Queue: **28 records**\n\nBreakdown:\n• Upload Batch UP-2024-153: 28 records\n• Flagged due to low confidence (<80%)\n• Awaiting Team Lead approval\n\nRecent Activity:\n- 14 records approved today\n- 2 records rejected\n- Average review time: 15 minutes",
        evidence: [
          { label: "Pending Review", value: "28 records" },
          { label: "Latest Batch", value: "UP-2024-153" },
          { label: "Status", value: "Awaiting approval", status: "pending" },
        ],
      };
    }
  }

  // Team Lead responses
  if (user?.role === "teamlead") {
    if (normalizedQ.includes("team") && normalizedQ.includes("spending")) {
      return {
        message: `**Your Team's Spending Summary**\n\nAssigned Labs: ${user.assignedLabs?.join(", ")}\n\nTotal Spending:\n- Combined Budget: $150,000\n- Actual Spend: $98,500\n- Utilization: 65.7%\n- Remaining: $51,500\n\nLab Breakdown:\n• W3L1: $72,800 (112%) ⚠️ Over budget\n• W3L2: $18,200 (40.4%)\n• W3L3: $7,500 (18.8%)`,
        evidence: [
          { label: "Team Budget", value: "$150,000" },
          { label: "Team Spending", value: "$98,500" },
          { label: "Utilization", value: "65.7%", status: "warning" },
        ],
      };
    } else if (normalizedQ.includes("budget status") || normalizedQ.includes("status for")) {
      return {
        message: `**Budget Status for Your Labs**\n\n**W3L1 - Food Pilot Plant**\n✗ Critical: 112% utilization ($7,800 over)\n\n**W3L2 - Food Chemistry**\n✓ Healthy: 40.4% utilization\n\n**W3L3 - Food Microbiology**\n✓ Healthy: 18.8% utilization\n\n**Recommendation:** Review W3L1 spending immediately. Consider reallocating from W3L2/W3L3 if needed.`,
        evidence: [
          { label: "Critical Labs", value: "1", status: "exceeded" },
          { label: "Healthy Labs", value: "2", status: "healthy" },
          { label: "Action Required", value: "W3L1" },
        ],
      };
    } else if (normalizedQ.includes("needs attention") || normalizedQ.includes("which lab")) {
      return {
        message: "**Lab Requiring Immediate Attention**\n\n**W3L1 - Food Pilot Plant**\n- Status: Critical (Over Budget)\n- Budget: $65,000\n- Actual: $72,800\n- Utilization: 112%\n- Over by: $7,800\n\n**Actions Taken:**\n✓ Alert sent to Team Lead and Admin\n✓ Email notification delivered\n✓ Flagged in dashboard\n\n**Next Steps:**\n1. Review recent PRs for W3L1\n2. Identify non-essential spending\n3. Consider budget reallocation",
        evidence: [
          { label: "Lab", value: "W3L1" },
          { label: "Status", value: "Critical", status: "exceeded" },
          { label: "Overage", value: "$7,800" },
        ],
      };
    } else if (normalizedQ.includes("how many") && normalizedQ.includes("review")) {
      return {
        message: "**PRs Awaiting Your Review**\n\nCurrent Queue: **28 records**\n\nBy Lab:\n• W3L1: 12 records\n• W3L2: 10 records\n• W3L3: 6 records\n\nClassification Confidence:\n• Low confidence (<50%): 8 records\n• Medium confidence (50-79%): 20 records\n\nOldest pending: 3 days\nAverage in queue: 1.5 days",
        evidence: [
          { label: "Total Pending", value: "28 records" },
          { label: "Oldest Item", value: "3 days ago" },
          { label: "Priority", value: "8 low confidence", status: "warning" },
        ],
      };
    }
  }

  // Lab IC responses
  if (user?.role === "labic") {
    const labCode = user.assignedLabs?.[0];
    if (normalizedQ.includes("utilization") || normalizedQ.includes("budget status")) {
      return {
        message: `**${labCode} Budget Utilization**\n\nLab: Food Pilot Plant (W3L1)\nLab IC: ${user.name}\n\n**Current Status:**\n- Budget: $65,000\n- Actual Spend: $72,800\n- Utilization: 112%\n- Over Budget: $7,800\n\n**Status:** 🚨 Critical - Exceeded Budget\n\n**Alert Triggered:** Critical threshold (95%) exceeded on May 20, 2026.\n\nYour lab has exceeded its annual budget. Please coordinate with Team Lead Sarah Chen for budget reallocation or spending review.`,
        evidence: [
          { label: "Your Lab", value: labCode },
          { label: "Utilization", value: "112%", status: "exceeded" },
          { label: "Overage", value: "$7,800" },
          { label: "Status", value: "Critical", status: "exceeded" },
        ],
      };
    } else if (normalizedQ.includes("category") || normalizedQ.includes("spending by")) {
      return {
        message: `**${labCode} Spending by Category**\n\n**Equipment** - $45,200 (62%)\nLab equipment, instruments, machinery\n\n**Supplies** - $18,500 (25%)\nConsumables, chemicals, materials\n\n**Services** - $7,100 (10%)\nExternal testing, calibration\n\n**Training** - $2,000 (3%)\nCourses and certifications\n\nTotal: $72,800`,
        evidence: [
          { label: "Top Category", value: "Equipment" },
          { label: "Amount", value: "$45,200" },
          { label: "Percentage", value: "62%" },
        ],
      };
    } else if (normalizedQ.includes("compare") || normalizedQ.includes("vs budget")) {
      return {
        message: `**${labCode} Budget Comparison**\n\n**Budget vs Actual:**\n- Annual Budget: $65,000\n- YTD Spending: $72,800\n- Variance: +$7,800 (112%)\n\n**Monthly Breakdown:**\n• Jan-Mar: $38,400 (on track)\n• Apr: $18,200 (spike detected)\n• May: $16,200 (continued high)\n\n**Recommendation:** Spending spiked in April. Review April PRs for unusual activity.`,
        evidence: [
          { label: "Budget", value: "$65,000" },
          { label: "Actual", value: "$72,800" },
          { label: "Variance", value: "+$7,800", status: "exceeded" },
        ],
      };
    } else if (normalizedQ.includes("remaining")) {
      return {
        message: `**${labCode} Remaining Budget**\n\n**Status:** Budget Exceeded\n\nYour lab has exceeded its annual budget allocation.\n\n- Annual Budget: $65,000\n- YTD Spending: $72,800\n- Over Budget: $7,800\n- Remaining: -$7,800\n\n**Action Required:**\nNo additional spending should occur without Team Lead approval. Contact Sarah Chen for budget review or reallocation from other labs.`,
        evidence: [
          { label: "Remaining", value: "-$7,800", status: "exceeded" },
          { label: "Status", value: "Over Budget" },
          { label: "Contact", value: "Sarah Chen (Team Lead)" },
        ],
      };
    }
  }

  // Default response
  return {
    message: "I can help you analyze budget data, spending patterns, and PR records. Try asking:\n\n• Budget utilization questions\n• Spending breakdowns\n• Lab comparisons\n• Alert status\n• Record counts\n\nOr select a suggested question from the sidebar.",
    evidence: [],
  };
};

const mockConversation = [
  {
    role: "assistant",
    message: "Hello. This is a frontend chatbot stub. It can show the intended UI, but it is not connected to authorised backend data yet.",
  },
];

export function ChatbotPage() {
  const { user } = useAuth();
  const [messages, setMessages] = useState(mockConversation);
  const [input, setInput] = useState("");
  const suggestedPrompts = getSuggestedPrompts(user?.role, user?.assignedLabs);

  const handleSend = () => {
    if (!input.trim()) return;

    // Add user message
    const userMessage = { role: "user", message: input };

    // Get hardcoded response based on question
    const aiResponse = {
      role: "assistant",
      ...getHardcodedResponse(input, user),
    };

    setMessages([...messages, userMessage, aiResponse]);
    setInput("");
  };

  return (
    <div className="h-full overflow-auto bg-[#f8f9fa]">
      <div className="p-6 h-full flex gap-6">
        {/* Chat Area */}
        <div className="flex-1 flex flex-col">
          <Card className="flex-1 bg-white border-border flex flex-col overflow-hidden">
            <div className="p-6 border-b border-border">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-full bg-gradient-to-br from-[#1e3a8a] to-[#3b82f6] flex items-center justify-center">
                  <Sparkles className="h-5 w-5 text-white" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-foreground">
                    Budget Chat Stub
                  </h2>
                  <p className="text-sm text-muted-foreground">
                    Ask questions about budgets, spending, and PR records
                  </p>
                </div>
              </div>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              {messages.map((msg, idx) => (
                <div
                  key={idx}
                  className={`flex ${
                    msg.role === "user" ? "justify-end" : "justify-start"
                  }`}
                >
                  <div
                    className={`max-w-[80%] rounded-lg p-4 ${
                      msg.role === "user"
                        ? "bg-[#1e3a8a] text-white"
                        : "bg-[#f8f9fa] text-foreground"
                    }`}
                  >
                    <p className="text-sm whitespace-pre-wrap">{msg.message}</p>
                    {msg.evidence && (
                      <div className="mt-3 pt-3 border-t border-border/20 space-y-2">
                        {msg.evidence.map((item: any, i: number) => (
                          <div key={i} className="flex items-center justify-between">
                            <span className="text-xs text-muted-foreground">
                              {item.label}:
                            </span>
                            {item.status ? (
                              <StatusBadge status={item.status}>
                                {item.value}
                              </StatusBadge>
                            ) : (
                              <span className="text-sm font-medium">
                                {item.value}
                              </span>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Input */}
            <div className="p-4 border-t border-border">
              <div className="flex gap-2">
                <Input
                  placeholder="Ask a question about budgets or PR records..."
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyPress={(e) => e.key === "Enter" && handleSend()}
                />
                <Button
                  className="bg-[#1e3a8a] hover:bg-[#1e40af] text-white"
                  onClick={handleSend}
                >
                  <Send className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </Card>
        </div>

        {/* Sidebar */}
        <div className="w-80 space-y-6">
          {/* Role Info */}
          {user?.role !== "admin" && (
            <Card className="p-4 bg-[#f0f9ff] border-[#bfdbfe]">
              <div className="flex items-start gap-3">
                <Shield className="h-5 w-5 text-[#2563eb] flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm text-[#1e40af] font-medium">
                    {user?.role === "labic" ? "Lab IC Access" : "Team Lead Access"}
                  </p>
                  <p className="text-xs text-[#1e3a8a] mt-1">
                    AI responses are filtered to your assigned labs: {user?.assignedLabs?.join(", ")}
                  </p>
                </div>
              </div>
            </Card>
          )}

          {/* Suggested Prompts */}
          <Card className="p-6 bg-white border-border">
            <h3 className="text-lg font-semibold text-foreground mb-4">
              Suggested Questions
            </h3>
            <div className="space-y-2">
              {suggestedPrompts.map((prompt, idx) => (
                <button
                  key={idx}
                  onClick={() => setInput(prompt)}
                  className="w-full text-left p-3 text-sm bg-[#f8f9fa] hover:bg-[#e5e7eb] rounded-lg transition-colors text-foreground"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </Card>

          {/* Quick Insights */}
          <Card className="p-6 bg-white border-border">
            <h3 className="text-lg font-semibold text-foreground mb-4">
              Quick Insights
            </h3>
            <div className="space-y-4">
              <div className="flex items-start gap-3 p-3 bg-[#fef2f2] rounded-lg border border-[#fecaca]">
                <AlertCircle className="h-5 w-5 text-[#dc2626] mt-0.5 flex-shrink-0" />
                <div>
                  <p className="text-sm font-medium text-[#dc2626]">
                    1 Lab Over Budget
                  </p>
                  <p className="text-xs text-[#991b1b] mt-1">
                    W3L1 at 112% utilization
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-3 p-3 bg-[#f0f9ff] rounded-lg border border-[#bfdbfe]">
                <TrendingUp className="h-5 w-5 text-[#2563eb] mt-0.5 flex-shrink-0" />
                <div>
                  <p className="text-sm font-medium text-[#1e40af]">
                    Overall Utilization
                  </p>
                  <p className="text-xs text-[#1e3a8a] mt-1">
                    41.4% across all labs
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-3 p-3 bg-[#f0fdf4] rounded-lg border border-[#bbf7d0]">
                <DollarSign className="h-5 w-5 text-[#059669] mt-0.5 flex-shrink-0" />
                <div>
                  <p className="text-sm font-medium text-[#047857]">
                    Total Remaining
                  </p>
                  <p className="text-xs text-[#065f46] mt-1">
                    $316,200 available
                  </p>
                </div>
              </div>
            </div>
          </Card>

          {/* Capabilities */}
          <Card className="p-6 bg-white border-border">
            <h3 className="text-lg font-semibold text-foreground mb-4">
              What I Can Do
            </h3>
            <ul className="space-y-2 text-sm text-muted-foreground">
              <li className="flex items-start gap-2">
                <span className="text-[#1e3a8a] mt-0.5">•</span>
                <span>Analyze budget utilization {user?.role !== "admin" ? "for your labs" : "by lab or category"}</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-[#1e3a8a] mt-0.5">•</span>
                <span>Find PR records matching specific criteria</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-[#1e3a8a] mt-0.5">•</span>
                <span>Compare spending trends over time</span>
              </li>
              {user?.role !== "labic" && (
                <li className="flex items-start gap-2">
                  <span className="text-[#1e3a8a] mt-0.5">•</span>
                  <span>Identify budget alerts and threshold breaches</span>
                </li>
              )}
              <li className="flex items-start gap-2">
                <span className="text-[#1e3a8a] mt-0.5">•</span>
                <span>Provide {user?.role === "admin" ? "audit trail and change history" : "spending summaries and reports"}</span>
              </li>
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}
