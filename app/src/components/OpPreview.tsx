import type { OpsJob } from "../stores/opsStore";
import OpLog from "./OpLog";

interface Props {
  job: OpsJob;
}

export default function OpPreview({ job }: Props) {
  return (
    <div className="flex flex-col gap-2" data-testid="op-preview">
      <p className="text-sm text-zinc-300">
        Dry-run preview for <span className="font-medium text-white">{job.kind}</span>:
      </p>
      <OpLog lines={job.log} />
    </div>
  );
}
