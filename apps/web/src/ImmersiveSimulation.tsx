import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowUpRight, Box, Check, ChevronDown, ChevronRight, CircleHelp, Expand, Focus, Layers3, LoaderCircle, Move3D, Orbit, Pause, Play, RotateCcw, ShieldCheck, SlidersHorizontal, Sun, X } from 'lucide-react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { SSAOPass } from 'three/examples/jsm/postprocessing/SSAOPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';
import { human } from './api';
import { PUBLIC_DEMO, REPOSITORY_URL, simulationAsset } from './deployment';
import { createSimulationTransport, type ReferenceState, type SimulationCommand, type SimulationTransport } from './simulationTransport';
import './immersive.css';

type ViewName='overview'|'bedside'|'robot';
type ViewerApi={setView:(name:ViewName)=>void;setQuality:(value:boolean)=>void;resetCamera:()=>void};
const PRESETS:Record<ViewName,{position:[number,number,number];target:[number,number,number];label:string}>={
  overview:{position:[6.8,-8.8,6.4],target:[0,.25,.95],label:'Room overview'},
  bedside:{position:[4.2,-4.7,2.75],target:[.85,.9,1.02],label:'At the bedside'},
  robot:{position:[1.2,-3.45,1.92],target:[-.55,-.62,1.05],label:'Robot detail'},
};

