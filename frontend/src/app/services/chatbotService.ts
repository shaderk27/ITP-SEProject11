const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

const FETCH_OPTS: RequestInit = { credentials: "include" };

export type ChatbotQueryType =
  | "budget_utilisation_summary"
  | "high_spending_areas"
  | "budget_risks"
  | "spending_trends"
  | "purchase_lookup";

interface ChatbotScope {
  role: string;
  lab_group_id: number | null;
  lab_id: number | null;
  scope_description: string;
}

interface ChatbotBudgetContext {
  lab_group_id: number;
  lab_group_name: string;
  lab_id: number;
  lab_name: string;
  category_id: number | null;
  category_name: string;
  budget_sgd: string;
  approved_spend_sgd: string;
  remaining_sgd: string;
  utilisation_pct: number;
}

interface ChatbotLabGroupBudgetContext {
  lab_group_id: number;
  lab_group_name: string;
  envelope_budget_sgd: string;
  allocated_to_labs_sgd: string;
  unallocated_sgd: string;
  approved_spend_sgd: string;
  utilisation_pct: number;
}

interface ChatbotPurchaseLineContext {
  pr_id: number;
  pr_line_id: number;
  source_pr_number: string;
  request_date: string | null;
  requestor_name: string;
  purpose: string;
  wbs_code: string;
  item_description: string;
  amount_gst: string;
  currency_code: string;
  lab_group_name: string;
  lab_name: string;
  category_name: string;
  pr_status: string | null;
}

interface ChatbotContextResponse {
  query_type: ChatbotQueryType;
  question: string | null;
  scope: ChatbotScope;
  data_sources: string[];
  supported_query_types: ChatbotQueryType[];
  lab_group_budget_context: ChatbotLabGroupBudgetContext[];
  budget_context: ChatbotBudgetContext[];
  purchase_lines: ChatbotPurchaseLineContext[];
  notes: string[];
}

export async function askBudgetAssistant(question: string): Promise<string> {
  const queryType = classifyQuestion(question);
  const response = await fetch(`${API_BASE_URL}/api/chatbot/query-context`, {
    ...FETCH_OPTS,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query_type: queryType,
      question,
      date_range: "all",
      limit: 12,
    }),
  });

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(detail || `Ask AI failed (${response.status}).`);
  }

  const context = (await response.json()) as ChatbotContextResponse;
  return formatAnswer(context);
}

function classifyQuestion(question: string): ChatbotQueryType {
  const q = question.toLowerCase();
  if (hasAny(q, ["risk", "risks", "exceed", "exceeded", "overspend", "close to", "attention", "recommend", "recommendation"])) {
    return "budget_risks";
  }
  if (hasAny(q, ["highest", "high spend", "high-spend", "top", "most", "spending categories", "spending labs"])) {
    return "high_spending_areas";
  }
  if (hasAny(q, ["trend", "trends", "recent", "over time", "changed", "monthly", "history"])) {
    return "spending_trends";
  }
  if (hasAny(q, ["purchase", "purchases", "pr ", "pr#", "wbs", "requestor", "item"])) {
    return "purchase_lookup";
  }
  return "budget_utilisation_summary";
}

function hasAny(value: string, needles: string[]): boolean {
  return needles.some((needle) => value.includes(needle));
}

function formatAnswer(context: ChatbotContextResponse): string {
  const scope = context.scope.scope_description;
  const lines = [`Scope: ${scope}`];

  if (
    context.lab_group_budget_context.length === 0 &&
    context.budget_context.length === 0 &&
    context.purchase_lines.length === 0
  ) {
    return [
      ...lines,
      "",
      "I could not find approved budget or purchase data for this question in your permitted scope.",
    ].join("\n");
  }

  switch (context.query_type) {
    case "high_spending_areas":
      return [...lines, "", ...formatHighSpending(context)].join("\n");
    case "budget_risks":
      return [...lines, "", ...formatRisks(context)].join("\n");
    case "spending_trends":
      return [...lines, "", ...formatTrends(context)].join("\n");
    case "purchase_lookup":
      return [...lines, "", ...formatPurchases(context.purchase_lines)].join("\n");
    case "budget_utilisation_summary":
    default:
      return [...lines, "", ...formatUtilisation(context)].join("\n");
  }
}

