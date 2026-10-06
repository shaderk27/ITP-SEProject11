import {
  Fragment,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type ReactElement,
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
import { InfoTip } from "../components/shared/InfoTip";
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
import { format, parseISO, subDays } from "date-fns";
import { setAskAiPageContext } from "../services/chatbotService";
import {
  exportDashboard,
  getBreakdown,
  getMonthly,
  getSpendingSummary,
  listLabGroups,
  listPeriods,
  type MonthlyPoint,
  type Period,
} from "../services/dashboardService";
import { toast } from "sonner";
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
// Plain-English meaning of each budget figure, shown on the KPI cards and the
// breakdown table headers. Keep in sync with how backend/app/api/dashboard.py
// calculates them.
const TERM_INFO = {
  totalBudget: "The full-year budget for your current selection.",
  actualSpend: 'Total of PR lines whose status starts with "Approved".',
  pending:
    'Total of PR lines whose status starts with "Pending". This money is committed but not yet approved.',
  available:
    "Budget − Actual Spend − Pending. What's left if every pending PR gets approved.",
  utilisation: "Actual Spend ÷ Budget × 100%.",
  projected:
    "(Actual Spend + Pending) ÷ Budget × 100%. Where you'll end up if all pending PRs are approved.",
};

const MAX_COMPARE = 20;

// Value-label font size that scales with how crowded the chart is: fewer bars
// → larger, more readable text; many bars → smaller so labels don't collide.
// `categories` = number of x-axis slots; `perCategory` = bars drawn in each
// slot (grouped/YoY charts pack 2+ bars per slot, so their labels need to be
// smaller). Since the chart cards are full-width, bar count is a good proxy
// for the horizontal space each label gets. Clamped to a legible 6–12px.
function labelFontSize(categories: number, perCategory = 1, floor = 6): number {
  const bars = Math.max(1, categories * perCategory);
  // ~5 bars → 12px, tapering down toward `floor` by ~40 bars.
  const size = Math.round(13 - (bars - 5) * (8 / 35));
  return Math.max(floor, Math.min(12, size));
}

// True when every value across `keys` is zero for all rows (also true for an
// empty list). An all-zero result carries no information, so charts treat it
// the same as "no data" instead of drawing a frame full of zero-height bars.
function allZero(
  rows: Array<Record<string, unknown>>,
  keys: string[],
): boolean {
  return rows.every((r) => keys.every((k) => Number(r[k] ?? 0) === 0));
}

// Searchable selector: pick up to `max` entities to display in a comparison chart.
// Starts empty — the user checks what they want to see.
function EntityFilter({
  names,
  selected,
  onToggle,
  onClear,
  max,
  label = "Select",
}: {
  names: string[];
  selected: Set<string>;
  onToggle: (name: string) => void;
  onClear: () => void;
  max: number;
  label?: string;
}) {
  const [query, setQuery] = useState("");
  if (names.length === 0) return null;
  const atMax = selected.size >= max;
  const filtered = names.filter((n) =>
    n.toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <div className="mb-3 no-print">
      <Popover>
        <PopoverTrigger asChild>
          <Button variant="outline" size="sm" className="gap-2">
            <Filter className="h-4 w-4" />
            {label} ({selected.size}/{max})
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-64 p-2">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-muted-foreground">
              {selected.size} selected
            </span>
            {selected.size > 0 && (
              <button
                type="button"
                onClick={onClear}
                className="text-xs text-blue-600 hover:underline"
              >
                Clear
              </button>
            )}
          </div>
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

// Mirrors the FilterBar "Date Range" options, for the printed cover block.
const DATE_RANGE_LABELS: Record<string, string> = {
  all: "Whole year",
  "7d": "Last 7 days",
  "30d": "Last 30 days",
  "90d": "Last 90 days",
  ytd: "Year to date",
};

const ROLE_LABELS: Record<string, string> = {
  admin: "Admin",
  teamlead: "Team Lead",
  labic: "Lab IC",
};

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

// Truncate a label to n chars (full name still shows in the tooltip).
function trunc(s: string, n: number): string {
  return s.length > n ? `${s.slice(0, n)}..` : s;
}

// Wrap a label to <=2 lines at word boundaries; if a word can't fit, truncate.
function wrapLabel(s: string, n: number): string[] {
  if (s.length <= n) return [s];
  const words = s.split(" ");
  let line1 = "";
  let i = 0;
  while (i < words.length) {
    const w = words[i] ?? "";
    const candidate = line1 ? `${line1} ${w}` : w;
    if (candidate.length > n) break;
    line1 = candidate;
    i++;
  }
  const rest = words.slice(i).join(" ");
  if (line1 && rest && rest.length <= n) return [line1, rest];
  return [trunc(s, n)];
}

// Multi-line x-axis tick: wraps long labels instead of truncating when there's room.
function WrapTick(props: {
  x?: number;
  y?: number;
  payload?: { value?: string | number };
  charsPerLine: number;
}) {
  const { x = 0, y = 0, payload, charsPerLine } = props;
  const lines = wrapLabel(String(payload?.value ?? ""), charsPerLine);
  return (
    <g transform={`translate(${x},${y})`}>
      {lines.map((line, i) => (
        <text
          key={i}
          x={0}
          dy={16 + i * 14}
          textAnchor="middle"
          fill="#6b7280"
          fontSize={12}
        >
          {line}
        </text>
      ))}
    </g>
  );
}

// Wraps a bar chart and measures its width so x-axis labels only truncate when
// the card is too narrow to fit them. Wide cards show full names.
function AdaptiveBarChart({
  height,
  bars,
  children,
}: {
  height: number;
  bars: number;
  children: (charsPerLine: number) => ReactElement;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      setWidth(entries[0]?.contentRect.width ?? 0);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  // Chars that fit per label line (minus the y-axis gutter + a gap). ~7.5px/char.
  // Before the first measurement, assume wide (no wrap/truncate).
  const band = width === 0 || bars === 0 ? 0 : (width - 50) / bars;
  const charsPerLine =
    band === 0 ? 999 : Math.max(4, Math.floor((band - 22) / 7.5));
  return (
    <div ref={ref}>
      <ResponsiveContainer width="100%" height={height}>
        {children(charsPerLine)}
      </ResponsiveContainer>
    </div>
  );
}

export function DashboardPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  // Lab IC is scoped to a single lab: the "By Lab Group" view and the
  // entity-select filter are meaningless for them, so both are hidden and
  // only the single lab's chart shows.
  const isLabIc = user?.role === "labic";

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
  const [stackShown, setStackShown] = useState<Set<string>>(new Set());
  const [categoryShown, setCategoryShown] = useState<Set<string>>(new Set());
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
  const [exporting, setExporting] = useState(false);
  // Track which lab_group / lab rows are expanded in the drilldown table.
  const [expandedGroups, setExpandedGroups] = useState<Set<number>>(new Set());
  const [expandedLabs, setExpandedLabs] = useState<Set<number>>(new Set());
  // Same-month Year-over-Year comparison: chosen fiscal month (calendar 1–12)
  // and which fiscal years to compare; the bars are computed by the effect below.
  const [yoyMonth, setYoyMonth] = useState(3); // default March
  const [yoyYearIds, setYoyYearIds] = useState<Set<number>>(new Set());
  const [yoyViewBy, setYoyViewBy] = useState<"group" | "lab">("group");
  // One row per entity (lab group / lab), with a spend value keyed by each year.
  const [yoyData, setYoyData] = useState<Record<string, number | string>[]>([]);
  const [yoyEntityShown, setYoyEntityShown] = useState<Set<string>>(new Set());
  // Toggle a fiscal year (by name) in the YoY comparison, capped at MAX_COMPARE.
  const toggleYoyYearByName = (name: string) =>
    setYoyYearIds((prev) => {
      const period = periods.find((p) => p.name === name);
      if (!period) return prev;
      const next = new Set(prev);
      if (next.has(period.id)) next.delete(period.id);
      else if (next.size < MAX_COMPARE) next.add(period.id);
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
    // Team Lead / Lab IC only have one lab group, so default every chart to
    // "By Lab"; Admin keeps "By Lab Group".
    const defaultViewBy =
      user?.role === "teamlead" || user?.role === "labic" ? "lab" : "group";
    setUtilViewBy(defaultViewBy);
    setAvbViewBy(defaultViewBy);
    setStackViewBy(defaultViewBy);
    setYoyViewBy(defaultViewBy);
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

  // Year-over-Year: for each selected fiscal year, fetch that year's spend for
  // the chosen month via the breakdown (one call per year), then group entities
  // (lab groups or labs) side by side with a bar per year.
  useEffect(() => {
    let cancelled = false;
    // Empty selection falls through: Promise.all([]) resolves to [] async.
    const chosen = periods.filter((p) => yoyYearIds.has(p.id));
    Promise.all(
      chosen.map((p) => {
        // Fiscal Apr–Dec sit in the FY's start year; Jan–Mar roll into +1.
        const startYear = Number(p.start_date.slice(0, 4));
        const calYear = yoyMonth >= 4 ? startYear : startYear + 1;
        const mm = String(yoyMonth).padStart(2, "0");
        const last = new Date(calYear, yoyMonth, 0).getDate();
        const start = `${calYear}-${mm}-01`;
        const end = `${calYear}-${mm}-${String(last).padStart(2, "0")}`;
        return getBreakdown("all", start, end, p.id).then((resp) => ({
          year: p.name,
          resp,
        }));
      }),
    )
      .then((results) => {
        if (cancelled) return;
        const map = new Map<string, Record<string, number | string>>();
        for (const { year, resp } of results) {
          for (const g of resp.lab_groups) {
            if (g.lab_group_name === "General") continue;
            if (yoyViewBy === "group") {
              const row = map.get(g.lab_group_name) ?? {
                name: g.lab_group_name,
              };
              row[year] = Number(g.actual_spend_sgd);
              map.set(g.lab_group_name, row);
            } else {
              for (const l of g.labs) {
                if (l.lab_name === "General") continue;
                const row = map.get(l.lab_name) ?? { name: l.lab_name };
                row[year] = Number(l.actual_spend_sgd);
                map.set(l.lab_name, row);
              }
            }
          }
        }
        const yearNames = results.map((r) => r.year);
        const rows = Array.from(map.values());
        for (const row of rows)
          for (const yn of yearNames)
            if (row[yn] === undefined) row[yn] = 0;
        rows.sort((a, b) => String(a.name).localeCompare(String(b.name)));
        setYoyData(rows);
      })
      .catch(() => {
        if (!cancelled) setYoyData([]);
      });
    return () => {
      cancelled = true;
    };
  }, [yoyMonth, yoyYearIds, yoyViewBy, periods]);

  // Persist the slot layout whenever it changes.
  useEffect(() => {
    try {
      localStorage.setItem(slotsStorageKey, JSON.stringify(slots));
    } catch {
      /* ignore */
    }
  }, [slotsStorageKey, slots]);

  // Selected fiscal year (undefined = "All time"). The 7/30/90-day presets
  // count back from today, so they only make sense when today is inside the
  // selected year; for a past or future year they would give an empty window.
  const selectedPeriod = periods.find((p) => p.id === selectedFYPeriodId);
  const fyStart = selectedPeriod?.start_date ?? "";
  const fyEnd = selectedPeriod?.end_date ?? "";
  const todayIso = format(new Date(), "yyyy-MM-dd");
  const presetsAvailable =
    !selectedPeriod || (fyStart <= todayIso && todayIso <= fyEnd);

  // Effective spend window: the selected FY's span, narrowed by a preset/custom.
  // `clipped` = the preset reached back before the FY start and was cut to it.
  const [effStart, effEnd, clipped] = useMemo(() => {
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
    return [s, e, Boolean(rawStart && fyStart && rawStart < fyStart)] as const;
  }, [fyStart, fyEnd, dateRange, startDate, endDate]);

  // The window is narrower than the whole fiscal year (or than all time), so
  // spend covers only part of the period the Total Budget is for.
  const windowNarrowed = selectedPeriod
    ? effStart !== fyStart || effEnd !== fyEnd
    : Boolean(effStart || effEnd);

  // Ask AI answers for the same period as the dashboard while it is open.
  useEffect(() => {
    if (selectedFYPeriodId == null) return;
    setAskAiPageContext({
      periodId: selectedFYPeriodId,
      startDate: effStart,
      endDate: effEnd,
    });
    return () => setAskAiPageContext(null);
  }, [selectedFYPeriodId, effStart, effEnd]);

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
      let total = 0;
      for (const catList of cats) {
        for (const cat of catList) {
          categories.add(cat.category_name);
          const amt = Number(cat.actual_spend_sgd);
          row[cat.category_name] = (Number(row[cat.category_name]) || 0) + amt;
          total += amt;
        }
      }
      row.__total = total;
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
  const stackAll =
    stackViewBy === "lab" ? stackedCategory.lab : stackedCategory.group;
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
  const stackNames = stackAll.map((d) => String(d.name)).join("|");
  const [prevStackNames, setPrevStackNames] = useState(stackNames);
  if (stackNames !== prevStackNames) {
    setPrevStackNames(stackNames);
    setStackShown(
      stackAll.length <= MAX_COMPARE
        ? new Set(stackAll.map((d) => String(d.name)))
        : new Set(),
    );
  }
  const utilVisible = utilAll.filter((d) => utilShown.has(d.name));
  const avbVisible = avbAll.filter((d) => avbShown.has(d.name));
  const stackVisible = stackAll.filter((r) => stackShown.has(String(r.name)));
  // Category chart filter (choose which categories to show).
  const categoryKey = categoryData.map((d) => d.category).join("|");
  const [prevCategoryKey, setPrevCategoryKey] = useState(categoryKey);
  if (categoryKey !== prevCategoryKey) {
    setPrevCategoryKey(categoryKey);
    setCategoryShown(
      categoryData.length <= MAX_COMPARE
        ? new Set(categoryData.map((d) => d.category))
        : new Set(),
    );
  }
  const categoryVisible = categoryData.filter((d) =>
    categoryShown.has(d.category),
  );
  // YoY selected fiscal years exposed as names for the shared Select filter.
  const yoyYearNames = new Set(
    periods.filter((p) => yoyYearIds.has(p.id)).map((p) => p.name),
  );
  // Years to plot as grouped bars (sorted oldest → newest).
  const yoySelectedYears = periods
    .filter((p) => yoyYearIds.has(p.id))
    .map((p) => p.name)
    .sort();
  // Entity Select seeding (≤ MAX_COMPARE auto-shows all), like the other charts.
  const yoyEntityKey = yoyData.map((r) => String(r.name)).join("|");
  const [prevYoyEntityKey, setPrevYoyEntityKey] = useState(yoyEntityKey);
  if (yoyEntityKey !== prevYoyEntityKey) {
    setPrevYoyEntityKey(yoyEntityKey);
    setYoyEntityShown(
      yoyData.length <= MAX_COMPARE
        ? new Set(yoyData.map((r) => String(r.name)))
        : new Set(),
    );
  }
  const yoyVisible = yoyData.filter((r) => yoyEntityShown.has(String(r.name)));

  // Message for an empty chart, kept consistent across roles:
  //   - no underlying data at all → a plain "nothing to show" line
  //     (Lab IC gets a "your lab" flavour since they're scoped to one lab);
  //   - data exists but nothing is picked (only reachable when there are more
  //     than MAX_COMPARE entities, so the select starts empty) → the action
  //     hint telling the user to pick some via the Select button.
  function emptyChartMessage(hasData: boolean, selectHint: string): string {
    if (hasData) return selectHint;
    return isLabIc
      ? "No data to display for your lab yet."
      : "No data to display yet.";
  }

  // Render the body (chart-specific controls + chart) for a given chart id.
  // Any slot can render any chart, so this lives in one place.
  function renderChartBody(chartId: string): ReactNode {
    switch (chartId) {
      case "utilisation":
        return (
          <>
            {!isLabIc && (
              <div className="flex justify-end mb-3 no-print">
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
            )}
            {!isLabIc && (
              <EntityFilter
                names={utilAll.map((d) => d.name)}
                selected={utilShown}
                onToggle={toggleShown(setUtilShown)}
                onClear={() => setUtilShown(new Set())}
                max={MAX_COMPARE}
              />
            )}
            {/* Utilisation is exempt from the all-zero rule: 0% is meaningful
                (a budget exists, nothing spent yet), so still draw the bars. */}
            {utilVisible.length === 0 ? (
              <div className="h-[300px] flex items-center justify-center text-sm text-muted-foreground">
                {emptyChartMessage(
                  utilAll.length > 0,
                  `Use the Select button above to choose up to ${MAX_COMPARE} to display.`,
                )}
              </div>
            ) : (
              <AdaptiveBarChart height={300} bars={utilVisible.length}>
                {(maxChars) => (
                  <BarChart data={utilVisible} barCategoryGap="25%" margin={{ top: 18 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis
                      dataKey="name"
                      stroke="#6b7280"
                      interval={0}
                      height={42}
                      tick={<WrapTick charsPerLine={maxChars} />}
                    />
                    <YAxis stroke="#6b7280" domain={[0, 100]} unit="%" />
                    <Tooltip formatter={(v: number) => `${v}%`} />
                    <ReferenceLine
                      y={50}
                      stroke="#fcd34d"
                      strokeDasharray="4 4"
                      label={{ value: "50%", position: "right", fill: "#fbbf24", fontSize: 11 }}
                    />
                    <ReferenceLine
                      y={80}
                      stroke="#fdba74"
                      strokeDasharray="4 4"
                      label={{ value: "80%", position: "right", fill: "#fb923c", fontSize: 11 }}
                    />
                    <ReferenceLine
                      y={95}
                      stroke="#fca5a5"
                      strokeDasharray="4 4"
                      label={{ value: "95%", position: "right", fill: "#f87171", fontSize: 11 }}
                    />
                    <Bar dataKey="util" name="Utilisation %" radius={[4, 4, 0, 0]}>
                      {utilVisible.map((d, i) => (
                        <Cell key={i} fill={utilColor(d.util)} />
                      ))}
                      <LabelList
                        dataKey="util"
                        position="top"
                        formatter={(v: number) => `${Number(v).toFixed(1)}%`}
                        fontSize={labelFontSize(utilVisible.length)}
                        fontWeight={600}
                        fill="#111827"
                      />
                    </Bar>
                  </BarChart>
                )}
              </AdaptiveBarChart>
            )}
          </>
        );
      case "actualVsBudget":
        return (
          <>
            {!isLabIc && (
              <div className="flex justify-end mb-3 no-print">
                <select
                  value={avbViewBy}
                  onChange={(e) => setAvbViewBy(e.target.value as "group" | "lab")}
                  className="text-sm border border-border rounded-md px-2 py-1 bg-white shrink-0"
                >
                  <option value="group">By Lab Group</option>
                  <option value="lab">By Lab</option>
                </select>
              </div>
            )}
            {!isLabIc && (
              <EntityFilter
                names={avbAll.map((d) => d.name)}
                selected={avbShown}
                onToggle={toggleShown(setAvbShown)}
                onClear={() => setAvbShown(new Set())}
                max={MAX_COMPARE}
              />
            )}
            {avbVisible.length === 0 ||
            allZero(avbVisible, ["budget", "actual"]) ? (
              <div className="h-[300px] flex items-center justify-center text-sm text-muted-foreground">
                {emptyChartMessage(
                  avbAll.length > 0 && avbVisible.length === 0,
                  `Use the Select button above to choose up to ${MAX_COMPARE} to display.`,
                )}
              </div>
            ) : (
              <AdaptiveBarChart height={300} bars={avbVisible.length}>
                {(maxChars) => (
                  <BarChart
                    data={avbVisible}
                    barGap={8}
                    barCategoryGap="20%"
                    margin={{ top: 24, left: 12, right: 8 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis
                      dataKey="name"
                      stroke="#6b7280"
                      interval={0}
                      height={42}
                      tick={<WrapTick charsPerLine={maxChars} />}
                    />
                    <YAxis stroke="#6b7280" />
                    <Tooltip formatter={(v: number) => `$${Number(v).toLocaleString()}`} />
                    <Legend />
                    <Bar dataKey="budget" fill="#1e3a8a" name="Budget" radius={[4, 4, 0, 0]}>
                      <LabelList
                        dataKey="budget"
                        position="top"
                        formatter={(v: number) => compactCurrency(Number(v))}
                        fontSize={labelFontSize(avbVisible.length, 2, 5)}
                        fill="#374151"
                      />
                    </Bar>
                    <Bar dataKey="actual" fill="#3b82f6" name="Actual" radius={[4, 4, 0, 0]}>
                      <LabelList
                        dataKey="actual"
                        position="top"
                        formatter={(v: number) => compactCurrency(Number(v))}
                        fontSize={labelFontSize(avbVisible.length, 2, 5)}
                        fill="#374151"
                      />
                    </Bar>
                  </BarChart>
                )}
              </AdaptiveBarChart>
            )}
          </>
        );
      case "category":
        return (
          <>
            <EntityFilter
              names={categoryData.map((d) => d.category)}
              selected={categoryShown}
              onToggle={toggleShown(setCategoryShown)}
              onClear={() => setCategoryShown(new Set())}
              max={MAX_COMPARE}
              label="Categories"
            />
            {categoryVisible.length === 0 ||
            allZero(categoryVisible, ["amount"]) ? (
              <div className="h-[300px] flex items-center justify-center text-sm text-muted-foreground">
                {emptyChartMessage(
                  categoryData.length > 0 && categoryVisible.length === 0,
                  "Select a category to display.",
                )}
              </div>
            ) : (
              <ResponsiveContainer
                width="100%"
                height={Math.max(300, categoryVisible.length * 22)}
              >
                <BarChart
                  data={categoryVisible}
                  layout="vertical"
                  barCategoryGap="20%"
                  margin={{ right: 64, left: 8 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis type="number" stroke="#6b7280" />
                  <YAxis
                    dataKey="category"
                    type="category"
                    stroke="#6b7280"
                    width={110}
                    interval={0}
                    tick={{ fontSize: 10 }}
                  />
                  <Tooltip
                    formatter={(v: number) =>
                      `$${Number(v).toLocaleString(undefined, {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}`
                    }
                    contentStyle={{ fontSize: 11 }}
                    itemStyle={{ fontSize: 11 }}
                    labelStyle={{ fontSize: 11 }}
                  />
                  <Bar dataKey="amount" fill="#0d9488" radius={[0, 4, 4, 0]}>
                    <LabelList
                      dataKey="amount"
                      position="right"
                      formatter={(v: number) => `$${Number(v).toLocaleString()}`}
                      fontSize={9}
                      fill="#374151"
                    />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </>
        );
      case "monthly":
        return (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={monthlyData} margin={{ top: 24, right: 32, left: 12 }}>
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
              >
                <LabelList
                  dataKey="amount"
                  content={(props: {
                    x?: number;
                    y?: number;
                    value?: number | string;
                    index?: number;
                  }) => {
                    const idx = props.index ?? 0;
                    const val = Number(props.value ?? 0);
                    const prev = monthlyData[idx - 1]?.amount ?? val;
                    const next = monthlyData[idx + 1]?.amount ?? val;
                    const isFirst = idx === 0;
                    const isLast = idx === monthlyData.length - 1;
                    // Endpoints go above and anchor to the edge so they don't
                    // clip; middle valleys go below the line — except $0 points,
                    // which sit on the axis, so "below" would collide with the
                    // month labels; force those above.
                    const below =
                      val !== 0 && !isFirst && !isLast && val <= prev && val <= next;
                    return (
                      <text
                        x={Number(props.x ?? 0)}
                        y={Number(props.y ?? 0)}
                        dy={below ? 16 : -8}
                        textAnchor={
                          isFirst ? "start" : isLast ? "end" : "middle"
                        }
                        fontSize={10}
                        fill="#374151"
                        stroke="#ffffff"
                        strokeWidth={3}
                        strokeLinejoin="round"
                        style={{ paintOrder: "stroke" }}
                      >
                        {`$${val.toLocaleString()}`}
                      </text>
                    );
                  }}
                />
              </Line>
            </LineChart>
          </ResponsiveContainer>
        );
      case "categoryMix":
        return (
          <>
            {!isLabIc && (
              <div className="flex justify-end mb-3 no-print">
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
            )}
            {!isLabIc && (
              <EntityFilter
                names={stackAll.map((d) => String(d.name))}
                selected={stackShown}
                onToggle={toggleShown(setStackShown)}
                onClear={() => setStackShown(new Set())}
                max={MAX_COMPARE}
              />
            )}
            {stackVisible.length === 0 || allZero(stackVisible, ["__total"]) ? (
              <div className="h-[320px] flex items-center justify-center text-sm text-muted-foreground">
                {emptyChartMessage(
                  stackAll.length > 0 && stackVisible.length === 0,
                  `Use the Select button above to choose up to ${MAX_COMPARE} to display.`,
                )}
              </div>
            ) : (
              <AdaptiveBarChart height={320} bars={stackVisible.length}>
                {(maxChars) => (
                  <BarChart
                    data={stackVisible}
                    barCategoryGap="20%"
                    margin={{ top: 20, left: 8 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis
                      dataKey="name"
                      stroke="#6b7280"
                      interval={0}
                      height={42}
                      tick={<WrapTick charsPerLine={maxChars} />}
                    />
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
                      >
                        {i === stackedCategory.categories.length - 1 && (
                          <LabelList
                            dataKey="__total"
                            position="top"
                            formatter={(v: number) => compactCurrency(Number(v))}
                            fontSize={labelFontSize(stackVisible.length)}
                            fontWeight={600}
                            fill="#374151"
                          />
                        )}
                      </Bar>
                    ))}
                  </BarChart>
                )}
              </AdaptiveBarChart>
            )}
          </>
        );
      case "yoy":
        return (
          <>
            <div className="flex flex-wrap items-center justify-end mb-3 gap-2 no-print">
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
              {!isLabIc && (
                <select
                  value={yoyViewBy}
                  onChange={(e) => setYoyViewBy(e.target.value as "group" | "lab")}
                  className="text-sm border border-border rounded-md px-2 py-1 bg-white"
                >
                  <option value="group">By Lab Group</option>
                  <option value="lab">By Lab</option>
                </select>
              )}
            </div>
            <div className="flex flex-wrap gap-2 mb-3">
              <EntityFilter
                names={periods.map((p) => p.name)}
                selected={yoyYearNames}
                onToggle={toggleYoyYearByName}
                onClear={() => setYoyYearIds(new Set())}
                max={MAX_COMPARE}
                label="Years"
              />
              {!isLabIc && (
                <EntityFilter
                  names={yoyData.map((r) => String(r.name))}
                  selected={yoyEntityShown}
                  onToggle={toggleShown(setYoyEntityShown)}
                  onClear={() => setYoyEntityShown(new Set())}
                  max={MAX_COMPARE}
                  label={yoyViewBy === "lab" ? "Labs" : "Groups"}
                />
              )}
            </div>
            {yoyVisible.length === 0 ||
            yoySelectedYears.length === 0 ||
            allZero(yoyVisible, yoySelectedYears) ? (
              <div className="h-[300px] flex items-center justify-center text-sm text-muted-foreground">
                {yoySelectedYears.length === 0
                  ? // No fiscal years chosen yet → prompt to pick (Lab IC has no
                    // entity picker, so drop "and entities" for them).
                    isLabIc
                    ? "Pick fiscal years to compare."
                    : "Pick fiscal years and entities to compare."
                  : // Years are chosen but nothing lands in scope (or all zero)
                    // → no data.
                    emptyChartMessage(false, "")}
              </div>
            ) : (
              <AdaptiveBarChart height={300} bars={yoyVisible.length}>
                {(maxChars) => (
                  <BarChart
                    data={yoyVisible}
                    barCategoryGap="20%"
                    margin={{ top: 24 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis
                      dataKey="name"
                      stroke="#6b7280"
                      interval={0}
                      height={42}
                      tick={<WrapTick charsPerLine={maxChars} />}
                    />
                    <YAxis stroke="#6b7280" />
                    <Tooltip
                      formatter={(v: number) => `$${Number(v).toLocaleString()}`}
                    />
                    <Legend />
                    {yoySelectedYears.map((yn, i) => (
                      <Bar
                        key={yn}
                        dataKey={yn}
                        name={yn}
                        fill={CATEGORY_COLORS[i % CATEGORY_COLORS.length]}
                        radius={[4, 4, 0, 0]}
                      >
                        <LabelList
                          dataKey={yn}
                          position="top"
                          formatter={(v: number) =>
                            v ? compactCurrency(Number(v)) : ""
                          }
                          fontSize={labelFontSize(
                            yoyVisible.length,
                            Math.max(1, yoySelectedYears.length),
                          )}
                          fill="#374151"
                        />
                      </Bar>
                    ))}
                  </BarChart>
                )}
              </AdaptiveBarChart>
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

  // ── Export ──────────────────────────────────────────────────────────
  const selectedGroupName =
    selectedGroupId === "all"
      ? "All Lab Groups"
      : (labGroups.find((g) => String(g.id) === selectedGroupId)?.name ??
        selectedGroupId);
  const selectedLabName =
    selectedLabId === "all" ? "All labs" : (selectedLab?.lab_name ?? "All labs");
  const dateRangeLabel = customActive
    ? `Custom: ${startDate || "beginning"} to ${endDate || "today"}`
    : (DATE_RANGE_LABELS[dateRange] ?? "Whole year");

  /** Filter context stamped onto the printed page, mirroring the .xlsx cover. */
  const printContext: [string, string][] = [
    ["Generated", new Date().toLocaleString("en-SG")],
    ["Generated by", `${user?.fullName ?? user?.email ?? ""} (${ROLE_LABELS[user?.role ?? ""] ?? ""})`],
    ["Fiscal Year", selectedPeriod?.name ?? "All time"],
    ["Date Range", dateRangeLabel],
    ["Lab Group", selectedGroupName],
    ["Lab", selectedLabName],
  ];

  // The browser's own print pipeline renders the PDF: the charts are inline
  // SVG so they stay vector, text stays selectable, and nothing has to be
  // rasterised by a canvas library (which would also choke on the oklch()
  // colours in theme.css).
  const handleExportPdf = () => {
    // Let the dropdown unmount before the print dialog snapshots the page.
    setTimeout(() => window.print(), 80);
  };

  const handleExportExcel = async () => {
    setExporting(true);
    try {
      const filename = await exportDashboard({
        startDate: effStart,
        endDate: effEnd,
        dateRange,
        periodId: selectedFYPeriodId,
        labGroupId: selectedGroupId === "all" ? null : Number(selectedGroupId),
        labId: selectedLabId === "all" ? null : Number(selectedLabId),
        customStart: startDate,
        customEnd: endDate,
      });
      toast.success("Export complete", {
        description: `${filename} saved to your downloads folder.`,
      });
    } catch (err) {
      toast.error("Export failed", {
        description:
          err instanceof Error ? err.message : "Could not generate the report.",
      });
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="h-full overflow-auto bg-[#f8f9fa]">
      {/* Filters */}
      <div className="no-print">
      <FilterBar
        searchPlaceholder="Search dashboard..."
        showExport
        exportDisabled={exporting}
        exportOptions={[
          {
            id: "pdf",
            label: "Export as PDF",
            description: "Visual snapshot — KPIs, charts and breakdown",
          },
          {
            id: "excel",
            label: "Export as Excel",
            description: "KPIs, breakdown table and monthly trend",
          },
        ]}
        onExportOption={(id) =>
          id === "pdf" ? handleExportPdf() : void handleExportExcel()
        }
        onFilterChange={(filterId, value) => {
          if (filterId === "Fiscal Year") {
            const id = value === "all" ? 0 : Number(value);
            setSelectedFYPeriodId(id);
            // Drop sub-window choices that don't fit the new year, rather than
            // silently clamping them into an empty or partial window.
            const next = periods.find((p) => p.id === id);
            if (next) {
              const inYear = (d: string) =>
                !d || (next.start_date <= d && d <= next.end_date);
              if (!(next.start_date <= todayIso && todayIso <= next.end_date)) {
                setDateRange("all");
              }
              if (!inYear(startDate) || !inYear(endDate)) {
                setStartDate("");
                setEndDate("");
              }
            }
          }
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
            // "Last N days" counts back from today, so it is only offered
            // when today falls inside the selected fiscal year.
            options: [
              { value: "all", label: "Whole year" },
              ...(presetsAvailable
                ? [
                    { value: "7d", label: "Last 7 days" },
                    { value: "30d", label: "Last 30 days" },
                    { value: "90d", label: "Last 90 days" },
                  ]
                : []),
            ],
          },
          // Lab IC is scoped to a single lab and has no group choice, so the
          // Lab Group filter is meaningless (renders empty) — hide it for them.
          ...(isLabIc
            ? []
            : [
                {
                  label: "Lab Group",
                  value: selectedGroupId,
                  options: labGroupOptions,
                },
              ]),
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
            minDate={fyStart || undefined}
            maxDate={endDate || fyEnd || undefined}
            onChange={setStartDate}
          />
        </label>
        <label className="flex items-center gap-1.5">
          <span className="text-muted-foreground">To</span>
          <DatePickerField
            value={endDate}
            minDate={startDate || fyStart || undefined}
            maxDate={fyEnd || undefined}
            onChange={setEndDate}
          />
        </label>
        {selectedPeriod && (
          <span className="text-xs text-muted-foreground">
            Within {selectedPeriod.name}. For another year, change Fiscal Year
            (or pick All time).
          </span>
        )}
        {clipped && (
          <span className="text-xs text-amber-700">
            {DATE_RANGE_LABELS[dateRange]} starts before {selectedPeriod?.name}, so
            it is counted from {formatIsoDate(fyStart)}.
          </span>
        )}
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
      </div>

      <div className="p-6 space-y-6">
        {/* Printed cover block. Hidden on screen; replaces the filter bar and
            role banner on paper so the PDF records what it is a snapshot of. */}
        <div className="print-only print-keep mb-4">
          <h1 className="text-xl font-bold text-[#1e3a8a]">
            Lab Budget Monitoring System
          </h1>
          <p className="text-sm text-[#475569]">Dashboard Report</p>
          <dl className="mt-3 grid grid-cols-2 gap-x-8 gap-y-1 text-xs text-[#475569]">
            {printContext.map(([label, value]) => (
              <div key={label} className="flex gap-2">
                <dt className="font-semibold">{label}:</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
          <hr className="mt-3 border-[#e5e7eb]" />
        </div>

        {/* Role Info */}
        <div className="no-print">
          <RoleInfo />
        </div>

        {loadError && (
          <Card className="p-4 bg-[#fef2f2] border-[#fecaca]">
            <p className="text-sm text-[#b91c1c]">{loadError}</p>
          </Card>
        )}

        {/* Spend covers a shorter window than the budget it is compared with;
            say so, or a 30-day slice reads as a low utilisation. */}
        {windowNarrowed && (
          <Card className="print-keep p-3 bg-[#eff6ff] border-[#bfdbfe]">
            <p className="text-sm text-[#1e3a8a]">
              Spend is for {effStart ? formatIsoDate(effStart) : "the start"} to{" "}
              {effEnd ? formatIsoDate(effEnd) : "today"}. Total Budget is the{" "}
              {selectedPeriod
                ? `full ${selectedPeriod.name} budget`
                : "total across all fiscal years"}
              , so Utilisation and Available Balance compare this shorter
              period's spend against the whole budget.
            </p>
          </Card>
        )}

        {/* KPI Cards */}
        <div className="print-keep grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-6 gap-6">
          <KPICard
            title="Total Budget"
            description={TERM_INFO.totalBudget}
            value={formatCurrency(totalBudget)}
            icon={DollarSign}
            status="info"
          />
          <KPICard
            title="Actual Spend"
            description={TERM_INFO.actualSpend}
            value={formatCurrency(actualSpend)}
            icon={TrendingUp}
            status="info"
          />
          <KPICard
            title="Pending Amount"
            description={TERM_INFO.pending}
            value={formatCurrency(pendingSpend)}
            icon={Clock}
            status="info"
          />
          <KPICard
            title="Available Balance"
            description={TERM_INFO.available}
            value={formatCurrency(availableBalance)}
            icon={Wallet}
            status="info"
          />
          <KPICard
            title="Utilisation %"
            description={TERM_INFO.utilisation}
            value={`${utilizationPct.toFixed(1)}%`}
            icon={Percent}
            status={utilizationPct >= 95 ? "error" : utilizationPct >= 80 ? "warning" : "info"}
          />
          <KPICard
            title="Projected Utilisation %"
            description={TERM_INFO.projected}
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
                    <th className="text-right p-3 text-xs font-medium text-muted-foreground">
                      <span className="inline-flex items-center gap-1">
                        Util %
                        <InfoTip label="Utilisation %" text={TERM_INFO.utilisation} />
                      </span>
                    </th>
                    <th className="text-right p-3 text-xs font-medium text-muted-foreground">
                      <span className="inline-flex items-center gap-1">
                        Proj %
                        <InfoTip label="Projected Utilisation %" text={TERM_INFO.projected} />
                      </span>
                    </th>
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

        {/* Chart slots — each full-width, one per row. Click a title to choose the chart */}
        {renderSlot(0)}
        {renderSlot(1)}
        {renderSlot(2)}
        {renderSlot(3)}
        {renderSlot(4)}
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

// Compact currency for on-chart value labels (e.g. $88K, $1.2M, $1.4B).
// Width stays ~constant regardless of magnitude, so adjacent grouped-bar
// labels don't clip into each other. Full precision stays in the tooltip.
function compactCurrency(amount: number): string {
  return amount.toLocaleString("en-SG", {
    style: "currency",
    currency: "SGD",
    notation: "compact",
    maximumFractionDigits: 1,
  });
}

// Threshold colors for utilisation / projected utilisation cells.
// Matches the KPI card thresholds: ≥95% = error (red), ≥80% = warning (yellow).
function pctColor(pct: number): string {
  if (pct >= 95) return "text-[#dc2626]";
  if (pct >= 80) return "text-[#d97706]";
  return "text-foreground";
}

/** "2026-04-01" → "1 Apr 2026" (same style as the Ask AI period label). */
function formatIsoDate(iso: string): string {
  return iso ? format(parseISO(iso), "d MMM yyyy") : "";
}
