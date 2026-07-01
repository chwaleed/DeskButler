type Msg = { role: "user" | "agent"; text: string };

export function ChatThread({ messages }: { messages: Msg[] }) {
  return (
    <div aria-label="chat" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {messages.map((m, i) => {
        const isUser = m.role === "user";
        return (
          <div
            key={i}
            data-role={m.role}
            style={{
              alignSelf: isUser ? "flex-end" : "flex-start",
              maxWidth: "80%",
              padding: "8px 12px",
              borderRadius: 10,
              background: isUser ? "var(--accent)" : "var(--surface)",
              color: isUser ? "#06222e" : "var(--text)",
              border: isUser ? "none" : "1px solid var(--border)",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
            }}
          >
            {m.text}
          </div>
        );
      })}
    </div>
  );
}
export type { Msg };
