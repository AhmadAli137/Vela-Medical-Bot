import type {DriveMetrics} from './browserDrive';
import { api } from './api';
import { PUBLIC_DEMO } from './deployment';
import { serializeSimulationTransport } from './serializeSimulationTransport';
import type {PickupMetrics,LiftMetrics,DemoMetrics,CameraPose,PhysicsCommand} from './browserPhysicsCore';

export type SimulationCommand = PhysicsCommand;
export type {CameraPose};
export type BodyPose = {position: [number, number, number]; quaternion: [number, number, number, number]};
export type ReferenceState = {
  bodies?: Record<string, BodyPose>;
  joints?: Record<string, number> | {name: string; position: number}[];
  object_joints?: Record<string,number>;
  cameras?: Record<string,CameraPose>;
  mode?: string;
  paused?: boolean;
  running?: boolean;
  simulation_time?: number;
  hardware_verified?: boolean;
  target?: {position: [number, number, number]};
  metrics?: {drive?:DriveMetrics;physics_steps?: number; stop_reason?: string | null; visual_tracking_pause_reason?:string|null; pickup?:PickupMetrics;lift?:LiftMetrics;demo?:DemoMetrics; reach?: {actual_endpoint_error_m?: number; endpoint_reached?: boolean}};
  [key: string]: unknown;
};

export interface SimulationTransport {
  state(): Promise<ReferenceState>;
  command(value: SimulationCommand): Promise<ReferenceState>;
  dispose(): void;
}

export async function createSimulationTransport(): Promise<SimulationTransport> {
  if (PUBLIC_DEMO) {
    const { createBrowserPhysics } = await import('./browserPhysics');
    const physics = await createBrowserPhysics();
    return serializeSimulationTransport({
      state: async () => physics.state() as ReferenceState,
      command: async value => physics.command(value) as ReferenceState,
      dispose: () => physics.dispose(),
    });
  }
  await api('/session', {role: 'researcher'});
  const controller = new AbortController();
  return serializeSimulationTransport({
    state: () => api<ReferenceState>('/sim/reference/state', undefined, controller.signal),
    command: value => api<ReferenceState>('/sim/reference/control', {command: value}, controller.signal),
    dispose: () => controller.abort(),
  });
}
