import { api } from './api';
import { PUBLIC_DEMO } from './deployment';

export type SimulationCommand = 'joint_demo' | 'reach_demo' | 'pause' | 'reset';
export type BodyPose = {position: [number, number, number]; quaternion: [number, number, number, number]};
export type ReferenceState = {
  bodies?: Record<string, BodyPose>;
  joints?: Record<string, number> | {name: string; position: number}[];
  mode?: string;
  paused?: boolean;
  running?: boolean;
  simulation_time?: number;
  hardware_verified?: boolean;
  target?: {position: [number, number, number]};
  metrics?: {physics_steps?: number; stop_reason?: string | null; reach?: {actual_endpoint_error_m?: number; endpoint_reached?: boolean}};
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
    return {
      state: async () => physics.state() as ReferenceState,
      command: async value => physics.command(value) as ReferenceState,
      dispose: () => physics.dispose(),
    };
  }
  await api('/session', {role: 'researcher'});
  const controller = new AbortController();
  return {
    state: () => api<ReferenceState>('/sim/reference/state', undefined, controller.signal),
    command: value => api<ReferenceState>('/sim/reference/control', {command: value}, controller.signal),
    dispose: () => controller.abort(),
  };
}
