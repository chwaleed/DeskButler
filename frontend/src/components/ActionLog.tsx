export function ActionLog({ steps }: { steps: string[] }) {
  return (
    <div aria-label="action-log">
      <h3>Activity</h3>
      <ul>
        {steps.map((s, i) => (
          <li key={i}>{s}</li>
        ))}
      </ul>
    </div>
  );
}
