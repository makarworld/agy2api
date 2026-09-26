import * as React from "react"
import { Input as InputPrimitive } from "@base-ui/react/input"

import { cn } from "@/lib/utils"

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <InputPrimitive
      type={type}
      data-slot="input"
      className={cn(
        "h-9 w-full min-w-0 rounded-lg border border-border/80 bg-muted/30 px-3 py-1.5 text-sm transition-all duration-150 outline-none file:inline-flex file:h-6 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground/60 shadow-xs hover:border-zinc-500/40 hover:bg-muted/50 focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/20 focus-visible:bg-background disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-2 aria-invalid:ring-destructive/20 dark:border-border/60 dark:bg-zinc-950/50 dark:hover:border-zinc-700 dark:hover:bg-zinc-900/60 dark:focus-visible:bg-zinc-950 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40",
        className
      )}
      {...props}
    />
  )
}

export { Input }
