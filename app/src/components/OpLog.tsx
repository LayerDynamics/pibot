interface Props {
  lines: string[];
}

export default function OpLog({ lines }: Props) {
  if (lines.length === 0) {
    return null;
  }
  return (
    <pre
      data-testid="op-log"
      className="rounded bg-zinc-950 p-3 text-xs text-zinc-300 font-mono overflow-auto max-h-48 whitespace-pre-wrap"
    >
      {lines.join("\n")}
    </pre>
  );
}
