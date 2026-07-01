type Req = { tool: string; args: Record<string, unknown>; message: string };

export function ApprovalModal({
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
    <div
      role="dialog"
      aria-label="approval"
      style={{
        margin: "10px 0",
        padding: 14,
        borderRadius: 10,
        border: "1px solid var(--warn)",
        background: "rgba(245, 166, 35, 0.08)",
      }}
    >
      <div style={{ color: "var(--warn)", fontWeight: 600, marginBottom: 6 }}>
        ⚠ {request.message}
      </div>
      <div style={{ fontFamily: "ui-monospace, Consolas, monospace", fontSize: 13, marginBottom: 12, wordBreak: "break-all" }}>
        <strong>{request.tool}</strong>
        {Object.entries(request.args).map(([k, v]) => (
          <div key={k} style={{ color: "var(--muted)" }}>
            {k}: {String(v)}
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <button style={{ background: "var(--warn)", color: "#2a1c00" }} onClick={onApprove}>
          Approve
        </button>
        <button
          style={{ background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)" }}
          onClick={onReject}
        >
          Reject
        </button>
      </div>
    </div>
  );
}
export type { Req };
