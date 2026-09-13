export const PUBLIC_DEMO = import.meta.env.VITE_PUBLIC_DEMO === '1' || import.meta.env.MODE === 'public';
export const REPOSITORY_URL = import.meta.env.VITE_REPOSITORY_URL || '';
export const simulationAsset = (filename: 'room.glb' | 'robot.glb') => PUBLIC_DEMO ? `/simulation/${filename}` : `/api/sim/assets/${filename}`;
