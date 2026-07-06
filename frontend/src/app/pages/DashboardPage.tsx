import {
  Fragment,
  useEffect,
  useMemo,
  useState,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from "react";
import {
  DollarSign,
  TrendingUp,
  Wallet,
  Percent,
  Clock,
  Activity,
  Filter,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { KPICard } from "../components/shared/KPICard";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../components/ui/dropdown-menu";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "../components/ui/popover";
import { Checkbox } from "../components/ui/checkbox";
import { FilterBar } from "../components/shared/FilterBar";
import { DatePickerField } from "../components/shared/DatePickerField";
import { RoleInfo } from "../components/shared/RoleInfo";
import { useAuth } from "../context/AuthContext";
import { format, subDays } from "date-fns";
import {
  getBreakdown,
  getMonthly,
  getSpendingSummary,
  listLabGroups,
  listPeriods,
  type MonthlyPoint,
  type Period,
} from "../services/dashboardService";
import type {
  BreakdownLabGroup,
  BreakdownResponse,
  LabGroupSummary,
  SpendingSummary,
} from "../types/dashboard";
import {
  BarChart,
  Bar,
  Cell,
  LabelList,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";

// Utilisation threshold colour: green <50%, amber <80%, orange <95%, red ≥95%.
function utilColor(pct: number): string {
  if (pct >= 95) return "#ef4444";
  if (pct >= 80) return "#f97316";
  if (pct >= 50) return "#f59e0b";
  return "#10b981";
}

// Max entities shown at once in a comparison chart.
const MAX_COMPARE = 5;

// Searchable selector: pick up to `max` entities to display in a comparison chart.
// Starts empty — the user checks what they want to see.
function EntityFilter({
  names,
  selected,
  onToggle,
  max,
}: {
  names: string[];
  selected: Set<string>;
  onToggle: (name: string) => void;
  max: number;
}) {
  const [query, setQuery] = useState("");
  if (names.length === 0) return null;
  const atMax = selected.size >= max;
  const filtered = names.filter((n) =>
    n.toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <div className="mb-3">
      <Popover>
        <PopoverTrigger asChild>
          <Button variant="outline" size="sm" className="gap-2">
            <Filter className="h-4 w-4" />
            Select ({selected.size}/{max})
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-64 p-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search…"
            className="w-full text-sm border border-border rounded-md px-2 py-1 mb-2"
          />
          <div className="max-h-60 overflow-y-auto space-y-1">
            {filtered.length === 0 ? (
              <p className="text-xs text-muted-foreground px-1 py-2">
                No matches.
              </p>
            ) : (
              filtered.map((n) => {
                const on = selected.has(n);
                const disabled = !on && atMax;
                return (
                  <label
                    key={n}
                    className={`flex items-center gap-2 text-sm px-1 py-0.5 rounded ${
                      disabled
                        ? "opacity-40 cursor-not-allowed"
                        : "cursor-pointer hover:bg-muted"
                    }`}
                  >
                    <Checkbox
                      checked={on}
                      disabled={disabled}
                      onCheckedChange={() => onToggle(n)}
                    />
                    <span className="truncate">{n}</span>
                  </label>
                );
              })
            )}
          </div>
          {atMax && (
            <p className="mt-2 text-xs text-muted-foreground">
              Max {max} selected — uncheck one to swap.
            </p>
          )}
        </PopoverContent>
      </Popover>
    </div>
  );
}

// Palette for the stacked category chart (cycles if there are more categories).
const CATEGORY_COLORS = [
  "#0d9488",
  "#3b82f6",
  "#f59e0b",
  "#8b5cf6",
  "#ef4444",
  "#10b981",
  "#ec4899",
  "#6b7280",
];

// Fiscal-year month order (Apr→Mar); value = calendar month number.
const FISCAL_MONTHS = [
  { value: 4, label: "April" },
  { value: 5, label: "May" },
  { value: 6, label: "June" },
  { value: 7, label: "July" },
  { value: 8, label: "August" },
  { value: 9, label: "September" },
  { value: 10, label: "October" },
  { value: 11, label: "November" },
  { value: 12, label: "December" },
  { value: 1, label: "January" },
  { value: 2, label: "February" },
  { value: 3, label: "March" },
];

// Toggleable dashboard charts (KPI cards always show). Order = display order.
const DASHBOARD_CHARTS = [
  { id: "utilisation", label: "Budget Utilisation" },
  { id: "actualVsBudget", label: "Actual vs Budget" },
  { id: "category", label: "Spending by Category" },
  { id: "monthly", label: "Monthly Spending Trend" },
  { id: "categoryMix", label: "Category Mix" },
  { id: "yoy", label: "Year-over-Year" },
] as const;

// Options offered in each slot's title dropdown.
const SLOT_OPTIONS = [...DASHBOARD_CHARTS];
const CHART_IDS = new Set<string>(DASHBOARD_CHARTS.map((c) => c.id));

// Default slot layout: 6 slots, each showing its original chart.
const DEFAULT_SLOTS = [
  "utilisation",
  "actualVsBudget",
  "category",
  "monthly",
  "categoryMix",
  "yoy",
];

// Load per-user slot layout from localStorage; default = DEFAULT_SLOTS.
// Any unknown/legacy value (e.g. an old "empty") falls back to that slot's default.
function loadSlots(key: string): string[] {
  try {
    const raw = localStorage.getItem(key);
    if (raw) {
      const parsed = JSON.parse(raw) as string[];
      if (Array.isArray(parsed) && parsed.length === DEFAULT_SLOTS.length)
        return parsed.map((s, i) => (CHART_IDS.has(s) ? s : DEFAULT_SLOTS[i]));
    }
  } catch {
    /* ignore malformed storage */
  }
  return [...DEFAULT_SLOTS];
}

export function DashboardPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [labGroups, setLabGroups] = useState<LabGroupSummary[]>([]);
  const [spending, setSpending] = useState<SpendingSummary | null>(null);
  const [breakdown, setBreakdown] = useState<BreakdownResponse | null>(null);
  // For Admin defaults to "all"; for Team Lead we auto-set to their lab_group
  // once it's known (see effect below).
  const [selectedGroupId, setSelectedGroupId] = useState<string>(() =>
    user?.labGroupId ? String(user.labGroupId) : "all",
  );
  // Fiscal year is the master time scope: it sets the budget year AND the base
  // spend window (Apr–Mar). The Date Range presets + custom range narrow within.
  const [periods, setPeriods] = useState<Period[]>([]);
  const [selectedFYPeriodId, setSelectedFYPeriodId] = useState<number | null>(null);
  // Date Range dropdown: all (whole FY) / 7d / 30d / 90d — a sub-window on spend.
  const [dateRange, setDateRange] = useState("all");
  // Custom date range (overrides the preset when either is set).
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const customActive = Boolean(startDate || endDate);
  // Optional single-lab focus within the selected group ("all" = whole group).
  const [selectedLabId, setSelectedLabId] = useState("all");
  // Per-chart "View by": compare lab groups or individual labs.
  const [utilViewBy, setUtilViewBy] = useState<"group" | "lab">("group");
  const [avbViewBy, setAvbViewBy] = useState<"group" | "lab">("group");
  const [stackViewBy, setStackViewBy] = useState<"group" | "lab">("group");
  // Per-chart entity include/exclude (by name) for the comparison bar charts.
  const [utilShown, setUtilShown] = useState<Set<string>>(new Set());
  const [avbShown, setAvbShown] = useState<Set<string>>(new Set());
  // Toggle an entity in/out of a chart's shown set, capped at MAX_COMPARE.
  const toggleShown =
    (setter: Dispatch<SetStateAction<Set<string>>>) => (name: string) =>
      setter((prev) => {
        const next = new Set(prev);
        if (next.has(name)) next.delete(name);
        else if (next.size < MAX_COMPARE) next.add(name);
        return next;
      });
  const [loadError, setLoadError] = useState<string | null>(null);
  // Track which lab_group / lab rows are expanded in the drilldown table.
  const [expandedGroups, setExpandedGroups] = useState<Set<number>>(new Set());
  const [expandedLabs, setExpandedLabs] = useState<Set<number>>(new Set());
  // Same-month Year-over-Year comparison: chosen fiscal month (calendar 1–12)
  // and which fiscal years to compare; the bars are computed by the effect below.
  const [yoyMonth, setYoyMonth] = useState(3); // default March
  const [yoyYearIds, setYoyYearIds] = useState<Set<number>>(new Set());
  const [yoyData, setYoyData] = useState<
    { name: string; amount: number; label: string }[]
  >([]);
  const toggleYoyYear = (id: number) =>
    setYoyYearIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  // Per-slot chart choice, persisted per user in localStorage. Reloaded on the
  // render-time key guard so switching users swaps in their saved layout.
  const slotsStorageKey = `dashboard_slots_v1:${user?.id ?? "anon"}`;
  const [slots, setSlots] = useState<string[]>(() => loadSlots(slotsStorageKey));
  const [prevSlotsKey, setPrevSlotsKey] = useState(slotsStorageKey);
  if (slotsStorageKey !== prevSlotsKey) {
    setPrevSlotsKey(slotsStorageKey);
    setSlots(loadSlots(slotsStorageKey));
  }
  const setSlot = (index: number, chartId: string) =>
    setSlots((prev) => prev.map((s, i) => (i === index ? chartId : s)));
  const resetSlots = () => setSlots([...DEFAULT_SLOTS]);

  // Auto-lock the dropdown to the Team Lead's own lab group whenever the user
  // changes (e.g. login/logout switching identities). Admins keep "all".
  // Done during render with a previous-value guard (React's "adjust state when
  // a prop changes" pattern) instead of an effect, which would fire an extra
  // cascading render on every identity change.
  const userKey = `${user?.role ?? ""}:${user?.labGroupId ?? ""}:${user?.labId ?? ""}`;
  const [prevUserKey, setPrevUserKey] = useState<string | null>(null);
  if (userKey !== prevUserKey) {
    setPrevUserKey(userKey);
    if (user?.role === "teamlead" && user.labGroupId) {
      setSelectedGroupId(String(user.labGroupId));
    } else if (user?.role === "admin") {
      setSelectedGroupId("all");
    } else if (user?.role === "labic" && user.labId) {
      // Lab IC is locked to their single assigned lab.
      setSelectedLabId(String(user.labId));
    }
  }

  // Load fiscal years once; default to the newest (current FY).
  useEffect(() => {
    let cancelled = false;
    listPeriods()
      .then((data) => {
        if (!cancelled) {
          setPeriods(data);
          if (data.length) setSelectedFYPeriodId(data[0].id);
          // Default the YoY comparison to the two most recent fiscal years.
          setYoyYearIds(new Set(data.slice(0, 2).map((p) => p.id)));
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  // Same-month Year-over-Year bars: for each selected fiscal year, fetch that
  // year's monthly spend (scoped to the current lab group / lab) and pull the
  // chosen fiscal month's bucket. Independent of the global FY selector.
  useEffect(() => {
    let cancelled = false;
    const gid = selectedGroupId !== "all" ? Number(selectedGroupId) : undefined;
    const lid = selectedLabId !== "all" ? Number(selectedLabId) : undefined;
    // Empty selection falls through: Promise.all([]) resolves to [] async,
    // avoiding a synchronous setState in the effect.
    const chosen = periods.filter((p) => yoyYearIds.has(p.id));
    Promise.all(
      chosen.map((p) =>
        getMonthly(p.start_date, p.end_date, gid, lid).then((pts) => {
          // Fiscal Apr–Dec sit in the FY's start year; Jan–Mar roll into +1.
          const startYear = Number(p.start_date.slice(0, 4));
          const calYear = yoyMonth >= 4 ? startYear : startYear + 1;
          const key = `${calYear}-${String(yoyMonth).padStart(2, "0")}`;
          const found = pts.find((x) => x.month === key);
          return { name: p.name, amount: found ? Number(found.amount) : 0 };
        }),
      ),
    )
      .then((rows) => {
        if (cancelled) return;
        rows.sort((a, b) => a.name.localeCompare(b.name)); // oldest → newest
        // Bar label = value + % change vs the previous selected year.
        const labelled = rows.map((r, i) => {
          const prev = rows[i - 1];
          let label = `$${r.amount.toLocaleString()}`;
          if (prev && prev.amount > 0) {
            const pct = ((r.amount - prev.amount) / prev.amount) * 100;
            const arrow = pct > 0 ? "▲" : pct < 0 ? "▼" : "";
            label += `  ${arrow}${Math.abs(pct).toFixed(0)}%`;
          } else if (prev && r.amount > 0) {
            label += "  (new)";
          }
          return { ...r, label };
        });
        setYoyData(labelled);
      })
      .catch(() => {
        if (!cancelled) setYoyData([]);
      });
    return () => {
      cancelled = true;
    };
  }, [yoyMonth, yoyYearIds, selectedGroupId, selectedLabId, periods]);

  // Persist the slot layout whenever it changes.
  useEffect(() => {
    try {
      localStorage.setItem(slotsStorageKey, JSON.stringify(slots));
    } catch {
      /* ignore */
    }
  }, [slotsStorageKey, slots]);

  // Effective spend window: the selected FY's span, narrowed by a preset/custom.
  const [effStart, effEnd] = useMemo(() => {
    const period = periods.find((p) => p.id === selectedFYPeriodId);
    const fyStart = period?.start_date ?? "";
    const fyEnd = period?.end_date ?? "";
    let rawStart = "";
    let rawEnd = "";
    if (startDate || endDate) {
      rawStart = startDate;
      rawEnd = endDate;
    } else if (dateRange === "7d" || dateRange === "30d" || dateRange === "90d") {
      const days = dateRange === "7d" ? 7 : dateRange === "30d" ? 30 : 90;
      rawStart = format(subDays(new Date(), days), "yyyy-MM-dd");
      rawEnd = format(new Date(), "yyyy-MM-dd");
    }
    // Clamp the sub-window to the FY span (ISO dates sort lexicographically).
    const s = !rawStart ? fyStart : rawStart > fyStart ? rawStart : fyStart;
    const e = !rawEnd ? fyEnd : rawEnd < fyEnd ? rawEnd : fyEnd;
    return [s, e] as const;
  }, [periods, selectedFYPeriodId, dateRange, startDate, endDate]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      listLabGroups(selectedFYPeriodId),
      getSpendingSummary("all", effStart, effEnd),
      getBreakdown("all", effStart, effEnd, selectedFYPeriodId),
    ])
      .then(([groups, spendingSummary, breakdownResp]) => {
        if (!cancelled) {
          setLabGroups(groups);
          setSpending(spendingSummary);
          setBreakdown(breakdownResp);
          setLoadError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setLoadError(err instanceof Error ? err.message : "Failed to load dashboard data.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [selectedFYPeriodId, effStart, effEnd]);

  // Monthly trend — its own fetch so the client-side group/lab filter re-scopes
  // it without re-loading the whole dashboard.
  const [monthlyPoints, setMonthlyPoints] = useState<MonthlyPoint[]>([]);
  useEffect(() => {
    let cancelled = false;
    const gid = selectedGroupId !== "all" ? Number(selectedGroupId) : undefined;
    const lid = selectedLabId !== "all" ? Number(selectedLabId) : undefined;
    getMonthly(effStart, effEnd, gid, lid)
      .then((pts) => {
        if (!cancelled) setMonthlyPoints(pts);
      })
      .catch(() => {
        if (!cancelled) setMonthlyPoints([]);
      });
    return () => {
      cancelled = true;
    };
  }, [effStart, effEnd, selectedGroupId, selectedLabId]);

  // When a single lab is picked, the cards read from that lab's breakdown row
  // instead of the group-level numbers below.
  const selectedLab = useMemo(() => {
    if (selectedLabId === "all" || !breakdown) return null;
    for (const g of breakdown.lab_groups) {
      const lab = g.labs.find((l) => String(l.lab_id) === selectedLabId);
      if (lab) return lab;
    }
    return null;
  }, [breakdown, selectedLabId]);

  // Total Budget = raw System Config number, scoped by the Lab Group dropdown.
  // Always shows the full configured budget (not adjusted for spend/pending).
  const totalBudget = useMemo(() => {
    if (selectedLab) return Number(selectedLab.budget_sgd) || 0;
    if (selectedGroupId === "all") {
      return labGroups.reduce((sum, g) => sum + g.budget, 0);
    }
    const match = labGroups.find((g) => String(g.id) === selectedGroupId);
    return match ? match.budget : 0;
  }, [labGroups, selectedGroupId, selectedLab]);

  // Actual Spend = sum of Approved lines only. Backend role-filters; Team
  // Lead only ever gets their own group's numbers.
  const actualSpend = useMemo(() => {
    if (selectedLab) return Number(selectedLab.actual_spend_sgd) || 0;
    if (!spending) return 0;
    if (selectedGroupId === "all") {
      return Number(spending.total_actual_spend_sgd) || 0;
    }
    const raw = spending.by_lab_group[selectedGroupId];
    return raw ? Number(raw) || 0 : 0;
  }, [spending, selectedGroupId, selectedLab]);

  // Pending = committed but not yet approved. Only used to reduce Available
  // Balance; doesn't affect Total Budget or Utilisation %.
  const pendingSpend = useMemo(() => {
    if (selectedLab) return Number(selectedLab.pending_sgd) || 0;
    if (!spending) return 0;
    if (selectedGroupId === "all") {
      return Number(spending.total_pending_sgd) || 0;
    }
    const raw = spending.pending_by_lab_group[selectedGroupId];
    return raw ? Number(raw) || 0 : 0;
  }, [spending, selectedGroupId, selectedLab]);

  // Available = Total Budget - Approved - Pending.
  // Utilisation        = Approved / Total Budget (already-spent share).
  // Projected Util     = (Approved + Pending) / Total Budget (worst-case share
  //                      if every pending line gets approved). Useful as a
  //                      proactive "you're about to run out" indicator.
  const availableBalance = totalBudget - actualSpend - pendingSpend;
  const utilizationPct = totalBudget > 0 ? (actualSpend / totalBudget) * 100 : 0;
  const projectedUtilizationPct =
    totalBudget > 0 ? ((actualSpend + pendingSpend) / totalBudget) * 100 : 0;

  // Drilldown rows respect the Lab Group dropdown filter so the table mirrors
  // whatever scope the KPI cards above are showing.
  const filteredBreakdown: BreakdownLabGroup[] = useMemo(() => {
    if (!breakdown) return [];
    if (selectedGroupId === "all") return breakdown.lab_groups;
    return breakdown.lab_groups.filter(
      (g) => String(g.lab_group_id) === selectedGroupId,
    );
  }, [breakdown, selectedGroupId]);

  // Lab dropdown options: every lab in the visible groups (+ "All labs").
  const labOptions = useMemo(() => {
    const seen = new Map<number, string>();
    for (const g of filteredBreakdown) {
      for (const l of g.labs) seen.set(l.lab_id, l.lab_name);
    }
    return [
      { value: "all", label: "All labs" },
      ...Array.from(seen, ([id, name]) => ({ value: String(id), label: name })),
    ];
  }, [filteredBreakdown]);

  // When a lab is focused, narrow the drilldown + category chart to it. The
  // group header row is rewritten to mirror the single lab's totals.
  const scopedBreakdown: BreakdownLabGroup[] = useMemo(() => {
    if (selectedLabId === "all") return filteredBreakdown;
    const out: BreakdownLabGroup[] = [];
    for (const g of filteredBreakdown) {
      const lab = g.labs.find((l) => String(l.lab_id) === selectedLabId);
      if (!lab) continue;
      out.push({
        ...g,
        budget_sgd: lab.budget_sgd,
        actual_spend_sgd: lab.actual_spend_sgd,
        pending_sgd: lab.pending_sgd,
        available_balance_sgd: lab.available_balance_sgd,
        utilisation_pct: lab.utilisation_pct,
        projected_utilisation_pct: lab.projected_utilisation_pct,
        labs: [lab],
      });
    }
    return out;
  }, [filteredBreakdown, selectedLabId]);

  // Spending by Category chart: approved spend summed per category_name across
  // the visible lab groups. Every category present in the breakdown is kept
  // (configured-but-unspent categories show as a $0 bar), sorted biggest-first.
  const categoryData = useMemo(() => {
    const totals = new Map<string, number>();
    for (const group of scopedBreakdown) {
      for (const lab of group.labs) {
        for (const cat of lab.categories) {
          totals.set(
            cat.category_name,
            (totals.get(cat.category_name) ?? 0) + Number(cat.actual_spend_sgd),
          );
        }
      }
    }
    return Array.from(totals, ([category, amount]) => ({ category, amount })).sort(
      (a, b) => b.amount - a.amount,
    );
  }, [scopedBreakdown]);

  // Series for the two bar charts, at both lab-group and lab granularity so a
  // per-chart "View by" toggle can compare either.
  const utilData = useMemo(
    () => ({
      group: scopedBreakdown.map((g) => ({
        name: g.lab_group_name,
        util: g.utilisation_pct,
      })),
      lab: scopedBreakdown.flatMap((g) =>
        g.labs.map((l) => ({ name: l.lab_name, util: l.utilisation_pct })),
      ),
    }),
    [scopedBreakdown],
  );
  const avbData = useMemo(
    () => ({
      group: scopedBreakdown.map((g) => ({
        name: g.lab_group_name,
        budget: Number(g.budget_sgd),
        actual: Number(g.actual_spend_sgd),
      })),
      lab: scopedBreakdown.flatMap((g) =>
        g.labs.map((l) => ({
          name: l.lab_name,
          budget: Number(l.budget_sgd),
          actual: Number(l.actual_spend_sgd),
        })),
      ),
    }),
    [scopedBreakdown],
  );

  // Stacked category chart: each lab group (or lab) is one bar, stacked by
  // approved spend per category. Returns rows keyed by category name + the
  // full list of categories present (one <Bar> per category).
  const stackedCategory = useMemo(() => {
    const categories = new Set<string>();
    const rowFor = (name: string, cats: { category_name: string; actual_spend_sgd: string }[][]) => {
      const row: Record<string, number | string> = { name };
      for (const catList of cats) {
        for (const cat of catList) {
          categories.add(cat.category_name);
          row[cat.category_name] =
            (Number(row[cat.category_name]) || 0) + Number(cat.actual_spend_sgd);
        }
      }
      return row;
    };
    const group = scopedBreakdown.map((g) =>
      rowFor(
        g.lab_group_name,
        g.labs.map((l) => l.categories),
      ),
    );
    const lab = scopedBreakdown.flatMap((g) =>
      g.labs.map((l) => rowFor(l.lab_name, [l.categories])),
    );
    return { group, lab, categories: Array.from(categories) };
  }, [scopedBreakdown]);

  // Monthly Spend Trend: for a specific FY, pad to all 12 Apr–Mar buckets
  // (missing months = 0). For "All time", show every month that has spend.
  const monthlyData = useMemo(() => {
    const map = new Map(monthlyPoints.map((p) => [p.month, Number(p.amount)]));
    const period = periods.find((p) => p.id === selectedFYPeriodId);
    if (period) {
      const [y, m] = period.start_date.split("-").map(Number);
      return Array.from({ length: 12 }, (_, i) => {
        const d = new Date(y, m - 1 + i, 1);
        return { month: format(d, "MMM"), amount: map.get(format(d, "yyyy-MM")) ?? 0 };
      });
    }
    return [...monthlyPoints]
      .sort((a, b) => a.month.localeCompare(b.month))
      .map((p) => {
        const [y, m] = p.month.split("-").map(Number);
        return {
          month: format(new Date(y, m - 1, 1), "MMM yy"),
          amount: Number(p.amount),
        };
      });
  }, [monthlyPoints, periods, selectedFYPeriodId]);

  const toggleGroup = (id: number) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleLab = (id: number) => {
    setExpandedLabs((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // "All Lab Groups" only makes sense for users who can see more than one
  // (Admin). Team Lead is locked to their own group, so we omit it.
  const labGroupOptions = [
    ...(isAdmin ? [{ value: "all", label: "All Lab Groups" }] : []),
    ...labGroups.map((g) => ({ value: String(g.id), label: g.name })),
  ];

  // Comparison-chart series: the full entity list (for the chips) and the
  // subset actually plotted (chips deselected → excluded).
  const utilAll = utilViewBy === "lab" ? utilData.lab : utilData.group;
  const avbAll = avbViewBy === "lab" ? avbData.lab : avbData.group;
  // Seed each chart's selection when its entity list changes: ≤ MAX_COMPARE
  // auto-shows all; more than that starts empty so the user picks up to the cap.
  const utilNames = utilAll.map((d) => d.name).join("|");
  const [prevUtilNames, setPrevUtilNames] = useState(utilNames);
  if (utilNames !== prevUtilNames) {
    setPrevUtilNames(utilNames);
    setUtilShown(
      utilAll.length <= MAX_COMPARE
        ? new Set(utilAll.map((d) => d.name))
        : new Set(),
    );
  }
  const avbNames = avbAll.map((d) => d.name).join("|");
  const [prevAvbNames, setPrevAvbNames] = useState(avbNames);
  if (avbNames !== prevAvbNames) {
    setPrevAvbNames(avbNames);
    setAvbShown(
      avbAll.length <= MAX_COMPARE
        ? new Set(avbAll.map((d) => d.name))
        : new Set(),
    );
  }
  const utilVisible = utilAll.filter((d) => utilShown.has(d.name));
  const avbVisible = avbAll.filter((d) => avbShown.has(d.name));

  // Render the body (chart-specific controls + chart) for a given chart id.
  // Any slot can render any chart, so this lives in one place.
  function renderChartBody(chartId: string): ReactNode {
    switch (chartId) {
      case "utilisation":
        return (
          <>
            <div className="flex justify-end mb-3">
              <select
                value={utilViewBy}
                onChange={(e) =>
                  setUtilViewBy(e.target.value as "group" | "lab")
                }
                className="text-sm border border-border rounded-md px-2 py-1 bg-white shrink-0"
              >
                <option value="group">By Lab Group</option>
                <option value="lab">By Lab</option>
              </select>
            </div>
            <EntityFilter
              names={utilAll.map((d) => d.name)}
              selected={utilShown}
              onToggle={toggleShown(setUtilShown)}
              max={MAX_COMPARE}
            />
            {utilVisible.length === 0 ? (
              <div className="h-[300px] flex items-center justify-center text-sm text-muted-foreground">
                Use the Select button above to choose up to {MAX_COMPARE} to
                display.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={utilVisible} barCategoryGap="25%">
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis dataKey="name" stroke="#6b7280" />
                  <YAxis stroke="#6b7280" domain={[0, 100]} unit="%" />
                  <Tooltip formatter={(v: number) => `${v}%`} />
                  <ReferenceLine
                    y={50}
                    stroke="#f59e0b"
                    strokeDasharray="4 4"
                    label={{ value: "50%", position: "right", fill: "#d97706", fontSize: 11 }}
                  />
                  <ReferenceLine
                    y={80}
                    stroke="#f97316"
                    strokeDasharray="4 4"
                    label={{ value: "80%", position: "right", fill: "#ea580c", fontSize: 11 }}
                  />
                  <ReferenceLine
                    y={95}
                    stroke="#ef4444"
                    strokeDasharray="4 4"
                    label={{ value: "95%", position: "right", fill: "#dc2626", fontSize: 11 }}
                  />
                  <Bar dataKey="util" name="Utilisation %" radius={[4, 4, 0, 0]}>
                    {utilVisible.map((d, i) => (
                      <Cell key={i} fill={utilColor(d.util)} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </>
        );
      case "actualVsBudget":
        return (
          <>
            <div className="flex justify-end mb-3">
              <select
                value={avbViewBy}
                onChange={(e) => setAvbViewBy(e.target.value as "group" | "lab")}
                className="text-sm border border-border rounded-md px-2 py-1 bg-white shrink-0"
              >
                <option value="group">By Lab Group</option>
                <option value="lab">By Lab</option>
              </select>
            </div>
            <EntityFilter
              names={avbAll.map((d) => d.name)}
              selected={avbShown}
              onToggle={toggleShown(setAvbShown)}
              max={MAX_COMPARE}
            />
            {avbVisible.length === 0 ? (
              <div className="h-[300px] flex items-center justify-center text-sm text-muted-foreground">
                Use the Select button above to choose up to {MAX_COMPARE} to
                display.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={avbVisible} barGap={8} barCategoryGap="20%">
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis dataKey="name" stroke="#6b7280" />
                  <YAxis stroke="#6b7280" />
                  <Tooltip formatter={(v: number) => `$${Number(v).toLocaleString()}`} />
                  <Legend />
                  <Bar dataKey="budget" fill="#1e3a8a" name="Budget" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="actual" fill="#3b82f6" name="Actual" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </>
        );
      case "category":
        return (
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={categoryData} layout="vertical" barCategoryGap="20%">
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis type="number" stroke="#6b7280" />
              <YAxis
                dataKey="category"
                type="category"
                stroke="#6b7280"
                width={100}
              />
              <Tooltip />
              <Bar dataKey="amount" fill="#0d9488" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        );
      case "monthly":
        return (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={monthlyData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="month" stroke="#6b7280" />
              <YAxis stroke="#6b7280" />
              <Tooltip
                formatter={(v: number) => `$${Number(v).toLocaleString()}`}
              />
              <Line
                type="monotone"
                dataKey="amount"
                stroke="#3b82f6"
                strokeWidth={2}
                name="Actual spend"
                dot
              />
            </LineChart>
          </ResponsiveContainer>
        );
      case "categoryMix":
        return (
          <>
            <div className="flex justify-end mb-3">
              <select
                value={stackViewBy}
                onChange={(e) =>
                  setStackViewBy(e.target.value as "group" | "lab")
                }
                className="text-sm border border-border rounded-md px-2 py-1 bg-white shrink-0"
              >
                <option value="group">By Lab Group</option>
                <option value="lab">By Lab</option>
              </select>
            </div>
            <ResponsiveContainer width="100%" height={320}>
              <BarChart
                data={stackViewBy === "lab" ? stackedCategory.lab : stackedCategory.group}
                barCategoryGap="20%"
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="name" stroke="#6b7280" />
                <YAxis stroke="#6b7280" />
                <Tooltip formatter={(v: number) => `$${Number(v).toLocaleString()}`} />
                <Legend />
                {stackedCategory.categories.map((cat, i) => (
                  <Bar
                    key={cat}
                    dataKey={cat}
                    stackId="spend"
                    fill={CATEGORY_COLORS[i % CATEGORY_COLORS.length]}
                    name={cat}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </>
        );
      case "yoy":
        return (
          <>
            <div className="flex flex-wrap items-center justify-end mb-3 gap-2">
              <label className="text-sm text-muted-foreground">Month</label>
              <select
                value={yoyMonth}
                onChange={(e) => setYoyMonth(Number(e.target.value))}
                className="text-sm border border-border rounded-md px-2 py-1 bg-white"
              >
                {FISCAL_MONTHS.map((m) => (
                  <option key={m.value} value={m.value}>
                    {m.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-wrap gap-1.5 mb-3">
              {periods.map((p) => {
                const on = yoyYearIds.has(p.id);
                return (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => toggleYoyYear(p.id)}
                    className={`text-xs px-2 py-0.5 rounded-full border transition-colors ${
                      on
                        ? "bg-[#1e3a8a]/10 text-[#1e3a8a] border-[#1e3a8a]/30"
                        : "bg-white text-muted-foreground border-border opacity-60"
                    }`}
                  >
                    {p.name}
                  </button>
                );
              })}
            </div>
            {yoyData.length === 0 ? (
              <div className="h-[300px] flex items-center justify-center text-sm text-muted-foreground">
                Pick at least one fiscal year to compare.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={yoyData} barCategoryGap="30%" margin={{ top: 24 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis dataKey="name" stroke="#6b7280" />
                  <YAxis stroke="#6b7280" />
                  <Tooltip
                    formatter={(v: number) => `$${Number(v).toLocaleString()}`}
                  />
                  <Bar dataKey="amount" name="Approved spend" radius={[4, 4, 0, 0]}>
                    {yoyData.map((_, i) => (
                      <Cell
                        key={i}
                        fill={CATEGORY_COLORS[i % CATEGORY_COLORS.length]}
                      />
                    ))}
                    <LabelList
                      dataKey="label"
                      position="top"
                      fontSize={12}
                      fill="#374151"
                    />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </>
        );
      default:
        return (
          <div className="h-[300px] flex items-center justify-center text-sm text-muted-foreground">
            No chart selected.
          </div>
        );
    }
  }

  // One dashboard slot: a card whose clickable title picks which chart it shows.
  function renderSlot(index: number) {
    const chartId = slots[index] ?? DASHBOARD_CHARTS[0].id;
    const current = SLOT_OPTIONS.find((o) => o.id === chartId);
    return (
      <Card key={index} className="p-6 bg-white border-border">
        <div className="mb-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                className="inline-flex items-center gap-1 text-lg font-semibold text-foreground hover:text-blue-700"
              >
                {current?.label ?? "Select chart"}
                <ChevronDown className="h-4 w-4" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              {SLOT_OPTIONS.map((o) => (
                <DropdownMenuItem key={o.id} onClick={() => setSlot(index, o.id)}>
                  {o.label}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        {renderChartBody(chartId)}
      </Card>
    );
  }

  return (
    <div className="h-full overflow-auto bg-[#f8f9fa]">
      {/* Filters */}
      <FilterBar
        searchPlaceholder="Search dashboard..."
        onFilterChange={(filterId, value) => {
          if (filterId === "Fiscal Year")
            setSelectedFYPeriodId(value === "all" ? 0 : Number(value));
          if (filterId === "Lab Group") {
            setSelectedGroupId(value);
            // Lab list depends on the group, so reset the lab focus.
            setSelectedLabId("all");
          }
          if (filterId === "Lab") setSelectedLabId(value);
          if (filterId === "Date Range") {
            // Picking a preset clears any custom range so the preset applies.
            setDateRange(value);
            setStartDate("");
            setEndDate("");
          }
        }}
        filters={[
          {
            label: "Fiscal Year",
            value:
              selectedFYPeriodId == null
                ? ""
                : selectedFYPeriodId === 0
                  ? "all"
                  : String(selectedFYPeriodId),
            options: [
              { value: "all", label: "All time" },
              ...periods.map((p) => ({ value: String(p.id), label: p.name })),
            ],
          },
          {
            label: "Date Range",
            value: dateRange,
            options: [
              { value: "all", label: "Whole year" },
              { value: "7d", label: "Last 7 days" },
              { value: "30d", label: "Last 30 days" },
              { value: "90d", label: "Last 90 days" },
            ],
          },
          {
            label: "Lab Group",
            value: selectedGroupId,
            options: labGroupOptions,
          },
          {
            label: "Lab",
            value: selectedLabId,
            options: labOptions,
          },
        ]}
      />

      {/* Custom date range — overrides the preset when set. */}
      <div className="flex items-center gap-3 px-4 py-3 bg-white border-b border-border text-sm">
        <span className="text-muted-foreground">Custom range:</span>
        <label className="flex items-center gap-1.5">
          <span className="text-muted-foreground">From</span>
          <DatePickerField
            value={startDate}
            maxDate={endDate || undefined}
            onChange={setStartDate}
          />
        </label>
        <label className="flex items-center gap-1.5">
          <span className="text-muted-foreground">To</span>
          <DatePickerField
            value={endDate}
            minDate={startDate || undefined}
            onChange={setEndDate}
          />
        </label>
        {customActive && (
          <>
            <span className="text-xs text-blue-600">
              Custom range active — preset ignored
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setStartDate("");
                setEndDate("");
              }}
            >
              Clear
            </Button>
          </>
        )}
      </div>

      <div className="p-6 space-y-6">
        {/* Role Info */}
        <RoleInfo />

        {loadError && (
          <Card className="p-4 bg-[#fef2f2] border-[#fecaca]">
            <p className="text-sm text-[#b91c1c]">{loadError}</p>
          </Card>
        )}

        {/* KPI Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-6 gap-6">
          <KPICard
            title="Total Budget"
            value={formatCurrency(totalBudget)}
            icon={DollarSign}
            status="info"
          />
          <KPICard
            title="Actual Spend"
            value={formatCurrency(actualSpend)}
            icon={TrendingUp}
            status="info"
          />
          <KPICard
            title="Pending Amount"
            value={formatCurrency(pendingSpend)}
            icon={Clock}
            status="info"
          />
          <KPICard
            title="Available Balance"
            value={formatCurrency(availableBalance)}
            icon={Wallet}
            status="info"
          />
          <KPICard
            title="Utilisation %"
            value={`${utilizationPct.toFixed(1)}%`}
            icon={Percent}
            status={utilizationPct >= 95 ? "error" : utilizationPct >= 80 ? "warning" : "info"}
          />
          <KPICard
            title="Projected Utilisation %"
            value={`${projectedUtilizationPct.toFixed(1)}%`}
            icon={Activity}
            status={
              projectedUtilizationPct >= 95
                ? "error"
                : projectedUtilizationPct >= 80
                  ? "warning"
                  : "info"
            }
          />
        </div>

        {/* Drilldown: Lab Group → Lab → Category (always shown) */}
        <Card className="p-6 bg-white border-border">
          <h3 className="text-lg font-semibold mb-4 text-foreground">
            Budget Breakdown
          </h3>
          {!breakdown ? (
            <p className="text-sm text-muted-foreground">Loading breakdown…</p>
          ) : scopedBreakdown.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No budget or spending data in this scope yet. Set budgets in System Config and commit a batch to see numbers here.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-[#f8f9fa]">
                  <tr className="border-b border-border">
                    <th className="text-left p-3 text-xs font-medium text-muted-foreground">Name</th>
                    <th className="text-right p-3 text-xs font-medium text-muted-foreground">Budget</th>
                    <th className="text-right p-3 text-xs font-medium text-muted-foreground">Actual Spend</th>
                    <th className="text-right p-3 text-xs font-medium text-muted-foreground">Pending</th>
                    <th className="text-right p-3 text-xs font-medium text-muted-foreground">Available</th>
                    <th className="text-right p-3 text-xs font-medium text-muted-foreground">Util %</th>
                    <th className="text-right p-3 text-xs font-medium text-muted-foreground">Proj %</th>
                  </tr>
                </thead>
                <tbody>
                  {scopedBreakdown.map((group) => {
                    const groupOpen = expandedGroups.has(group.lab_group_id);
                    return (
                      <Fragment key={`g-${group.lab_group_id}`}>
                        <tr
                          className="border-b border-border hover:bg-[#f8f9fa] cursor-pointer"
                          onClick={() => toggleGroup(group.lab_group_id)}
                        >
                          <td className="p-3 text-sm font-semibold text-foreground">
                            <span className="inline-flex items-center gap-2">
                              {groupOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                              {group.lab_group_name}
                            </span>
                          </td>
                          <td className="p-3 text-sm text-right font-medium text-foreground">{formatCurrency(Number(group.budget_sgd))}</td>
                          <td className="p-3 text-sm text-right text-foreground">{formatCurrency(Number(group.actual_spend_sgd))}</td>
                          <td className="p-3 text-sm text-right text-foreground">{formatCurrency(Number(group.pending_sgd))}</td>
                          <td className="p-3 text-sm text-right font-medium text-foreground">{formatCurrency(Number(group.available_balance_sgd))}</td>
                          <td className={`p-3 text-sm text-right font-medium ${pctColor(group.utilisation_pct)}`}>{group.utilisation_pct.toFixed(1)}%</td>
                          <td className={`p-3 text-sm text-right font-medium ${pctColor(group.projected_utilisation_pct)}`}>{group.projected_utilisation_pct.toFixed(1)}%</td>
                        </tr>
                        {groupOpen &&
                          group.labs.map((lab) => {
                            const labOpen = expandedLabs.has(lab.lab_id);
                            return (
                              <Fragment key={`l-${lab.lab_id}`}>
                                <tr
                                  className="border-b border-border bg-[#fafafa] hover:bg-[#f3f4f6] cursor-pointer"
                                  onClick={() => toggleLab(lab.lab_id)}
                                >
                                  <td className="p-3 pl-10 text-sm text-foreground">
                                    <span className="inline-flex items-center gap-2">
                                      {labOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                                      {lab.lab_name}
                                    </span>
                                  </td>
                                  <td className="p-3 text-sm text-right text-foreground">{formatCurrency(Number(lab.budget_sgd))}</td>
                                  <td className="p-3 text-sm text-right text-foreground">{formatCurrency(Number(lab.actual_spend_sgd))}</td>
                                  <td className="p-3 text-sm text-right text-foreground">{formatCurrency(Number(lab.pending_sgd))}</td>
                                  <td className="p-3 text-sm text-right text-foreground">{formatCurrency(Number(lab.available_balance_sgd))}</td>
                                  <td className={`p-3 text-sm text-right ${pctColor(lab.utilisation_pct)}`}>{lab.utilisation_pct.toFixed(1)}%</td>
                                  <td className={`p-3 text-sm text-right ${pctColor(lab.projected_utilisation_pct)}`}>{lab.projected_utilisation_pct.toFixed(1)}%</td>
                                </tr>
                                {labOpen &&
                                  lab.categories.map((cat) => (
                                    <tr
                                      key={`c-${lab.lab_id}-${cat.category_id}`}
                                      className="border-b border-border bg-[#f5f5f5]"
                                    >
                                      <td className="p-3 pl-16 text-sm text-muted-foreground">{cat.category_name}</td>
                                      <td className="p-3 text-sm text-right text-muted-foreground">{formatCurrency(Number(cat.budget_sgd))}</td>
                                      <td className="p-3 text-sm text-right text-muted-foreground">{formatCurrency(Number(cat.actual_spend_sgd))}</td>
                                      <td className="p-3 text-sm text-right text-muted-foreground">{formatCurrency(Number(cat.pending_sgd))}</td>
                                      <td className="p-3 text-sm text-right text-muted-foreground">{formatCurrency(Number(cat.available_balance_sgd))}</td>
                                      <td className={`p-3 text-sm text-right ${pctColor(cat.utilisation_pct)}`}>{cat.utilisation_pct.toFixed(1)}%</td>
                                      <td className={`p-3 text-sm text-right ${pctColor(cat.projected_utilisation_pct)}`}>{cat.projected_utilisation_pct.toFixed(1)}%</td>
                                    </tr>
                                  ))}
                              </Fragment>
                            );
                          })}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {/* Reset the slot layout to defaults */}
        <div className="flex justify-end">
          <Button variant="outline" size="sm" onClick={resetSlots}>
            Reset layout
          </Button>
        </div>

        {/* Chart slots row 1 — click a title to choose the chart */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {renderSlot(0)}
          {renderSlot(1)}
        </div>

        {/* Chart slots row 2 */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {renderSlot(2)}
          {renderSlot(3)}
        </div>

        {/* Chart slot 5 */}
        {renderSlot(4)}

        {/* Chart slot 6 */}
        {renderSlot(5)}
      </div>
    </div>
  );
}

function formatCurrency(amount: number): string {
  return amount.toLocaleString("en-SG", {
    style: "currency",
    currency: "SGD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  });
}

// Threshold colors for utilisation / projected utilisation cells.
// Matches the KPI card thresholds: ≥95% = error (red), ≥80% = warning (yellow).
function pctColor(pct: number): string {
  if (pct >= 95) return "text-[#dc2626]";
  if (pct >= 80) return "text-[#d97706]";
  return "text-foreground";
}
