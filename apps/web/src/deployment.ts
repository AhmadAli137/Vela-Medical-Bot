export const PUBLIC_DEMO = import.meta.env.VITE_PUBLIC_DEMO === '1' || import.meta.env.MODE === 'public';
export const REPOSITORY_URL = import.meta.env.VITE_REPOSITORY_URL || '';
export const SCENE_REVISION = __SCENE_REVISION__;
export const simulationAsset = (filename: 'room.glb' | 'robot.glb' | 'phone.glb' | 'meal_box.glb') => `${PUBLIC_DEMO?'/simulation':'/api/sim/assets'}/${filename}?v=${SCENE_REVISION}`;
export const physicsAsset = (filename: 'reference.xml' | 'reference-descriptors.json') => `/simulation/${filename}?v=${SCENE_REVISION}`;
