import { useEffect, useRef } from 'react';
import { ArrowUpRight, Hand, Route, RotateCcw, Smartphone, Sun, Utensils, X } from 'lucide-react';

export type ExtraDemoCommand = 'bedside_demo' | 'greeting_demo' | 'phone_return_demo' | 'deliver_phone_demo' | 'deliver_meal_demo' | 'blinds_demo';
export const EXTRA_DEMOS = [
  { command: 'deliver_phone_demo', title: 'Bring my phone', action: 'Deliver phone', description: 'Grasp the phone, carry it to the patient, and place it on the bedside tray.', steps: 'Grasp · Carry · Place within reach', view: 'delivery', icon: Smartphone },
  { command: 'deliver_meal_demo', title: 'Bring my meal', action: 'Deliver meal', description: 'Carry a small sealed meal container and set it on the patient’s tray.', steps: 'Pick up · Carry · Serve on tray', view: 'delivery', icon: Utensils },
  { command: 'blinds_demo', title: 'Open the blinds', action: 'Open blinds', description: 'Approach the window and press the blind control to turn the linked slats.', steps: 'Approach · Press control · Let in light', view: 'blinds', icon: Sun },
  { command: 'bedside_demo', title: 'Bedside approach', action: 'Start bedside approach', description: 'Move toward the foot of the bed, pause, and return to the starting point.', steps: 'Approach · Pause · Return', view: 'bedside', icon: Route },
  { command: 'greeting_demo', title: 'Patient greeting', action: 'Start greeting', description: 'Raise one arm, give a short wave, and lower it back to rest.', steps: 'Raise · Wave · Rest', view: 'robot', icon: Hand },
  { command: 'phone_return_demo', title: 'Pick up & put back', action: 'Start phone return', description: 'Lift the phone, hold it, and gently put it back on its stand.', steps: 'Pick up · Hold · Put back', view: 'pickup', icon: Smartphone },
] as const;

export default function SimulationDemoGallery({ ready, onClose, onStart }: { ready: boolean; onClose: () => void; onStart: (command: ExtraDemoCommand) => void }) {
  const dialog = useRef<HTMLElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    dialog.current?.querySelector<HTMLButtonElement>('button')?.focus();
    return () => previous?.focus();
  }, []);
  return <div className="immersive-demo-backdrop" onClick={event => { if (event.target === event.currentTarget) onClose(); }}>
    <section ref={dialog} className="immersive-demo-gallery" role="dialog" aria-modal="true" aria-labelledby="extra-demo-title" aria-describedby="extra-demo-description" onKeyDown={event => {
      if (event.key === 'Escape') { event.preventDefault(); onClose(); }
      if (event.key === 'Tab') {
        const buttons = Array.from(dialog.current?.querySelectorAll<HTMLButtonElement>('button:not([disabled])') ?? []);
        const first = buttons[0], last = buttons.at(-1);
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    }}>
      <div className="immersive-demo-gallery-heading"><div><span className="immersive-kicker">PATIENT ASSISTANCE & MOVEMENT</span><h2 id="extra-demo-title">More to explore.</h2></div><button className="immersive-icon-button" aria-label="Close demos" onClick={onClose}><X size={20}/></button></div>
      <p id="extra-demo-description">Watch the robot move through a complete task, with progress measured in the simulation.</p>
      <div className="immersive-demo-grid">{EXTRA_DEMOS.map((demo, index) => <article className="immersive-demo-card" key={demo.command}>
        <div className="immersive-demo-card-top"><span><demo.icon size={26} strokeWidth={1.5}/></span><small>0{index + 1}</small></div>
        <h3>{demo.title}</h3><p>{demo.description}</p><span className="immersive-demo-steps">{demo.steps}</span>
        <button disabled={!ready} onClick={() => onStart(demo.command)}>{demo.action}<ArrowUpRight size={16}/></button>
      </article>)}</div>
      <p className="immersive-demo-gallery-note"><RotateCcw size={14}/>Each start resets the room. Planned routes and contact physics control these tasks. The patient remains still; meals are placed on the tray.</p>
    </section>
  </div>;
}
