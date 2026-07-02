import { useState } from "react";
import { Activity, ChevronDown, Trash2 } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";

export type Step = { t: string; text: string; out?: string };

export function ActivityLog({
  steps,
  onClear,
}: {
  steps: Step[];
  onClear: () => void;
}) {
  const [open, setOpen] = useState<Record<number, boolean>>({});

  return (
    <div className="flex flex-col min-h-0 flex-1">
      <div className="flex items-center gap-2 px-4 py-3 border-b shrink-0">
        <Activity className="size-3.5 text-muted-foreground/60" />
        <div className="font-mono text-[11px] tracking-[1.4px] uppercase text-muted-foreground/60">
          Activity
        </div>
        <div className="font-mono text-[11px] text-muted-foreground/60">
          {steps.length || ""}
        </div>
        <div className="flex-1" />
        <Button variant="ghost" size="icon" onClick={onClear} title="Clear log">
          <Trash2 />
        </Button>
      </div>
      <ScrollArea className="flex-1">
        <div className="px-4 py-3 font-mono text-xs leading-[1.75]">
          {steps.length === 0 ? (
            <div className="text-muted-foreground/60 text-pretty">
              Everything the agent does — reads, writes, and pauses — appears here,
              in order.
            </div>
          ) : (
            steps.map((s, i) => (
              <div key={i}>
                <div className="flex gap-2.5 items-baseline">
                  <span className="text-muted-foreground/50 text-[10.5px] shrink-0">
                    {s.t}
                  </span>
                  <span className="text-muted-foreground/60 shrink-0">›</span>
                  <span className="break-all flex-1">{s.text}</span>
                  {s.out && (
                    <button
                      onClick={() => setOpen((o) => ({ ...o, [i]: !o[i] }))}
                      title="Terminal output"
                      className="text-muted-foreground/60 hover:text-foreground cursor-pointer self-center shrink-0"
                    >
                      <ChevronDown
                        className={`size-3 transition-transform ${open[i] ? "rotate-180" : ""}`}
                      />
                    </button>
                  )}
                </div>
                {s.out && open[i] && (
                  <pre className="my-1 ml-5 bg-background border rounded-md px-2.5 py-2 overflow-x-auto text-muted-foreground text-[11px] leading-[1.7] whitespace-pre-wrap break-all">
                    {s.out}
                  </pre>
                )}
              </div>
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
