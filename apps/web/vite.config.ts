import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import {createHash} from 'node:crypto';
import {existsSync,readFileSync} from 'node:fs';

const sceneHash=createHash('sha256');
for(const path of ['../../assets/simulation/room.glb','../../assets/simulation/robot.glb','../../assets/simulation/phone.glb','../../assets/simulation/meal_box.glb','public/simulation/reference.xml','public/simulation/reference-descriptors.json']){
  const file=new URL(path,import.meta.url);
  sceneHash.update(path);
  if(existsSync(file))sceneHash.update(readFileSync(file));
}

export default defineConfig({
  plugins: [react()],
  define: {__SCENE_REVISION__: JSON.stringify(sceneHash.digest('hex').slice(0,16))},
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
  preview: { proxy: { '/api': 'http://127.0.0.1:8000' } },
});
