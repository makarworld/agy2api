import * as React from "react"
import { ChevronDown } from "lucide-react"

import { cn } from "@/lib/utils"

interface SelectProps extends React.ComponentProps<"select"> {
  wrapperClassName?: string
}

function Select({ className, wrapperClassName, children, disabled, ...props }: SelectProps) {
  return (
    <div className={cn("relative inline-flex items-center w-full", wrapperClassName)}>
      <select
        data-slot="select"
        disabled={disabled}
        className={cn(
          "appearance-none h-9 w-full min-w-0 rounded-lg border border-border/80 bg-muted/30 pl-3 pr-8 py-1.5 text-sm transition-all duration-150 outline-none shadow-xs cursor-pointer hover:border-zinc-500/40 hover:bg-muted/50 focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/20 focus-visible:bg-background disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 dark:border-border/60 dark:bg-zinc-950/50 dark:hover:border-zinc-700 dark:hover:bg-zinc-900/60 dark:focus-visible:bg-zinc-950 [&>option]:bg-card [&>option]:text-card-foreground dark:[&>option]:bg-zinc-900 dark:[&>option]:text-zinc-100",
          className
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 size-4 text-muted-foreground/70 shrink-0" />
    </div>
  )
}

export { Select }
