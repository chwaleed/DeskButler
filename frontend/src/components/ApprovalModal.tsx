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
    <div role="dialog" aria-label="approval" style={{ border: "1px solid", padding: 16 }}>
      <p>{request.message}</p>
      <p>
        <strong>{request.tool}</strong>: {JSON.stringify(request.args)}
      </p>
      <button onClick={onApprove}>Approve</button>
      <button onClick={onReject}>Reject</button>
    </div>
  );
}
export type { Req };
