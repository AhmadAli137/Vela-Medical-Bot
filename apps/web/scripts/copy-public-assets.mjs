import {copyFile, mkdir, stat} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {dirname, resolve} from 'node:path';

const webRoot=resolve(dirname(fileURLToPath(import.meta.url)), '..');
const destination=resolve(webRoot, 'dist/simulation');
await mkdir(destination, {recursive: true});
for (const filename of ['room.glb', 'robot.glb']) {
  const source=resolve(webRoot, '../../assets/simulation', filename);
  const information=await stat(source);
  if (!information.size) throw new Error(`Empty simulation asset: ${filename}`);
  await copyFile(source, resolve(destination, filename));
  console.log(`Copied ${filename} (${information.size} bytes)`);
}
for (const filename of ['reference.xml', 'reference-descriptors.json']) {
  const information=await stat(resolve(destination, filename));
  if (!information.size) throw new Error(`Missing browser physics fixture: ${filename}`);
}
