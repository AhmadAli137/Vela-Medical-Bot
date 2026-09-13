import { useState } from 'react';
import { ArrowUpRight, Monitor, LoaderCircle } from 'lucide-react';
import { api } from './api';
import { PUBLIC_DEMO, REPOSITORY_URL } from './deployment';
import './workspace-guide.css';

const surfaces = [
  ['staff', 'Room operations', 'Review requests, room snapshots and approval steps.'],
  ['patient', 'Patient experience', 'Try patient requests and see how they are routed.'],
  ['fleet', 'Robot & fleet', 'Inspect mock robot status, permissions and correction sessions.'],
  ['research', 'Research studio', 'Inspect evidence, benchmarks and the offline learning workflow.'],
] as const;

export default function WorkspaceGuide({ onNavigate, canOpenNative = true }: { onNavigate?: () => void; canOpenNative?: boolean }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const openNative = async () => {
    setBusy(true); setMessage('');
    try {
      const result = await api('/sim/viewer', {});
      setMessage(result.status === 'starting' ? 'The MuJoCo window is starting on this computer.' : 'The MuJoCo window shares this local simulation. Controls in either window affect the same robot.');
    } catch (error) { setMessage((error as Error).message); }
    finally { setBusy(false); }
  };
  return <div className="workspace-guide">
    <p>Vela is one project with a simulation and four workflow screens. Start with the simulation to watch the robot move.</p>
    <div className="workspace-guide-feature">
      <strong>Simulation studio</strong>
      <p>The furnished room, patient, robot, camera views and assistance demos. MuJoCo computes motion and contact; Three.js draws the detailed scene.</p>
      <a href="#simulation" onClick={onNavigate}>Open simulation<ArrowUpRight size={15}/></a>
    </div>
    <div className="workspace-guide-feature">
      <strong>Native MuJoCo window</strong>
      <p>The same room assets, robot model and demos in MuJoCo's desktop renderer. Its lighting differs. When opened from the local workspace, it shares the browser's running simulation.</p>
      {PUBLIC_DEMO ? <p className="workspace-guide-note">Available on your computer through Open Native Simulation.cmd. The public website cannot open desktop apps.</p> : canOpenNative ? <button className="button secondary" disabled={busy} onClick={openNative}>{busy ? <LoaderCircle size={15} className="spin"/> : <Monitor size={15}/>}Open native MuJoCo</button> : <a href="#simulation" onClick={onNavigate}>Open Simulation studio to launch the native viewer<ArrowUpRight size={15}/></a>}
      {message && <p role="status">{message}</p>}
    </div>
    <h3>The local workspace</h3>
    <p>These four screens use a mock task database. Their room diagram and task completions are separate from the physical 3D demos; a patient request does not yet drive the simulated robot.</p>
    <div className="workspace-guide-surfaces">{surfaces.map(([route, title, description]) => <div key={route}>
      {PUBLIC_DEMO ? <strong>{title}</strong> : <a href={`#${route}`} onClick={onNavigate}>{title}<ArrowUpRight size={14}/></a>}
      <p>{description}</p>
    </div>)}</div>
    <p className="workspace-guide-note">{PUBLIC_DEMO ? 'You are using the public demo. Each browser tab runs its own physics session. Local workspace services and desktop windows run on your computer.' : 'You are using the local workspace. Browser views and a native window opened here share one physics session. The Vercel demo and a standalone command-line viewer run independent sessions.'}</p>
    <p className="workspace-guide-note">The older randomized room remains an explicitly labeled research benchmark. No physical robot or hospital is connected.</p>
    {REPOSITORY_URL && <a href={REPOSITORY_URL} target="_blank" rel="noreferrer">View the project<ArrowUpRight size={15}/></a>}
  </div>;
}
