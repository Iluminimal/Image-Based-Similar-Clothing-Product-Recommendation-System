"use client";

import { Switch as SwitchPrimitive } from "radix-ui";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

/**
 * Асаах/унтраах унтраалга. Дармагц шууд хэрэгждэг хоёр утгатай тохиргоонд хэрэглэнэ; "Хадгалах"
 * товчтой маягтын сонголтод checkbox тохиромжтой. Хуруугаар дарах талбай 44px (`after:`).
 */
export function Switch({ className, ...props }: ComponentProps<typeof SwitchPrimitive.Root>) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      className={cn(
        "bg-muted-foreground/60 data-[state=checked]:bg-success focus-visible:ring-ring/50 relative inline-flex h-6 w-10 shrink-0 cursor-pointer items-center rounded-full p-0.5 outline-none transition-colors after:absolute after:-inset-2.5 focus-visible:ring-3 disabled:cursor-wait disabled:opacity-60",
        className,
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb className="block size-5 rounded-full bg-white shadow-sm transition-transform data-[state=checked]:translate-x-4 motion-reduce:transition-none" />
    </SwitchPrimitive.Root>
  );
}
