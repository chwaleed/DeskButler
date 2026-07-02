import { Loader2 } from "lucide-react";

export type Msg = { role: "user" | "agent"; text: string };

const SUGGESTIONS = [
  "List my Downloads",
  "Move report.pdf to Documents",
  "What's in my Documents folder?",
];

function EmptyState({ onSuggest }: { onSuggest: (s: string) => void }) {
  return (
    <div className="flex flex-col items-center gap-3 pt-[11vh]">
      <svg width="46" height="46" viewBox="0 0 24 24" fill="none">
        <rect x="2.25" y="2.25" width="19.5" height="19.5" rx="6" stroke="var(--accent)" strokeWidth="1.6" />
        <path d="M8 8.5 11.5 12 8 15.5" stroke="var(--accent)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M13.5 15.5H16.5" stroke="var(--accent)" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
      <div className="text-lg font-semibold mt-1">DeskButler</div>
      <div className="text-muted-foreground max-w-[400px] text-center text-pretty">
        Tell it what to do with your files, in plain language. It runs entirely on
        this machine — nothing leaves your computer.
      </div>
      <div className="flex flex-col gap-2 mt-4 w-full max-w-[440px]">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            onClick={() => onSuggest(s)}
            className="text-left bg-card border rounded-lg px-3.5 py-2.5 font-mono text-[12.5px] hover:border-primary transition-colors cursor-pointer"
          >
            <span className="text-muted-foreground/60">› </span>
            {s}
          </button>
        ))}
      </div>
      <div className="font-mono text-[11px] text-muted-foreground/60 mt-3.5">
        local model · no cloud · no account
      </div>
    </div>
  );
}

export function ChatThread({
  messages,
  busy,
  lastStep,
  onSuggest,
}: {
  messages: Msg[];
  busy: boolean;
  lastStep: string;
  onSuggest: (s: string) => void;
}) {
  const empty = messages.length === 0 && !busy;
  return (
    <div className="max-w-[720px] mx-auto flex flex-col gap-[18px]">
      {empty && <EmptyState onSuggest={onSuggest} />}
      {messages.map((m, i) =>
        m.role === "user" ? (
          <div
            key={i}
            className="self-end max-w-[78%] bg-primary/15 border border-primary/30 rounded-[10px_10px_3px_10px] px-3.5 py-2.5 whitespace-pre-wrap break-words"
          >
            {m.text}
          </div>
        ) : (
          <div key={i} className="self-start max-w-[88%] flex flex-col gap-1.5">
            <div className="font-mono text-[10.5px] tracking-[1.2px] uppercase text-primary">
              DeskButler
            </div>
            <div className="whitespace-pre-wrap break-words text-pretty">{m.text}</div>
          </div>
        ),
      )}
      {busy && (
        <div className="flex items-center gap-2.5 text-muted-foreground font-mono text-[12.5px]">
          <Loader2 className="size-3 animate-spin text-primary" />
          <span>{lastStep || "thinking…"}</span>
        </div>
      )}
    </div>
  );
}
