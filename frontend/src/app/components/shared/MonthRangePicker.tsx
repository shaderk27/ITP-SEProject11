import { useMemo } from "react";
import { eachMonthOfInterval, endOfMonth, format, parseISO } from "date-fns";
import type { Period } from "../../services/dashboardService";

interface MonthRangePickerProps {
  /** Fiscal years whose months are offered (one year, or all for "All time"). */
  periods: Period[];
  /** ISO date: the 1st of the From month, or "" for open-ended. */
  startDate: string;
  /** ISO date: the last day of the To month, or "" for open-ended. */
  endDate: string;
  onStartChange: (iso: string) => void;
  onEndChange: (iso: string) => void;
}

const selectClass = "text-sm border border-border rounded-md px-2 py-1 bg-white";

// From/To month dropdowns for a custom date range. Whole months only: From
// maps to the 1st of the month and To to its last day, so the backend's
// inclusive date filter counts complete months.
export function MonthRangePicker({
  periods,
  startDate,
  endDate,
  onStartChange,
  onEndChange,
}: MonthRangePickerProps) {
  const months = useMemo(() => {
    if (periods.length === 0) return [];
    const first = periods.reduce(
      (a, p) => (p.start_date < a ? p.start_date : a),
      periods[0].start_date,
    );
    const last = periods.reduce(
      (a, p) => (p.end_date > a ? p.end_date : a),
      periods[0].end_date,
    );
    return eachMonthOfInterval({ start: parseISO(first), end: parseISO(last) }).map(
      (d) => ({ value: format(d, "yyyy-MM"), label: format(d, "MMM yyyy") }),
    );
  }, [periods]);

  const fromMonth = startDate.slice(0, 7);
  const toMonth = endDate.slice(0, 7);

  return (
    <>
      <label className="flex items-center gap-1.5">
        <span className="text-muted-foreground">From</span>
        <select
          value={fromMonth}
          onChange={(e) => onStartChange(e.target.value ? `${e.target.value}-01` : "")}
          className={selectClass}
        >
          <option value="">Select month</option>
          {months
            .filter((m) => !toMonth || m.value <= toMonth)
            .map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
        </select>
      </label>
      <label className="flex items-center gap-1.5">
        <span className="text-muted-foreground">To</span>
        <select
          value={toMonth}
          onChange={(e) =>
            onEndChange(
              e.target.value
                ? format(endOfMonth(parseISO(`${e.target.value}-01`)), "yyyy-MM-dd")
                : "",
            )
          }
          className={selectClass}
        >
          <option value="">Select month</option>
          {months
            .filter((m) => !fromMonth || m.value >= fromMonth)
            .map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
        </select>
      </label>
    </>
  );
}
