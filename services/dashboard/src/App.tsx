import { Header } from "./panels/Header";
import { LiveWorkflow } from "./panels/LiveWorkflow";
import { ModelTimeline } from "./panels/ModelTimeline";
import { ABPanel } from "./panels/ABPanel";
import { ScenarioControls } from "./panels/ScenarioControls";
import { PipelineStatus } from "./panels/PipelineStatus";

export default function App() {
  return (
    <div className="min-h-full bg-bg text-slate-200">
      <div className="mx-auto max-w-[1600px] space-y-4 p-4 sm:p-6">
        <Header />

        <main className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {/* Row 1: live workflow spans full width on xl */}
          <LiveWorkflow />

          {/* Row 2: model timeline + A/B */}
          <ModelTimeline />
          <ABPanel />

          {/* Row 3: scenario cockpit + pipeline */}
          <ScenarioControls />
          <PipelineStatus />
        </main>

        <footer className="pb-2 pt-2 text-center text-[11px] text-slate-600">
          Lenta MVP · dashboard polls every 2s · {import.meta.env.VITE_API_URL ?? "http://localhost:8000"}
        </footer>
      </div>
    </div>
  );
}