export default function ImmersiveSimulation(){
  const mount=useRef<HTMLDivElement>(null);
  const viewer=useRef<ViewerApi|undefined>(undefined);
  const latest=useRef<ReferenceState|undefined>(undefined);
  const [state,setState]=useState<ReferenceState>();
  const [connected,setConnected]=useState(false);
  const [assets,setAssets]=useState({room:false,robot:false});
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [view,setView]=useState<ViewName>('bedside');
  const [busy,setBusy]=useState(false);
  const [quality,setQuality]=useState(true);
  const [showDetails,setShowDetails]=useState(false);
  const [showHelp,setShowHelp]=useState(false);
  const [showAbout,setShowAbout]=useState(false);
  const aboutDialog=useRef<HTMLElement>(null);
  const [fps,setFps]=useState<number>();
  const [bodyCount,setBodyCount]=useState(0);
  const [ready,setReady]=useState(false);
  const transport=useRef<SimulationTransport|undefined>(undefined);
  const command=useCallback(async(value:SimulationCommand)=>{
    setBusy(true);setError('');
    try{if(!transport.current)throw new Error('The physics engine is still loading.');const result=await transport.current.command(value);if(result.bodies){latest.current=result;setState(result)}setNotice(value==='reset'?'Simulation returned to its starting state.':value==='joint_demo'?'Joint movement demonstration started.':value==='reach_demo'?'Table reach demonstration started.':'Simulation playback updated.')}
    catch(e){setError((e as Error).message)}finally{setBusy(false)}
  },[]);

  useEffect(()=>{
    let cancelled=false;let timer:number;let runtime:SimulationTransport|undefined;let uiAt=0;
    const tick=async()=>{
      if(cancelled||!runtime)return;
      const started=performance.now();
      try{
        const incoming=await runtime.state();
        if(!cancelled){latest.current=incoming;setConnected(true);if(performance.now()-uiAt>250){setState(incoming);uiAt=performance.now()}}
      }catch(e){if(!cancelled){setConnected(false);setError((e as Error).message)}}
      finally{if(!cancelled)timer=window.setTimeout(tick,Math.max(0,50-(performance.now()-started)))}
    };
    createSimulationTransport().then(engine=>{if(cancelled){engine.dispose();return}runtime=engine;transport.current=engine;tick()}).catch(e=>{if(!cancelled)setError(`Physics could not start: ${(e as Error).message}`)});
    return()=>{cancelled=true;window.clearTimeout(timer);runtime?.dispose();transport.current=undefined};
  },[]);

  useEffect(()=>{
    if(!mount.current)return;
    const element=mount.current;
    let disposed=false;let frame=0;let uiAt=0;let frameCount=0;let sampleAt=performance.now();let smoothAt=performance.now();
    const retryTimers:number[]=[];const objects=new Map<string,THREE.Object3D>();
    let renderer:THREE.WebGLRenderer;
    try{renderer=new THREE.WebGLRenderer({antialias:true,alpha:false,powerPreference:'high-performance'})}
    catch{setError('WebGL could not start. Enable hardware acceleration in your browser to open this scene.');return}
    renderer.setPixelRatio(Math.min(window.devicePixelRatio,1.5));
    renderer.setSize(element.clientWidth,element.clientHeight);
    renderer.outputColorSpace=THREE.SRGBColorSpace;
    renderer.toneMapping=THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure=.98;
    renderer.shadowMap.enabled=true;
    renderer.shadowMap.type=THREE.PCFSoftShadowMap;
    renderer.domElement.setAttribute('aria-label','Interactive 3D hospital room and reference robot. Drag to orbit, scroll to zoom, or use the camera view controls.');
    renderer.domElement.setAttribute('role','img');
    renderer.domElement.tabIndex=0;
    element.appendChild(renderer.domElement);
    const scene=new THREE.Scene();
    scene.background=new THREE.Color('#edf0ea');
    scene.fog=new THREE.Fog('#edf0ea',24,70);
    const camera=new THREE.PerspectiveCamera(38,element.clientWidth/element.clientHeight,.025,100);
    camera.up.set(0,0,1);
    camera.position.fromArray(PRESETS.bedside.position);
    const controls=new OrbitControls(camera,renderer.domElement);
    controls.target.fromArray(PRESETS.bedside.target);
    controls.enableDamping=true;controls.dampingFactor=.075;controls.minDistance=1.1;controls.maxDistance=23;
    controls.maxPolarAngle=Math.PI/2-.025;controls.minPolarAngle=.12;controls.enablePan=true;
    controls.mouseButtons={LEFT:THREE.MOUSE.ROTATE,MIDDLE:THREE.MOUSE.DOLLY,RIGHT:THREE.MOUSE.PAN};
    controls.update();
    const pmrem=new THREE.PMREMGenerator(renderer);
    const environment=new RoomEnvironment();
    const envTexture=pmrem.fromScene(environment,.04).texture;
    scene.environment=envTexture;scene.environmentIntensity=.68;
    environment.dispose();pmrem.dispose();
    const hemi=new THREE.HemisphereLight('#e9f3ff','#c8bcaa',1.35);hemi.position.set(0,0,8);scene.add(hemi);
    const sunlight=new THREE.DirectionalLight('#fff4dd',3.0);
    sunlight.position.set(-3.9,1.5,9.0);sunlight.target.position.set(.5,-1.8,0);scene.add(sunlight.target);
    sunlight.castShadow=true;sunlight.shadow.mapSize.set(2048,2048);sunlight.shadow.camera.left=-7;sunlight.shadow.camera.right=7;sunlight.shadow.camera.top=7;sunlight.shadow.camera.bottom=-7;sunlight.shadow.camera.near=.1;sunlight.shadow.camera.far=30;sunlight.shadow.bias=-.0012;sunlight.shadow.normalBias=.025;sunlight.shadow.radius=3;scene.add(sunlight);
    const fill=new THREE.DirectionalLight('#dcebf2',.75);fill.position.set(4,-6,5);scene.add(fill);
    const ground=new THREE.Mesh(new THREE.PlaneGeometry(200,200),new THREE.MeshStandardMaterial({color:'#e5e8df',roughness:.94}));ground.position.z=-.095;ground.receiveShadow=true;scene.add(ground);
    const temporaryFloor=new THREE.Mesh(new THREE.BoxGeometry(7,6,.12),new THREE.MeshStandardMaterial({color:'#e6e3da',roughness:.84}));temporaryFloor.position.z=-.055;temporaryFloor.receiveShadow=true;scene.add(temporaryFloor);
    const targetMarker=new THREE.Group();
    targetMarker.add(new THREE.Mesh(new THREE.SphereGeometry(.025,16,12),new THREE.MeshBasicMaterial({color:'#38a877',transparent:true,opacity:.85})));
    targetMarker.add(new THREE.Mesh(new THREE.TorusGeometry(.065,.003,8,40),new THREE.MeshBasicMaterial({color:'#3baf7e',transparent:true,opacity:.8})));
    targetMarker.visible=false;scene.add(targetMarker);
    const composer=new EffectComposer(renderer);
    composer.addPass(new RenderPass(scene,camera));
    const ssao=new SSAOPass(scene,camera,element.clientWidth,element.clientHeight);
    ssao.kernelRadius=.22;ssao.minDistance=.0001;ssao.maxDistance=.035;
    composer.addPass(ssao);composer.addPass(new OutputPass());
    const desiredCamera=new THREE.Vector3().fromArray(PRESETS.overview.position);
    const desiredTarget=new THREE.Vector3().fromArray(PRESETS.overview.target);
    let cameraMoving=false;
    const stopCamera=()=>{cameraMoving=false};controls.addEventListener('start',stopCamera);
    const selectView=(name:ViewName)=>{desiredCamera.fromArray(PRESETS[name].position);desiredTarget.fromArray(PRESETS[name].target);cameraMoving=true};
    viewer.current={setView:selectView,setQuality:value=>{ssao.enabled=value;renderer.setPixelRatio(value?Math.min(window.devicePixelRatio,1.5):1);renderer.setSize(element.clientWidth,element.clientHeight);composer.setSize(element.clientWidth,element.clientHeight)},resetCamera:()=>selectView('overview')};
    const loader=new GLTFLoader();
    const load=async(kind:'room'|'robot')=>{
      if(disposed)return;
      if(!PUBLIC_DEMO&&!transport.current){retryTimers.push(window.setTimeout(()=>load(kind),150));return}
      try{
        // GLBs preserve native Z-up. Their mesh geometry is local to the named physics body.
        const gltf=await loader.loadAsync(simulationAsset(`${kind}.glb`));
        if(disposed){gltf.scene.traverse(disposeObject);return}
        gltf.scene.name=`${kind}_asset_root`;
        gltf.scene.traverse(node=>{
          if(kind==='robot'&&node.name)objects.set(node.name,node);
          if(node instanceof THREE.Mesh){
            const materials=Array.isArray(node.material)?node.material:[node.material];
            node.castShadow=!materials.some(material=>material.transparent&&material.opacity<.6);
            node.receiveShadow=true;
            materials.forEach(material=>{if(material instanceof THREE.MeshStandardMaterial){material.envMapIntensity=.8;material.needsUpdate=true}});
          }
        });
        scene.add(gltf.scene);
        if(kind==='room'){scene.remove(temporaryFloor);temporaryFloor.geometry.dispose();(temporaryFloor.material as THREE.Material).dispose()}
        setAssets(current=>({...current,[kind]:true}));
      }catch{
        if(!disposed)retryTimers.push(window.setTimeout(()=>load(kind),4000));
      }
    };
    load('room');load('robot');
    const targetPosition=new THREE.Vector3(),targetQuaternion=new THREE.Quaternion(),parentQuaternion=new THREE.Quaternion();
    const resize=new ResizeObserver(()=>{
      if(!element.clientWidth||!element.clientHeight)return;
      camera.aspect=element.clientWidth/element.clientHeight;camera.updateProjectionMatrix();
      renderer.setSize(element.clientWidth,element.clientHeight);composer.setSize(element.clientWidth,element.clientHeight);
    });resize.observe(element);
    function disposeObject(node:THREE.Object3D){if(node instanceof THREE.Mesh){node.geometry.dispose();(Array.isArray(node.material)?node.material:[node.material]).forEach(material=>{for(const value of Object.values(material))if(value instanceof THREE.Texture)value.dispose();material.dispose()})}}
    function animate(){
      if(disposed)return;
      frame=requestAnimationFrame(animate);
      if(document.hidden)return;
      const now=performance.now();const dt=Math.min(.1,(now-smoothAt)/1000);smoothAt=now;
      const alpha=1-Math.exp(-22*dt);
      if(cameraMoving){camera.position.lerp(desiredCamera,.075);controls.target.lerp(desiredTarget,.075);if(camera.position.distanceTo(desiredCamera)<.003)cameraMoving=false}
      scene.updateMatrixWorld(true);
      targetMarker.visible=latest.current?.mode==='reach_demo'&&!!latest.current.target?.position;
      if(latest.current?.target?.position)targetMarker.position.fromArray(latest.current.target.position);
      let matches=0;
      for(const [name,pose]of Object.entries(latest.current?.bodies??{})){
        const object=objects.get(name);
        if(!object||!pose.position||!pose.quaternion)continue;
        targetPosition.fromArray(pose.position);
        targetQuaternion.set(pose.quaternion[1],pose.quaternion[2],pose.quaternion[3],pose.quaternion[0]);
        if(object.parent){object.parent.worldToLocal(targetPosition);object.parent.getWorldQuaternion(parentQuaternion);targetQuaternion.premultiply(parentQuaternion.invert())}
        object.position.lerp(targetPosition,alpha);object.quaternion.slerp(targetQuaternion,alpha);object.updateMatrixWorld(true);matches++;
      }
      controls.update();composer.render();frameCount++;
      if(now-uiAt>500){setBodyCount(matches);uiAt=now}
      if(now-sampleAt>1000){setFps(Math.round(frameCount*1000/(now-sampleAt)));frameCount=0;sampleAt=now}
    }
    animate();setReady(true);
    return()=>{
      disposed=true;cancelAnimationFrame(frame);retryTimers.forEach(clearTimeout);resize.disconnect();controls.dispose();scene.traverse(disposeObject);envTexture.dispose();ssao.dispose();composer.dispose();renderer.dispose();renderer.domElement.remove();viewer.current=undefined;
    };
  },[]);

  useEffect(()=>{if(!notice)return;const timer=window.setTimeout(()=>setNotice(''),4500);return()=>window.clearTimeout(timer)},[notice]);
  useEffect(()=>{
    if(!showAbout||!aboutDialog.current)return;
    const previous=document.activeElement as HTMLElement|null;
    const dialog=aboutDialog.current;
    const focusable=()=>Array.from(dialog.querySelectorAll<HTMLElement>('button:not([disabled]), a[href]'));
    focusable()[0]?.focus();
    const onKey=(event:KeyboardEvent)=>{
      if(event.key==='Escape'){event.preventDefault();setShowAbout(false)}
      if(event.key==='Tab'){
        const items=focusable(),first=items[0],last=items.at(-1);
        if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus()}
        else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus()}
      }
    };
    dialog.addEventListener('keydown',onKey);
    return()=>{dialog.removeEventListener('keydown',onKey);previous?.focus()};
  },[showAbout]);
  const chooseView=(name:ViewName)=>{setView(name);viewer.current?.setView(name)};
  const paused=state?.paused??(state?.running===false);
  const joints=Array.isArray(state?.joints)?state.joints.map(item=>[item.name,item.position] as const):Object.entries(state?.joints??{});
  const loaded=assets.room&&assets.robot;
  const runningLabel=!connected?'Connecting':state?.metrics?.stop_reason?'Contact stop':paused?'Paused':state?.mode==='idle'?'Ready':human(state?.mode??'Live physics');
  return <div className="immersive-shell">
    <header className="immersive-header">{PUBLIC_DEMO?<button className="immersive-back" aria-label="About this demo" onClick={()=>setShowAbout(true)}><CircleHelp size={17}/></button>:<a href="#research" className="immersive-back" aria-label="Back to workspace"><ArrowLeft size={17}/></a>}<a href={PUBLIC_DEMO?"#simulation":"#staff"} className="immersive-brand">vela<span>.</span></a><span className="immersive-header-divider"/><div className="immersive-page-title"><strong>Simulation studio</strong><span>Hospital room · Reference environment</span></div><div className="immersive-header-right"><span className={`physics-status ${connected?'connected':''}`}><i/>{connected?(PUBLIC_DEMO?'MuJoCo · in browser':'MuJoCo connected'):'Loading MuJoCo'}</span><button className="immersive-icon-button" title="Viewer controls" aria-label="Viewer controls" onClick={()=>setShowHelp(!showHelp)}><CircleHelp size={19}/></button><button className="immersive-icon-button" aria-label="Toggle full screen" onClick={()=>document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen()}><Expand size={18}/></button></div></header>
    <div className="immersive-stage"><div ref={mount} className="immersive-canvas"/>
      <div className="scene-topline"><span><i/>INTERACTIVE 3D ENVIRONMENT</span><span>REAL-TIME PHYSICS · REFERENCE GEOMETRY</span></div>
      <aside className="immersive-scene-card"><div className="immersive-kicker"><Layers3 size={13}/> SCENE 01</div><h1>Patient room<br/>417.</h1><p>Explore the room and run simulated robot joints.</p><div className="immersive-room-meta"><span><Box size={14}/>Hospital room</span><span>7 × 6 m<span className="estimated-label">scene estimate</span></span></div><button onClick={()=>setShowDetails(!showDetails)} className="immersive-detail-button"><span><SlidersHorizontal size={14}/>Model & physics</span>{showDetails?<ChevronDown size={15}/>:<ChevronRight size={15}/>}</button>
      {showDetails&&<div className="immersive-detail-content"><dl><div><dt>Physics engine</dt><dd>{PUBLIC_DEMO?'MuJoCo / WebAssembly':'MuJoCo / Python'}</dd></div><div><dt>Geometry</dt><dd>Detailed reference model</dd></div><div><dt>Robot pose bodies</dt><dd>{bodyCount} synchronized</dd></div><div><dt>Render performance</dt><dd>{fps===undefined?'Measuring':`${fps} fps`}</dd></div><div><dt>Hardware verification</dt><dd>Unverified</dd></div><div><dt>Physics steps</dt><dd>{state?.metrics?.physics_steps?.toLocaleString()??"Waiting"}</dd></div>{state?.metrics?.reach?.actual_endpoint_error_m!==undefined&&<div><dt>Reach endpoint error</dt><dd>{(state.metrics.reach.actual_endpoint_error_m*100).toFixed(1)} cm</dd></div>}{state?.metrics?.stop_reason&&<div><dt>Stop reason</dt><dd>{state.metrics.stop_reason}</dd></div>}</dl><p>Visual reconstruction and estimated mechanics. Vendor CAD, calibrated dimensions, inertia, and joint limits are required for hardware-accurate validation.</p>{joints.length>0&&<details><summary>{joints.length} joint positions</summary><div className="immersive-joints">{joints.map(([name,value])=><div key={name}><span>{human(name)}</span><code>{typeof value==='number'?value.toFixed(3):String(value)} {/base_[xy]$|lift|stage/i.test(name)?'m':'rad'}</code></div>)}</div></details>}</div>}
      </aside>
      <div className="immersive-camera-switch" role="group" aria-label="Camera view">{(['overview','bedside','robot'] as ViewName[]).map((name,index)=><button key={name} aria-pressed={view===name} onClick={()=>chooseView(name)}>{index===0?<Orbit size={15}/>:index===1?<Focus size={15}/>:<Move3D size={15}/>}<span>{PRESETS[name].label}</span></button>)}</div>
      <div className="immersive-lighting"><Sun size={14}/><span>Daylight</span><i/><button aria-pressed={quality} onClick={()=>{setQuality(!quality);viewer.current?.setQuality(!quality)}}>{quality?'High quality':'Performance'}</button></div>
      {(!loaded||!connected)&&<div className="immersive-loading"><div><LoaderCircle size={22} className="spin"/><h2>{ready?(loaded?'Starting the physics engine':'Loading the detailed environment'):'Preparing the 3D viewer'}</h2><p>{assets.room?'Room ready':'Hospital room'} · {assets.robot?'Robot ready':'Reference robot'}</p></div></div>}
      {showHelp&&<div className="immersive-help"><div><strong>Make yourself at home.</strong><button className="immersive-icon-button" aria-label="Close controls help" onClick={()=>setShowHelp(false)}><X size={16}/></button></div><p><span>Orbit</span>Drag with the left mouse button</p><p><span>Pan</span>Drag with the right mouse button</p><p><span>Zoom</span>Scroll, or pinch on a trackpad</p><p><span>Touch</span>One finger to orbit; two to pan</p><button onClick={()=>chooseView('overview')}><RotateCcw size={13}/>Reset camera</button></div>}
      <div className="immersive-view-caption"><span className="immersive-view-line"/><span>BRACKET BOT<br/><strong>Reference reconstruction</strong></span></div>
      <div className="immersive-reference-badge"><ShieldCheck size={15}/><span>Research environment<span>Hardware model unverified</span></span></div>
      {notice&&<div className="immersive-toast" role="status"><Check size={16}/>{notice}</div>}
      {error&&<div className="immersive-toast immersive-error" role="alert"><span>{error}</span><button onClick={()=>setError('')} aria-label="Dismiss simulation error"><X size={16}/></button></div>}
    </div>
    {showAbout&&<div className="public-demo-about-backdrop" onClick={event=>{if(event.target===event.currentTarget)setShowAbout(false)}}><section ref={aboutDialog} role="dialog" aria-modal="true" aria-labelledby="public-demo-about-title" className="public-demo-about"><button className="immersive-icon-button" aria-label="Close demo information" onClick={()=>setShowAbout(false)}><X size={18}/></button><span className="immersive-kicker">VELA · PUBLIC SIMULATION</span><h2 id="public-demo-about-title">Explore the room. See the physics.</h2><p>This demo runs the reference robot in your browser using MuJoCo WebAssembly. Drag to explore, then try joint movement or a table reach.</p><p>The geometry and mechanics are estimates for research. No physical robot or hospital is connected.</p><h3>The complete local workspace</h3><p>The repository also includes patient assistance, staff operations, safety-gated task workflows, evidence tools, and learning pipelines. Those services run locally with the Python backend.</p>{REPOSITORY_URL&&<a className="button primary" href={REPOSITORY_URL} target="_blank" rel="noreferrer">View the project<ArrowUpRight size={15}/></a>}<button className="button secondary" onClick={()=>setShowAbout(false)}>Back to the simulation</button></section></div>}
    <footer className="immersive-transport"><div className="immersive-playback"><button aria-label={paused?'Resume simulation':'Pause simulation'} disabled={!connected||busy} onClick={()=>command('pause')} className="immersive-play-button">{paused?<Play size={20} fill="currentColor"/>:<Pause size={19} fill="currentColor"/>}</button><button className="immersive-icon-button" aria-label="Reset simulation" disabled={!connected||busy} onClick={()=>command('reset')}><RotateCcw size={19}/></button><div className="immersive-clock"><span>SIMULATION TIME</span><strong>{Number(state?.simulation_time??0).toFixed(2)}<small>s</small></strong></div><div className="immersive-playback-state"><i className={connected&&!paused?'live':''}/>{runningLabel}</div></div><div className="immersive-demo-controls"><span>EXPLORE THE ROBOT</span><button disabled={!connected||busy||!loaded} onClick={()=>{chooseView('robot');command('joint_demo')}}><Move3D size={16}/>Joint movement<ArrowUpRight size={14}/></button><button className="immersive-reach-button" disabled={!connected||busy||!loaded} onClick={()=>{chooseView('bedside');command('reach_demo')}}><Play size={14}/>Table reach demo<ArrowUpRight size={14}/></button></div><div className="immersive-transport-note">{PUBLIC_DEMO?"Physics runs on your device.":"Visual reference + simulated motion."}<br/>No physical robot connected.</div></footer>
  </div>;
}
