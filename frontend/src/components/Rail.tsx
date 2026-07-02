import { ChevronLeft } from "lucide-react";
import { ActivityLog, type Step } from "./ActivityLog";
import { SettingsPanel } from "./SettingsPanel";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { ChatMeta, Settings } from "@/api/bridge";

export type RailView = "activity" | "chats" | "settings";

function ChatsPanel({
  chats,
  onOpen,
  onClose,
}: {
  chats: ChatMeta[];
  onOpen: (id: string) => void;
  onClose: () => void;
}) {
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
      <ScrollArea className="flex-1">
        <div className="p-2 flex flex-col gap-1">
          {chats.length === 0 ? (
            <div className="text-muted-foreground/60 text-[12.5px] p-2 text-pretty">
              No past chats yet. Your conversations are saved here automatically.
            </div>
          ) : (
            chats.map((c) => (
              <button
                key={c.id}
                onClick={() => onOpen(c.id)}
                className="flex flex-col gap-0.5 items-stretch text-left rounded-md px-2.5 py-2 cursor-pointer border border-transparent hover:bg-background hover:border-border min-w-0"
              >
                <span className="text-[13px] truncate">{c.title}</span>
                <span className="font-mono text-[10.5px] text-muted-foreground/60">
                  {new Date(c.updated * 1000).toLocaleString()}
                </span>
              </button>
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  );
}

export function Rail({
  view,
  onView,
  steps,
  onClearLog,
  chats,
  onOpenChat,
  settings,
  onSettingsChange,
}: {
  view: RailView;
  onView: (v: RailView) => void;
  steps: Step[];
  onClearLog: () => void;
  chats: ChatMeta[];
  onOpenChat: (id: string) => void;
  settings: Settings | null;
  onSettingsChange: (s: Settings) => void;
}) {
  return (
    <div className="w-[340px] flex-none border-l bg-card flex flex-col min-h-0">
      {view === "activity" && <ActivityLog steps={steps} onClear={onClearLog} />}
      {view === "chats" && (
        <ChatsPanel chats={chats} onOpen={onOpenChat} onClose={() => onView("activity")} />
      )}
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
