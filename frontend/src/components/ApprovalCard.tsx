import { TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";

export type Req = { tool: string; args: Record<string, unknown>; message: string };

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
  return (
    <div className="flex-none px-6 pb-3.5">
      <div className="max-w-[720px] mx-auto border border-warning bg-warning/8 rounded-[10px] p-4">
        <div className="flex items-center gap-2.5 mb-2">
          <TriangleAlert className="size-[18px] text-warning shrink-0" />
          <div className="font-semibold">Approval required</div>
          <div className="font-mono text-[11px] text-warning border border-warning rounded-full px-2.5 py-0.5">
            {request.tool}
          </div>
        </div>
        <div className="mb-2.5 text-pretty">{request.message}</div>
        <div className="font-mono text-xs leading-[1.7] bg-background border rounded-lg px-3.5 py-2.5 mb-3">
          {Object.entries(request.args).map(([k, v]) => (
            <div key={k} className="break-all">
              <span className="text-muted-foreground/60">
                {k}
                {Array.isArray(v) ? ` (${v.length} items)` : ""}
                {": "}
              </span>
              <ArgValue v={v} />
            </div>
          ))}
        </div>
        <div className="flex gap-2.5 items-center">
          <Button
            className="bg-warning text-background hover:bg-warning/90"
            onClick={onApprove}
          >
            Approve
          </Button>
          <Button variant="destructive" onClick={onReject}>
            Reject
          </Button>
          <span className="text-muted-foreground/60 text-xs ml-auto">
            The agent is paused until you decide.
          </span>
        </div>
      </div>
    </div>
  );
}
