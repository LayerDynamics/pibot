import VideoCanvas from "../components/VideoCanvas";
import { useTelemetryStore } from "../stores/telemetryStore";

function Metric({ label, value, unit }: { label: string; value: unknown; unit?: string }) {
  const shown = value === null || value === undefined ? "—" : `${value}${unit ?? ""}`;
  return (
    <div className="rounded-md bg-zinc-900 px-3 py-2">
      <div className="text-xs uppercase tracking-wide text-zinc-500">{label}</div>
      <div className="text-lg tabular-nums">{shown}</div>
    </div>
  );
}

export default function Dashboard() {
  const snapshot = useTelemetryStore((s) => s.snapshot);
  const alerts = useTelemetryStore((s) => s.alerts);

  if (!snapshot) {
    return (
      <div data-testid="dashboard-empty" className="text-zinc-500">
        No telemetry yet — connect to a robot.
      </div>
    );
  }

  const pi = snapshot.pi ?? {};
  const battery = snapshot.robot?.battery?.volts;
  const policy = snapshot.policy;
  const policyLabel =
    policy?.connected == null ? "—" : policy.connected ? "up" : "down";

  return (
    <div data-testid="dashboard" className="flex flex-col gap-4">
      <VideoCanvas />
      {alerts.length > 0 && (
        <div
          data-testid="alerts"
          className="rounded-md border border-red-700 bg-red-950/50 p-3 text-red-200"
        >
          {alerts.map((a) => (
            <div key={a}>⚠ {a}</div>
          ))}
        </div>
      )}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Metric label="Temp" value={pi.temp_c} unit="°C" />
        <Metric label="CPU" value={pi.cpu_pct} unit="%" />
        <Metric label="Mem" value={pi.mem_pct} unit="%" />
        <Metric label="Battery" value={battery} unit="V" />
        <Metric label="Transport" value={snapshot.transport?.open ? "up" : "down"} />
        <Metric label="E-Stop" value={snapshot.safety?.estop ? "LATCHED" : "clear"} />
        <Metric label="Policy" value={policyLabel} />
        <Metric label="Infer" value={policy?.last_inference_ms} unit="ms" />
      </div>
    </div>
  );
}
