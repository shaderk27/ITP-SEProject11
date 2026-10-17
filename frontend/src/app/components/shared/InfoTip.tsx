import { Info } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";

interface InfoTipProps {
  /** What the term means, shown on hover / keyboard focus. */
  text: string;
  /** Term being explained, used for the screen-reader label. */
  label: string;
}

// Small "i" icon that explains a dashboard term. A real button so keyboard
// users can tab to it; hidden when printing so it doesn't clutter PDF exports.
export function InfoTip({ text, label }: InfoTipProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label={`What is ${label}?`}
          className="inline-flex items-center align-middle text-muted-foreground hover:text-foreground focus-visible:text-foreground focus-visible:outline-none print:hidden"
        >
          <Info className="h-3.5 w-3.5" />
        </button>
      </TooltipTrigger>
      <TooltipContent sideOffset={4} className="max-w-xs text-left font-normal">
        {text}
      </TooltipContent>
    </Tooltip>
  );
}
