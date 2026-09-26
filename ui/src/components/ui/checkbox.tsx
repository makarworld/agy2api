import * as React from "react"
import { Checkbox as CheckboxPrimitive } from "@base-ui/react/checkbox"
import { Check } from "lucide-react"

import { cn } from "@/lib/utils"

function Checkbox({
  className,
  ...props
}: React.ComponentProps<typeof CheckboxPrimitive.Root>) {
  return (
    <CheckboxPrimitive.Root
      data-slot="checkbox"
      className={cn(
        "peer size-4.5 shrink-0 rounded-md border border-border/80 bg-muted/30 transition-all duration-150 outline-none flex items-center justify-center cursor-pointer shadow-xs hover:border-zinc-500/40 hover:bg-muted/50 focus-visible:ring-2 focus-visible:ring-primary/20 focus-visible:border-primary disabled:cursor-not-allowed disabled:opacity-50 data-[checked]:bg-primary data-[checked]:border-primary data-[checked]:text-primary-foreground dark:border-border/60 dark:bg-zinc-950/50 dark:hover:border-zinc-700 dark:data-[checked]:bg-primary dark:data-[checked]:border-primary",
        className
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator className="flex items-center justify-center text-current">
        <Check className="size-3.5 stroke-[2.5]" />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  )
}

export { Checkbox }
