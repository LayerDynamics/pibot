import type { Episode } from "../lib/api/types";

interface Props {
  episodes: Episode[];
  onSelect?: (ep: Episode) => void;
}

export default function EpisodeList({ episodes, onSelect }: Props) {
  if (episodes.length === 0) {
    return (
      <p className="text-xs text-zinc-500" data-testid="episode-list-empty">
        No episodes recorded yet.
      </p>
    );
  }
  return (
    <ul className="flex flex-col gap-1" data-testid="episode-list">
      {episodes.map((ep) => (
        <li
          key={ep.id}
          className="flex items-center gap-3 rounded bg-zinc-800 px-3 py-2 text-sm cursor-pointer hover:bg-zinc-700"
          onClick={() => onSelect?.(ep)}
        >
          <span className="font-mono text-xs text-zinc-400 w-24 shrink-0">{ep.id}</span>
          <span className="flex-1 truncate text-zinc-200">{ep.task}</span>
          <span className="text-xs text-zinc-500">{ep.length} frames</span>
        </li>
      ))}
    </ul>
  );
}
