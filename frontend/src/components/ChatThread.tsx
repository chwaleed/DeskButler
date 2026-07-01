type Msg = { role: "user" | "agent"; text: string };

export function ChatThread({ messages }: { messages: Msg[] }) {
  return (
    <div aria-label="chat">
      {messages.map((m, i) => (
        <div key={i} data-role={m.role}>
          <strong>{m.role === "user" ? "You" : "Agent"}:</strong> {m.text}
        </div>
      ))}
    </div>
  );
}
export type { Msg };
