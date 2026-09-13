import { Check, Layers3 } from 'lucide-react';
import type { DemoMetrics, PickupMetrics } from './browserPhysicsCore';
import { human } from './api';

const CHECK_LABELS: Record<string, string> = { returned_to_rest: 'Robot at rest', robot_settled: 'Motion settled', visited_bedside: 'Approach reached', base_travel_observed: 'Travel measured', hand_raised: 'Hand raised', wrist_waved: 'Wave measured', confirmed_grasp: 'Grasp confirmed', phone_on_riser: 'Phone on stand', fingers_clear: 'Gripper open', hand_retracted: 'Hand withdrawn' };

export default function SimulationDemoMetrics({ demo, pickup, paused, onBrowse }: { demo: DemoMetrics; pickup?: PickupMetrics; paused: boolean; onBrowse: () => void }) {
  const progress = Math.max(0, Math.min(1, demo.progress));
  const stopped = demo.status === 'stopped';
  const measured = demo.measurements;
  const distance = typeof measured.max_base_excursion_m === 'number' ? measured.max_base_excursion_m : undefined;
  const handHeight = typeof measured.hand_height_m === 'number' ? measured.hand_height_m : undefined;
  return <div className="immersive-action-metrics immersive-extra-demo-metrics" data-testid="demo-metrics" data-command={demo.command} data-status={demo.status} data-complete={demo.complete} data-progress={progress} data-demo-metrics={JSON.stringify(demo)} data-pickup-metrics={JSON.stringify(pickup ?? null)}>
    <span className="immersive-demo-status">{stopped ? 'Stopped' : demo.complete ? 'Task complete' : paused ? 'Paused' : 'Demo in progress'}</span>
    <strong>{demo.name}</strong>
    <div className="immersive-demo-progress" role="progressbar" aria-label="Demo progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress * 100)}><span style={{ width: `${progress * 100}%` }}/></div>
    <dl><div><dt>Stage</dt><dd>{human(demo.stage)}</dd></div><div><dt>Progress</dt><dd>{Math.min(demo.stage_index + 1, demo.stage_count)} / {demo.stage_count}</dd></div><div><dt>Elapsed</dt><dd>{demo.elapsed_s.toFixed(1)} s</dd></div>{distance !== undefined && <div><dt>Farthest travel</dt><dd>{distance.toFixed(2)} m</dd></div>}{handHeight !== undefined && <div><dt>Hand height</dt><dd>{handHeight.toFixed(2)} m</dd></div>}{pickup && <div><dt>Phone lifted</dt><dd>{Math.max(0, pickup.height_gain_m * 100).toFixed(1)} cm</dd></div>}</dl>
    {Object.keys(demo.checks).length > 0 && <div className="immersive-demo-checks">{Object.entries(demo.checks).map(([name, passed]) => <span key={name} data-passed={passed}>{passed ? <Check size={12}/> : <i/>}{CHECK_LABELS[name] ?? human(name)}</span>)}</div>}
    <p>{stopped ? 'The simulation stopped before the task was complete. Start a demo to reset the scene.' : demo.complete ? 'The measured task checks passed. Choose another demo or explore the room.' : 'Completion follows measured robot and object motion.'}</p>
    <button onClick={onBrowse}><Layers3 size={14}/>{demo.complete || stopped ? 'Try another demo' : 'Browse demos'}</button>
  </div>;
}
