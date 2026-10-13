import { ChevronDown, Search } from "lucide-react";
import { Input } from "../ui/input";
import { Button } from "../ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";

interface FilterBarProps {
  searchPlaceholder?: string;
  filters?: {
    label: string;
    options: { value: string; label: string }[];
    // Optional controlled value. If provided, the dropdown reflects this
    // state externally (instead of being uncontrolled).
    value?: string;
  }[];
  onSearchChange?: (value: string) => void;
  onFilterChange?: (filterId: string, value: string) => void;
  showExport?: boolean;
  onExport?: () => void;
  /**
   * Turns the Export button into a dropdown. Used where a page can be
   * exported in more than one format; omit it for a single-action button.
   */
  exportOptions?: {
    id: string;
    label: string;
    description?: string;
  }[];
  onExportOption?: (id: string) => void;
  exportDisabled?: boolean;
}

export function FilterBar({
  searchPlaceholder = "Search...",
  filters = [],
  onSearchChange,
  onFilterChange,
  showExport = false,
  onExport,
  exportOptions,
  onExportOption,
  exportDisabled = false,
}: FilterBarProps) {
  return (
    <div className="flex items-center gap-4 p-4 bg-white border-b border-border">
      {/* Search */}
      <div className="relative flex-1 max-w-md">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder={searchPlaceholder}
          className="pl-9"
          onChange={(e) => onSearchChange?.(e.target.value)}
        />
      </div>

      {/* Filters */}
      {filters.map((filter, index) => (
        <Select
          key={index}
          value={filter.value}
          onValueChange={(value) => onFilterChange?.(filter.label, value)}
        >
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder={filter.label} />
          </SelectTrigger>
          <SelectContent>
            {filter.options.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ))}

      {/* Export — a menu when several formats are offered, else a button. */}
      {showExport &&
        (exportOptions?.length ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" disabled={exportDisabled}>
                Export
                <ChevronDown className="ml-1 h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-64">
              {exportOptions.map((option) => (
                <DropdownMenuItem
                  key={option.id}
                  onSelect={() => onExportOption?.(option.id)}
                  className="flex-col items-start gap-0.5 py-2"
                >
                  <span className="text-sm font-medium">{option.label}</span>
                  {option.description && (
                    <span className="text-xs text-muted-foreground">
                      {option.description}
                    </span>
                  )}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        ) : (
          <Button variant="outline" onClick={onExport} disabled={exportDisabled}>
            Export
          </Button>
        ))}
    </div>
  );
}
