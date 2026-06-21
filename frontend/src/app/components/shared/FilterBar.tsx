import { Search } from "lucide-react";
import { Input } from "../ui/input";
import { Button } from "../ui/button";
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
  }[];
  onSearchChange?: (value: string) => void;
  onFilterChange?: (filterId: string, value: string) => void;
  showExport?: boolean;
  onExport?: () => void;
}

export function FilterBar({
  searchPlaceholder = "Search...",
  filters = [],
  onSearchChange,
  onFilterChange,
  showExport = false,
  onExport,
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

      {/* Export button */}
      {showExport && (
        <Button variant="outline" onClick={onExport}>
          Export
        </Button>
      )}
    </div>
  );
}
