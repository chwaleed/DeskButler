import { ChevronLeft } from "lucide-react";
import { ActivityLog, type Step } from "./ActivityLog";
import { SettingsPanel } from "./SettingsPanel";
import { Button } from "@/components/ui/button";
import type { Settings } from "@/api/bridge";

export type RailView = "activity" | "chats" | "settings";

function ChatsPanel({ onClose }: { onClose: () => void }) {
  return (
    <div className="flex flex-col min-h-0 flex-1">
      <div className="flex items-center gap-2.5 px-4 py-2.5 border-b shrink-0">
        <Button variant="ghost" size="sm" className="font-mono px-1.5" onClick={onClose}>
          <ChevronLeft /> activity
        </Button>
        <div className="flex-1" />
        <div className="font-mono text-[11px] tracking-[1.4px] uppercase text-muted-foreground/60">
          Chats
        </div>
      </div>
      <div className="flex-1 p-4 text-muted-foreground/60 text-[12.5px] text-pretty">
        Past chats aren't saved yet. This is where they'll appear once history is
        added.
      </div>
    </div>
  );
}

export function Rail({
  view,
  onView,
  steps,
  onClearLog,
  settings,
  onSettingsChange,
}: {
  view: RailView;
  onView: (v: RailView) => void;
  steps: Step[];
  onClearLog: () => void;
  settings: Settings | null;
  onSettingsChange: (s: Settings) => void;
}) {
  return (
    <div className="w-[340px] flex-none border-l bg-card flex flex-col min-h-0">
      {view === "activity" && <ActivityLog steps={steps} onClear={onClearLog} />}
      {view === "chats" && <ChatsPanel onClose={() => onView("activity")} />}
      {view === "settings" && settings && (
        <SettingsPanel
          settings={settings}
          onClose={() => onView("activity")}
          onChange={onSettingsChange}
        />
      )}
    </div>
  );
}
