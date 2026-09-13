import ReactDOM from 'react-dom/client';
import { lazy, Suspense, useEffect, useState } from 'react';
import '@fontsource/dm-sans/latin-400.css';
import '@fontsource/dm-sans/latin-500.css';
import '@fontsource/dm-sans/latin-600.css';
import '@fontsource/manrope/latin-500.css';
import '@fontsource/manrope/latin-600.css';
import '@fontsource/manrope/latin-700.css';
import { PUBLIC_DEMO } from './deployment';
import './styles.css';

const ImmersiveSimulation=lazy(()=>import('./ImmersiveSimulation'));
const App=lazy(()=>import('./App'));
function Workspace(){
  const [immersive,setImmersive]=useState(PUBLIC_DEMO||location.hash==='#simulation');
  useEffect(()=>{const update=()=>setImmersive(PUBLIC_DEMO||location.hash==='#simulation');window.addEventListener('hashchange',update);return()=>window.removeEventListener('hashchange',update)},[]);
  return <Suspense fallback={<div className="loading-screen"><h2>Opening your workspace…</h2></div>}>{immersive?<ImmersiveSimulation/>:<App/>}</Suspense>;
}
ReactDOM.createRoot(document.getElementById('root')!).render(<Workspace />);
