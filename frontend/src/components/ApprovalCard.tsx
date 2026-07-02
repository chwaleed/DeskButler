import { TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";

export type Req = {
  actions: { tool: string; args: Record<string, unknown> }[];
  message: string;
};

function ArgValue({ v }: { v: unknown }) {
  if (Array.isArray(v)) {
    return (
      <div className="max-h-44 overflow-y-auto mt-1 flex flex-col gap-0.5 border-l-2 border-warning/40 pl-2.5">
        {v.map((item, i) => (
          <div key={i} className="break-all">
            {item !== null && typeof item === "object" && "src" in item
              ? `${(item as { src?: unknown }).src} → ${(item as { dst?: unknown }).dst}`
              : String(item)}
          </div>
        ))}
      </div>
    );
  }
  return <>{String(v)}</>;
}

function ActionRow({
  tool,
  args,
}: {
  tool: string;
  args: Record<string, unknown>;
}) {
  const isMove = "src" in args && "dst" in args;
  return (
    <div className="flex flex-col gap-0.5 py-1.5 first:pt-0 last:pb-0">
      <span className="font-mono text-[10.5px] tracking-wide text-warning">{tool}</span>
      {isMove ? (
        <div className="break-all">
          {String(args.src)} <span className="text-muted-foreground/60">→</span>{" "}
          {String(args.dst)}
        </div>
      ) : (
        Object.entries(args).map(([k, v]) => (
          <div key={k} className="break-all">
            <span className="text-muted-foreground/60">
              {k}
              {Array.isArray(v) ? ` (${v.length} items)` : ""}
              {": "}
            </span>
            <ArgValue v={v} />
          </div>
        ))
      )}
    </div>
  );
}

export function ApprovalCard({
  request,
  onApprove,
  onReject,
}: {
  request: Req | null;
  onApprove: () => void;
  onReject: () => void;
}) {
  if (!request) return null;
  const { actions, message } = request;
  const many = actions.length > 1;
  return (
    <div className="flex-none px-6 pb-3.5">
      <div className="max-w-[720px] mx-auto border border-warning bg-warning/8 rounded-[10px] p-4">
        <div className="flex items-center gap-2.5 mb-2">
          <TriangleAlert className="size-[18px] text-warning shrink-0" />
          <div className="font-semibold">Approval required</div>
          <div className="font-mono text-[11px] text-warning border border-warning rounded-full px-2.5 py-0.5">
            {actions.length} action{many ? "s" : ""}
          </div>
        </div>
        <div className="mb-2.5 text-pretty">{message}</div>
        <div className="font-mono text-xs leading-[1.7] bg-background border rounded-lg px-3.5 py-2.5 mb-3 max-h-56 overflow-y-auto divide-y divide-border/50">
          {actions.map((a, i) => (
            <ActionRow key={i} tool={a.tool} args={a.args} />
          ))}
        </div>
        <div className="flex gap-2.5 items-center">
          <Button
            className="bg-warning text-background hover:bg-warning/90"
            onClick={onApprove}
          >
            Approve{many ? " all" : ""}
          </Button>
          <Button variant="destructive" onClick={onReject}>
            Reject{many ? " all" : ""}
          </Button>
          <span className="text-muted-foreground/60 text-xs ml-auto">
            The agent is paused until you decide.
          </span>
        </div>
      </div>
    </div>
  );
}
