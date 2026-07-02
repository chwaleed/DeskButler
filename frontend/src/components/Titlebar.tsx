import { History, SquarePen, Settings, Eye } from "lucide-react";
import { Button } from "@/components/ui/button";

function Logo({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className="shrink-0">
      <rect x="2.25" y="2.25" width="19.5" height="19.5" rx="6" stroke="var(--accent)" strokeWidth="1.8" />
      <path d="M8 8.5 11.5 12 8 15.5" stroke="var(--accent)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M13.5 15.5H16.5" stroke="var(--accent)" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

export function Titlebar({
  busy,
  dryRun,
  onChats,
  onNewChat,
  onSettings,
}: {
  busy: boolean;
  dryRun: boolean;
  onChats: () => void;
  onNewChat: () => void;
  onSettings: () => void;
}) {
  return (
    <div className="flex items-center gap-3 h-12 px-3.5 border-b bg-card shrink-0">
      <Logo />
      <div className="font-semibold text-sm tracking-tight">DeskButler</div>
      <div className="flex items-center gap-1.5 font-mono text-[11.5px]">
        <span
          className={`size-[7px] rounded-full ${busy ? "bg-primary animate-pulse" : "bg-muted-foreground/50"}`}
        />
        <span className={busy ? "text-muted-foreground" : "text-muted-foreground/60"}>
          {busy ? "working" : "idle"}
        </span>
      </div>
      <div className="flex-1" />
      {dryRun && (
        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-warning/55 bg-warning/10 text-warning font-mono text-[11px] font-medium tracking-wide">
          <Eye className="size-3" />
          DRY RUN — NOTHING WILL BE CHANGED
        </div>
      )}
      <Button variant="outline" size="sm" className="font-mono" onClick={onChats}>
        <History /> chats
      </Button>
      <Button variant="outline" size="sm" className="font-mono" onClick={onNewChat}>
        <SquarePen /> new chat
      </Button>
      <Button variant="outline" size="icon" onClick={onSettings} title="Settings">
        <Settings />
      </Button>
    </div>
  );
}
