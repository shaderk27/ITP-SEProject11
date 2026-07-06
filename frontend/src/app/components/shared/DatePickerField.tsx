import { CalendarIcon } from "lucide-react";
import { format, isValid, parse } from "date-fns";
import type { Matcher } from "react-day-picker";
import { Button } from "../ui/button";
import { Calendar } from "../ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";

interface DatePickerFieldProps {
  /** ISO yyyy-mm-dd (or "" for empty) — the value the backend expects. */
  value: string;
  /** Called with an ISO yyyy-mm-dd string (or "" when cleared). */
  onChange: (isoDate: string) => void;
  placeholder?: string;
  /** Optional inclusive min/max as ISO yyyy-mm-dd. */
  minDate?: string;
  maxDate?: string;
}

function isoToDate(iso: string | undefined): Date | undefined {
  if (!iso) return undefined;
  const d = parse(iso, "yyyy-MM-dd", new Date());
  return isValid(d) ? d : undefined;
}

// Year range offered in the caption dropdown.
const MIN_YEAR = 2000;
const MAX_YEAR = new Date().getFullYear() + 2;

/**
 * Date field that always displays dd/MM/yyyy (via date-fns) and picks from a
 * calendar with month + year dropdowns — unlike a native <input type="date">,
 * whose format is dictated by the browser's locale and can't be forced, and
 * whose year navigation is one-month-at-a-time. Value in/out stays ISO.
 */
export function DatePickerField({
  value,
  onChange,
  placeholder = "dd/mm/yyyy",
  minDate,
  maxDate,
}: DatePickerFieldProps) {
  const selected = isoToDate(value);

  const disabled: Matcher[] = [];
  const min = isoToDate(minDate);
  const max = isoToDate(maxDate);
  if (min) disabled.push({ before: min });
  if (max) disabled.push({ after: max });

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="font-normal">
          <CalendarIcon className="h-4 w-4 mr-2 text-muted-foreground" />
          {selected ? (
            format(selected, "dd/MM/yyyy")
          ) : (
            <span className="text-muted-foreground">{placeholder}</span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <Calendar
          mode="single"
          selected={selected}
          defaultMonth={selected}
          onSelect={(d) => onChange(d ? format(d, "yyyy-MM-dd") : "")}
          disabled={disabled.length ? disabled : undefined}
          captionLayout="dropdown"
          fromYear={MIN_YEAR}
          toYear={MAX_YEAR}
          initialFocus
          classNames={{
            // rdp ships these hidden via its own CSS (not loaded here) —
            // hide them ourselves so the a11y labels don't leak as text.
            vhidden: "sr-only",
            caption_label: "hidden",
            caption_dropdowns: "flex justify-center gap-2",
            dropdown:
              "bg-white border border-border rounded-md px-2 py-1 text-sm font-medium cursor-pointer focus:outline-none focus:ring-2 focus:ring-ring",
          }}
        />
      </PopoverContent>
    </Popover>
  );
}