function formatUtilisation(context: ChatbotContextResponse): string[] {
  const lines = ["Budget utilisation summary:"];
  if (context.lab_group_budget_context.length > 0) {
    const groups = [...context.lab_group_budget_context].sort(
      (a, b) => b.utilisation_pct - a.utilisation_pct,
    );
    const totals = groups.reduce(
      (acc, row) => {
        acc.budget += money(row.envelope_budget_sgd);
        acc.spend += money(row.approved_spend_sgd);
        acc.remaining += money(row.unallocated_sgd);
        return acc;
      },
      { budget: 0, spend: 0, remaining: 0 },
    );
    lines.push(
      `Total envelope budget: ${formatSgd(totals.budget)}`,
      `Approved spend: ${formatSgd(totals.spend)}`,
      `Unallocated envelope balance: ${formatSgd(totals.remaining)}`,
      "",
      "Top lab groups by utilisation:",
      ...groups.slice(0, 5).map((row) =>
        `- ${row.lab_group_name}: ${formatPercent(row.utilisation_pct)} used (${formatSgd(money(row.approved_spend_sgd))} of ${formatSgd(money(row.envelope_budget_sgd))})`,
      ),
    );
    return lines;
  }

  const rows = [...context.budget_context].sort(
    (a, b) => b.utilisation_pct - a.utilisation_pct,
  );
  const totals = rows.reduce(
    (acc, row) => {
      acc.budget += money(row.budget_sgd);
      acc.spend += money(row.approved_spend_sgd);
      acc.remaining += money(row.remaining_sgd);
      return acc;
    },
    { budget: 0, spend: 0, remaining: 0 },
  );
  lines.push(
    `Total budget: ${formatSgd(totals.budget)}`,
    `Approved spend: ${formatSgd(totals.spend)}`,
    `Remaining budget: ${formatSgd(totals.remaining)}`,
    "",
    "Highest utilisation rows:",
    ...rows.slice(0, 5).map((row) =>
      `- ${row.lab_name} / ${row.category_name}: ${formatPercent(row.utilisation_pct)} used (${formatSgd(money(row.approved_spend_sgd))} of ${formatSgd(money(row.budget_sgd))})`,
    ),
  );
  return lines;
}

function formatHighSpending(context: ChatbotContextResponse): string[] {
  const rows = [...context.budget_context]
    .filter((row) => money(row.approved_spend_sgd) > 0)
    .sort((a, b) => money(b.approved_spend_sgd) - money(a.approved_spend_sgd));

  if (rows.length === 0) {
    return ["No approved spend was found in your permitted scope."];
  }

  return [
    "Highest approved spending areas:",
    ...rows.slice(0, 5).map((row, index) =>
      `${index + 1}. ${row.lab_name} / ${row.category_name}: ${formatSgd(money(row.approved_spend_sgd))} approved spend, ${formatPercent(row.utilisation_pct)} utilisation.`,
    ),
  ];
}

function formatRisks(context: ChatbotContextResponse): string[] {
  const riskRows = [...context.budget_context]
    .filter((row) => row.utilisation_pct >= 80 || money(row.remaining_sgd) < 0)
    .sort((a, b) => b.utilisation_pct - a.utilisation_pct);

  if (riskRows.length === 0) {
    return [
      "No budget rows are currently above 80% utilisation or below zero remaining budget in your permitted scope.",
      "Recommended next step: continue monitoring newly approved PRs against the dashboard and alert thresholds.",
    ];
  }

  return [
    "Budget risk areas:",
    ...riskRows.slice(0, 6).map((row) => {
      const remaining = money(row.remaining_sgd);
      const status = remaining < 0 ? "over budget" : "high utilisation";
      return `- ${row.lab_name} / ${row.category_name}: ${formatPercent(row.utilisation_pct)} used, ${formatSgd(remaining)} remaining (${status}).`;
    }),
    "",
    "Recommended next step: review the listed categories before approving additional PRs in the same scope.",
  ];
}

function formatTrends(context: ChatbotContextResponse): string[] {
  if (context.purchase_lines.length === 0) {
    return ["No approved purchase lines were found for trend context."];
  }

  const byMonth = new Map<string, number>();
  for (const line of context.purchase_lines) {
    const month = line.request_date?.slice(0, 7) ?? "No date";
    byMonth.set(month, (byMonth.get(month) ?? 0) + money(line.amount_gst));
  }

  const months = [...byMonth.entries()].sort(([a], [b]) => a.localeCompare(b));
  return [
    "Approved spending trend context:",
    ...months.slice(-6).map(([month, amount]) => `- ${month}: ${formatSgd(amount)}`),
    "",
    "Recent approved purchases used for this context:",
    ...formatPurchases(context.purchase_lines.slice(0, 5)),
  ];
}

function formatPurchases(purchaseLines: ChatbotPurchaseLineContext[]): string[] {
  if (purchaseLines.length === 0) {
    return ["No approved purchase lines were found in your permitted scope."];
  }

  return [
    "Approved purchase lines:",
    ...purchaseLines.slice(0, 8).map((line) => {
      const pr = line.source_pr_number || `PR ${line.pr_id}`;
      const wbs = line.wbs_code ? `, WBS ${line.wbs_code}` : "";
      const date = line.request_date ? `${line.request_date}, ` : "";
      return `- ${date}${pr}${wbs}: ${line.item_description || line.purpose || "No description"} (${line.lab_name} / ${line.category_name}) - ${formatSgd(money(line.amount_gst))}`;
    }),
  ];
}

function money(value: string): number {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatSgd(value: number): string {
  return new Intl.NumberFormat("en-SG", {
    style: "currency",
    currency: "SGD",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatPercent(value: number): string {
  return `${value.toFixed(1)}%`;
}

async function readErrorDetail(response: Response): Promise<string> {
  try {
    const body = await response.json();
    return typeof body?.detail === "string" ? body.detail : "";
  } catch {
    return "";
  }
}
