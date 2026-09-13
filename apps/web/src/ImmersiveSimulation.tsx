import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowUpRight, Box, Check, ChevronDown, ChevronRight, CircleHelp, Expand, Focus, Layers3, LoaderCircle, Move3D, MoveVertical, Orbit, Pause, Play, RotateCcw, ShieldCheck, SlidersHorizontal, Smartphone, Sun, UserRound, X } from 'lucide-react';
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
import SimulationDemoGallery, { EXTRA_DEMOS, type ExtraDemoCommand } from './SimulationDemoGallery';
import SimulationDemoMetrics from './SimulationDemoMetrics';
import RobotPerceptionPanel from './RobotPerceptionPanel';
import { RobotSensors, type SensorCanvasSet, type SensorName, type SensorPose, type SensorSnapshot } from './robotSensors';
import { VisualTrackingGuard } from './visualTrackingGuard';
import './immersive.css';

type ViewName='overview'|'bedside'|'robot'|'pickup'|'patient'|'patient_face'|'bed_foot'|'bed_rear'|'chair'|'storage'|'wardrobe'|'delivery'|'blinds';
type ViewerApi={setView:(name:ViewName)=>void;setQuality:(value:boolean)=>void;resetCamera:()=>void};
const PRESETS:Record<ViewName,{position:[number,number,number];target:[number,number,number];label:string}>={
  overview:{position:[6.8,-8.8,6.4],target:[0,.25,.95],label:'Room overview'},
  bedside:{position:[4.2,-4.7,2.75],target:[.85,.9,1.02],label:'At the bedside'},
  robot:{position:[1.2,-3.45,1.92],target:[-.55,-.62,1.05],label:'Robot detail'},
  pickup:{position:[1.75,-2.65,1.62],target:[.4,-.62,.91],label:'Phone close-up'},
  patient:{position:[3.15,.55,2.0],target:[1.40,1.88,1.03],label:'Patient bedside'},
  patient_face:{position:[2.1,1.15,2.3],target:[1.40,2.10,1.17],label:'Patient close-up'},
  bed_foot:{position:[3.2,-1.20,1.35],target:[1.40,1.40,.65],label:'Bed foot and chassis'},
  bed_rear:{position:[-.75,2.70,1.75],target:[1.35,1.42,.65],label:'Bed rear corner'},
  chair:{position:[.50,2.60,1.20],target:[-1.60,1.30,.58],label:'Chair construction'},
  storage:{position:[3.2,.75,1.08],target:[2.62,2.28,.48],label:'Bedside storage'},
  wardrobe:{position:[1,-1.6,1.65],target:[-2.3,2.1,1],label:'Wardrobe and visitor table'},
  delivery:{position:[3.9,-2.8,3.3],target:[.55,.65,1.05],label:'Bedside delivery'},
  blinds:{position:[.8,-3.9,2.75],target:[-2.85,-.2,1.45],label:'Window blinds'},
};
const ROOM_ASSEMBLIES=['patient','hospital_bed','visitor_chair','bedside_table','bedside_storage','wardrobe','visitor_table','room_plant'];
const INSPECTION_VIEWS:ViewName[]=['patient_face','bed_foot','bed_rear','chair','storage','wardrobe'];

export default function ImmersiveSimulation(){
  const mount=useRef<HTMLDivElement>(null);
  const viewer=useRef<ViewerApi|undefined>(undefined);
  const latest=useRef<ReferenceState|undefined>(undefined);
  const [state,setState]=useState<ReferenceState>();
  const [connected,setConnected]=useState(false);
  const [assets,setAssets]=useState({room:false,robot:false,phone:false,meal_box:false});
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [view,setView]=useState<ViewName>('bedside');
  const [busy,setBusy]=useState(false);
  const [quality,setQuality]=useState(true);
  const [showDetails,setShowDetails]=useState(false);
  const [showHelp,setShowHelp]=useState(false);
  const [showAbout,setShowAbout]=useState(false);
  const [showDemos,setShowDemos]=useState(false);
  const aboutDialog=useRef<HTMLElement>(null);
  const [fps,setFps]=useState<number>();
  const [bodyCount,setBodyCount]=useState(0);
  const [ready,setReady]=useState(false);
  const [hasPatient,setHasPatient]=useState(false);
  const sensorCanvases=useRef<SensorCanvasSet>({});
  const sensors=useRef<RobotSensors|undefined>(undefined);
  const [sensorSnapshot,setSensorSnapshot]=useState<SensorSnapshot>();
  const latestVision=useRef<{snapshot:SensorSnapshot;frameAtMs:number}|undefined>(undefined);
  const trackingGuard=useRef(new VisualTrackingGuard());
  const [guardEnabled,setGuardEnabled]=useState(false);
  const [visionPaused,setVisionPaused]=useState(false);
  const guardPending=useRef(false);
  const manualControlPending=useRef(false);
  const transport=useRef<SimulationTransport|undefined>(undefined);
  const command=useCallback(async(value:SimulationCommand)=>{
    manualControlPending.current=true;setBusy(true);setError('');
    trackingGuard.current.reset();setVisionPaused(false);
    try{if(!transport.current)throw new Error('The physics engine is still loading.');const result=await transport.current.command(value);if(result.bodies){latest.current=result;setState(result)}setNotice(value==='reset'?'Simulation returned to its starting state.':value==='joint_demo'?'Joint movement demonstration started.':value==='reach_demo'?'Table reach demonstration started.':value==='pickup_demo'?'Contact pickup sequence started.':value==='lift_demo'?'Vertical carriage travel started.':value==='release_phone'?'Grippers opening. The phone remains under physics.':'Simulation playback updated.')}
    catch(e){setError((e as Error).message)}finally{manualControlPending.current=false;setVisionPaused(false);setBusy(false)}
  },[]);

  useEffect(()=>{
    trackingGuard.current.reset();
    const timer=window.setInterval(()=>{
      const current=latest.current,observation=latestVision.current;
      const moving=!manualControlPending.current&&!!current&&current.mode!=='idle'&&!current.paused&&!current.metrics?.demo?.complete;
      const shouldPause=trackingGuard.current.evaluate({enabled:guardEnabled,moving,nowMs:performance.now(),frameAtMs:observation?.frameAtMs??null,status:observation?.snapshot.slam.status??'initializing',hasPose:!!observation?.snapshot.slam.pose});
      if(shouldPause&&moving&&!guardPending.current&&transport.current){
        guardPending.current=true;
        transport.current.command('pause_for_tracking').then(result=>{latest.current=result;setState(result);setVisionPaused(true)}).catch(error=>setError(`Visual tracking pause failed: ${(error as Error).message}`)).finally(()=>{guardPending.current=false});
      }
    },150);
    return()=>window.clearInterval(timer);
  },[guardEnabled]);

  useEffect(()=>{
    let cancelled=false;let timer:number;let runtime:SimulationTransport|undefined;let uiAt=0;
    const tick=async()=>{
      if(cancelled||!runtime)return;
      const started=performance.now();
      try{
        const incoming=await runtime.state();
        if(!cancelled){latest.current=incoming;setConnected(true);if(performance.now()-uiAt>250){setState(incoming);uiAt=performance.now()}}
      }catch(e){if(!cancelled){setConnected(false);setError((e as Error).message)}}
      finally{if(!cancelled)timer=window.setTimeout(tick,Math.max(0,(PUBLIC_DEMO?1000/60:50)-(performance.now()-started)))}
    };
    createSimulationTransport().then(engine=>{if(cancelled){engine.dispose();return}runtime=engine;transport.current=engine;tick()}).catch(e=>{if(!cancelled)setError(`Physics could not start: ${(e as Error).message}`)});
    return()=>{cancelled=true;window.clearTimeout(timer);runtime?.dispose();transport.current=undefined};
  },[]);

  useEffect(()=>{
    if(!mount.current)return;
    const element=mount.current;
    let disposed=false;let frame=0;let uiAt=0;let frameCount=0;let sampleAt=performance.now();
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
    renderer.domElement.setAttribute('aria-label','Interactive 3D hospital room, synthetic patient and reference robot. Drag to orbit, scroll to zoom, or use the camera view controls.');
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
    sunlight.castShadow=true;sunlight.shadow.mapSize.set(2048,2048);sunlight.shadow.camera.left=-7;sunlight.shadow.camera.right=7;sunlight.shadow.camera.top=7;sunlight.shadow.camera.bottom=-7;sunlight.shadow.camera.near=.1;sunlight.shadow.camera.far=30;sunlight.shadow.bias=-.0003;sunlight.shadow.normalBias=.006;sunlight.shadow.radius=3;scene.add(sunlight);
    const fill=new THREE.DirectionalLight('#dcebf2',.75);fill.position.set(4,-6,5);scene.add(fill);
    const ground=new THREE.Mesh(new THREE.PlaneGeometry(200,200),new THREE.MeshStandardMaterial({color:'#e5e8df',roughness:.94}));ground.position.z=-.095;ground.receiveShadow=true;scene.add(ground);
    const temporaryFloor=new THREE.Mesh(new THREE.BoxGeometry(7,6,.12),new THREE.MeshStandardMaterial({color:'#e6e3da',roughness:.84}));temporaryFloor.position.z=-.055;temporaryFloor.receiveShadow=true;scene.add(temporaryFloor);
    const targetMarker=new THREE.Group();
    targetMarker.add(new THREE.Mesh(new THREE.SphereGeometry(.025,16,12),new THREE.MeshBasicMaterial({color:'#38a877',transparent:true,opacity:.85})));
    targetMarker.add(new THREE.Mesh(new THREE.TorusGeometry(.065,.003,8,40),new THREE.MeshBasicMaterial({color:'#3baf7e',transparent:true,opacity:.8})));
    targetMarker.visible=false;scene.add(targetMarker);
    // Postprocessing renders offscreen, so canvas antialiasing alone has no effect.
    const renderTarget=new THREE.WebGLRenderTarget(element.clientWidth,element.clientHeight,{type:THREE.HalfFloatType,samples:Math.min(4,renderer.capabilities.maxSamples)});
    const composer=new EffectComposer(renderer,renderTarget);
    composer.setSize(element.clientWidth,element.clientHeight);
    composer.addPass(new RenderPass(scene,camera));
    const ssao=new SSAOPass(scene,camera,element.clientWidth,element.clientHeight);
    ssao.kernelRadius=.16;ssao.minDistance=.001;ssao.maxDistance=.025;
    composer.addPass(ssao);composer.addPass(new OutputPass());
    const desiredCamera=new THREE.Vector3().fromArray(PRESETS.overview.position);
    const desiredTarget=new THREE.Vector3().fromArray(PRESETS.overview.target);
    let cameraMoving=false;
    const stopCamera=()=>{cameraMoving=false};controls.addEventListener('start',stopCamera);
    const selectView=(name:ViewName)=>{desiredCamera.fromArray(PRESETS[name].position);desiredTarget.fromArray(PRESETS[name].target);cameraMoving=true;renderer.domElement.dataset.cameraView=name;renderer.domElement.dataset.cameraSettled='false'};
    renderer.domElement.dataset.cameraView='bedside';renderer.domElement.dataset.cameraSettled='true';
    viewer.current={setView:selectView,setQuality:value=>{ssao.enabled=value;renderer.setPixelRatio(value?Math.min(window.devicePixelRatio,1.5):1);renderer.setSize(element.clientWidth,element.clientHeight);composer.setPixelRatio(renderer.getPixelRatio());composer.setSize(element.clientWidth,element.clientHeight)},resetCamera:()=>selectView('overview')};
    const loader=new GLTFLoader();
    const load=async(kind:'room'|'robot'|'phone'|'meal_box')=>{
      if(disposed)return;
      if(!PUBLIC_DEMO&&!transport.current){retryTimers.push(window.setTimeout(()=>load(kind),150));return}
      try{
        // GLBs preserve native Z-up. Their mesh geometry is local to the named physics body.
        const gltf=await loader.loadAsync(simulationAsset(`${kind}.glb`));
        if(disposed){gltf.scene.traverse(disposeObject);return}
        gltf.scene.name=`${kind}_asset_root`;
        gltf.scene.traverse(node=>{
          if(node.name)objects.set(node.name,node);
          if(node instanceof THREE.Mesh){
            const materials=Array.isArray(node.material)?node.material:[node.material];
            node.castShadow=!materials.some(material=>material.transparent&&material.opacity<.6);
            node.receiveShadow=true;
            materials.forEach(material=>{if(material instanceof THREE.MeshStandardMaterial){material.envMapIntensity=.8;material.needsUpdate=true}});
          }
        });
        scene.add(gltf.scene);
        if(kind==='room'){
          scene.remove(temporaryFloor);temporaryFloor.geometry.dispose();(temporaryFloor.material as THREE.Material).dispose();
          const assemblies:Record<string,{mesh_count:number;triangle_count:number;bounds:{min:number[];max:number[]}}>= {};
          for(const name of ROOM_ASSEMBLIES){
            const group=gltf.scene.getObjectByName(name);if(!group)continue;
            let meshCount=0,triangleCount=0;
            group.traverse(node=>{if(node instanceof THREE.Mesh){meshCount++;triangleCount+=(node.geometry.index?.count??node.geometry.getAttribute('position')?.count??0)/3}});
            const bounds=new THREE.Box3().setFromObject(group,true);
            assemblies[name]={mesh_count:meshCount,triangle_count:triangleCount,bounds:{min:bounds.min.toArray(),max:bounds.max.toArray()}};
          }
          // Read-only evidence from the loaded GLB, useful for scene diagnostics.
          renderer.domElement.dataset.roomAssemblies=JSON.stringify(assemblies);
          setHasPatient(!!assemblies.patient?.mesh_count);
        }
        setAssets(current=>({...current,[kind]:true}));
      }catch(error){
        if(!disposed){setError(`The ${kind} model could not load: ${(error as Error).message}`);retryTimers.push(window.setTimeout(()=>load(kind),4000))}
      }
    };
    load('room');load('robot');load('phone');load('meal_box');
    const sensorRig=new RobotSensors(renderer,scene);sensors.current=sensorRig;
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
      const now=performance.now();
      if(cameraMoving){camera.position.lerp(desiredCamera,.075);controls.target.lerp(desiredTarget,.075);if(camera.position.distanceTo(desiredCamera)<.003){cameraMoving=false;renderer.domElement.dataset.cameraSettled='true'}}
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
        // Apply one coherent physics sample. Independently smoothing world-space
        // links takes different arcs and visibly pulls an articulated robot apart.
        object.position.copy(targetPosition);object.quaternion.copy(targetQuaternion);object.updateMatrixWorld(true);matches++;
      }
      controls.update();composer.render();frameCount++;
      if(latest.current?.cameras&&objects.has('head')&&scene.getObjectByName('room_asset_root')){
        const markerVisible=targetMarker.visible;targetMarker.visible=false;
        try{
          const snapshot=sensorRig.sample(latest.current.cameras as Partial<Record<SensorName,SensorPose>>,latest.current.simulation_time??0,now,sensorCanvases.current);
          if(snapshot){latestVision.current={snapshot,frameAtMs:snapshot.timestampMs};setSensorSnapshot(snapshot)}
        }catch(error){setError(`Robot vision: ${(error as Error).message}`)}
        finally{targetMarker.visible=markerVisible}
      }
      if(now-uiAt>500){setBodyCount(matches);uiAt=now}
      if(now-sampleAt>1000){setFps(Math.round(frameCount*1000/(now-sampleAt)));frameCount=0;sampleAt=now}
    }
    animate();setReady(true);
    return()=>{
      disposed=true;cancelAnimationFrame(frame);retryTimers.forEach(clearTimeout);resize.disconnect();controls.dispose();sensorRig.dispose();sensors.current=undefined;scene.traverse(disposeObject);envTexture.dispose();ssao.dispose();composer.dispose();renderer.dispose();renderer.domElement.remove();viewer.current=undefined;
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
  const startExtraDemo=async(value:ExtraDemoCommand)=>{
    if(busy||!transport.current)return;
    manualControlPending.current=true;
    setBusy(true);setError('');setNotice('');setShowDemos(false);setShowDetails(false);
    trackingGuard.current.reset();setVisionPaused(false);
    try{
      await transport.current.command('reset');
      const result=await transport.current.command(value);
      latest.current=result;setState(result);
      const selected=EXTRA_DEMOS.find(demo=>demo.command===value)!;
      chooseView(selected.view);setNotice(`${selected.title} started.`);
    }catch(error){setError((error as Error).message)}finally{manualControlPending.current=false;setVisionPaused(false);setBusy(false)}
  };
  const paused=state?.paused??(state?.running===false);
  const joints=Array.isArray(state?.joints)?state.joints.map(item=>[item.name,item.position] as const):Object.entries(state?.joints??{});
  const loaded=assets.room&&assets.robot&&assets.phone&&assets.meal_box;
  const pickup=state?.metrics?.pickup,lift=state?.metrics?.lift,demo=state?.metrics?.demo;
  const demoActive=state?.mode!==undefined&&state.mode!=='idle';
  const runningLabel=!connected?'Connecting':state?.metrics?.stop_reason?'Contact stop':paused?'Paused':state?.mode==='idle'?'Ready':demo?(demo.complete?'Complete':demo.name):human(state?.mode??'Live physics');
  return <div className="immersive-shell">
    <header className="immersive-header">{PUBLIC_DEMO?<button className="immersive-back" aria-label="About this demo" onClick={()=>setShowAbout(true)}><CircleHelp size={17}/></button>:<a href="#research" className="immersive-back" aria-label="Back to workspace"><ArrowLeft size={17}/></a>}<a href={PUBLIC_DEMO?"#simulation":"#staff"} className="immersive-brand">vela<span>.</span></a><span className="immersive-header-divider"/><div className="immersive-page-title"><strong>Simulation studio</strong><span>Hospital room · Reference environment</span></div><div className="immersive-header-right"><span className={`physics-status ${connected?'connected':''}`}><i/>{connected?(PUBLIC_DEMO?'MuJoCo · in browser':'MuJoCo connected'):'Loading MuJoCo'}</span><button className="immersive-icon-button" title="Viewer controls" aria-label="Viewer controls" onClick={()=>setShowHelp(!showHelp)}><CircleHelp size={19}/></button><button className="immersive-icon-button" aria-label="Toggle full screen" onClick={()=>document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen()}><Expand size={18}/></button></div></header>
    <div className="immersive-stage"><div ref={mount} className="immersive-canvas"/>
      <div className="scene-topline"><span><i/>INTERACTIVE 3D ENVIRONMENT</span><span>REAL-TIME PHYSICS · REFERENCE GEOMETRY</span></div>
      <aside className="immersive-scene-card"><div className="immersive-kicker"><Layers3 size={13}/> SCENE 01</div><h1>Patient room<br/>417.</h1><p>See through the robot cameras. Bring a phone or meal to the patient, or open the blinds.</p><div className="immersive-room-meta"><span><Box size={14}/>Hospital room</span>{hasPatient&&<span className="immersive-synthetic-patient"><UserRound size={14}/>Synthetic patient model</span>}<span>7 × 6 m<span className="estimated-label">scene estimate</span></span></div>
      {demo&&<SimulationDemoMetrics demo={demo} pickup={pickup} paused={!!paused} onBrowse={()=>setShowDemos(true)}/>}
      {pickup&&!demo&&<div className="immersive-action-metrics" data-testid="pickup-metrics" data-success={pickup.success} data-released={pickup.released} data-height-gain={pickup.height_gain_m} data-bilateral-contact={pickup.bilateral_contact} data-hold-seconds={pickup.bilateral_hold_s}>
        <strong>{pickup.success?'Pickup confirmed':pickup.released?'Phone released':pickup.status==='failed'?'Pickup stopped':'Contact pickup'}</strong>
        <dl><div><dt>Stage</dt><dd>{human(pickup.stage)}</dd></div><div><dt>Phone lifted</dt><dd>{(pickup.height_gain_m*100).toFixed(1)} cm</dd></div><div><dt>Finger contacts</dt><dd>{pickup.finger_contacts.length} / 2</dd></div><div><dt>Verified hold</dt><dd>{pickup.bilateral_hold_s.toFixed(1)} s</dd></div></dl>
        <p>MuJoCo contact and friction hold the free phone. Success requires a 15 cm lift and two seconds of contact from both fingers.</p>
        <button disabled={!pickup.success||busy||state?.mode!=='pickup_demo'} onClick={()=>command('release_phone')}><Smartphone size={13}/>{pickup.released?'Phone released':'Release phone'}</button>
      </div>}
      {lift&&<div className="immersive-action-metrics" data-testid="lift-metrics" data-complete={lift.complete} data-left-travel={lift.travel_m.left} data-right-travel={lift.travel_m.right} data-low-height={Math.min(lift.min_hand_height_m.left,lift.min_hand_height_m.right)} data-high-height={Math.max(lift.max_hand_height_m.left,lift.max_hand_height_m.right)}>
        <strong>{lift.complete?'Vertical travel complete':'Vertical carriage travel'}</strong>
        <dl><div><dt>Stage</dt><dd>{human(lift.stage)}</dd></div><div><dt>Left carriage</dt><dd>{(lift.positions_m.left*100).toFixed(1)} cm</dd></div><div><dt>Right carriage</dt><dd>{(lift.positions_m.right*100).toFixed(1)} cm</dd></div><div><dt>Measured travel</dt><dd>{(Math.max(lift.travel_m.left,lift.travel_m.right)*100).toFixed(1)} cm</dd></div><div><dt>Hand height</dt><dd>{Math.max(lift.hand_height_m.left,lift.hand_height_m.right).toFixed(2)} m</dd></div></dl>
        <p>Carriage positions are relative to their starting height. Motion follows the estimated rail limits and checks collisions at each physics step.</p>
      </div>}
<button onClick={()=>setShowDetails(!showDetails)} className="immersive-detail-button"><span><SlidersHorizontal size={14}/>Model & physics</span>{showDetails?<ChevronDown size={15}/>:<ChevronRight size={15}/>}</button>
      {showDetails&&<div className="immersive-detail-content"><dl><div><dt>Physics engine</dt><dd>{PUBLIC_DEMO?'MuJoCo / WebAssembly':'MuJoCo / Python'}</dd></div><div><dt>Geometry</dt><dd>Detailed reference model</dd></div><div><dt>Physics bodies</dt><dd>{bodyCount} synchronized</dd></div><div><dt>Render performance</dt><dd>{fps===undefined?'Measuring':`${fps} fps`}</dd></div><div><dt>Hardware verification</dt><dd>Unverified</dd></div><div><dt>Physics steps</dt><dd>{state?.metrics?.physics_steps?.toLocaleString()??"Waiting"}</dd></div>{state?.metrics?.reach?.actual_endpoint_error_m!==undefined&&<div><dt>Reach endpoint error</dt><dd>{(state.metrics.reach.actual_endpoint_error_m*100).toFixed(1)} cm</dd></div>}{state?.metrics?.stop_reason&&<div><dt>Stop reason</dt><dd>{state.metrics.stop_reason}</dd></div>}</dl><p>Visual reconstruction and estimated mechanics. Vendor CAD, calibrated dimensions, inertia, and joint limits are required for hardware-accurate validation.</p>{joints.length>0&&<details><summary>{joints.length} joint positions</summary><div className="immersive-joints">{joints.map(([name,value])=><div key={name}><span>{human(name)}</span><code>{typeof value==='number'?value.toFixed(3):String(value)} {/base_[xy]$|lift|stage/i.test(name)?'m':'rad'}</code></div>)}</div></details>}<label className="immersive-inspection-selector">Inspect the room<select aria-label="Inspect room furnishings" value={INSPECTION_VIEWS.includes(view)?view:''} onChange={event=>{if(event.target.value)chooseView(event.target.value as ViewName)}}><option value="">Choose a detail view</option>{INSPECTION_VIEWS.map(name=><option key={name} value={name}>{PRESETS[name].label}</option>)}</select></label></div>}
      </aside>
      <div className="immersive-camera-switch" role="group" aria-label="Camera view">{(['overview','bedside','patient','robot','pickup'] as ViewName[]).map((name,index)=><button key={name} aria-pressed={view===name} onClick={()=>chooseView(name)}>{index===0?<Orbit size={15}/>:index===1?<Focus size={15}/>:index===2?<UserRound size={15}/>:index===3?<Move3D size={15}/>:<Smartphone size={15}/>}<span>{PRESETS[name].label}</span></button>)}</div>
      <div className="immersive-lighting"><Sun size={14}/><span>Daylight</span><i/><button aria-pressed={quality} onClick={()=>{setQuality(!quality);viewer.current?.setQuality(!quality)}}>{quality?'High quality':'Performance'}</button></div>
      <RobotPerceptionPanel canvases={sensorCanvases} snapshot={sensorSnapshot} guardEnabled={guardEnabled} onGuardChange={setGuardEnabled} visionPaused={visionPaused} onReset={()=>{sensors.current?.reset();setSensorSnapshot(undefined);latestVision.current=undefined;trackingGuard.current.reset()}}/>
      {(!loaded||!connected)&&<div className="immersive-loading"><div><LoaderCircle size={22} className="spin"/><h2>{ready?(loaded?'Starting the physics engine':'Loading the detailed environment'):'Preparing the 3D viewer'}</h2><p>{assets.room?'Room ready':'Hospital room'} · {assets.robot?'Robot ready':'Reference robot'} · {assets.phone?'Phone ready':'Dynamic phone'}</p></div></div>}
      {showHelp&&<div className="immersive-help"><div><strong>Make yourself at home.</strong><button className="immersive-icon-button" aria-label="Close controls help" onClick={()=>setShowHelp(false)}><X size={16}/></button></div><p><span>Orbit</span>Drag with the left mouse button</p><p><span>Pan</span>Drag with the right mouse button</p><p><span>Zoom</span>Scroll, or pinch on a trackpad</p><p><span>Touch</span>One finger to orbit; two to pan</p><button onClick={()=>chooseView('overview')}><RotateCcw size={13}/>Reset camera</button></div>}
      <div className="immersive-view-caption"><span className="immersive-view-line"/><span>BRACKET BOT<br/><strong>Reference reconstruction</strong></span></div>
      <div className="immersive-reference-badge"><ShieldCheck size={15}/><span>Research environment<span>Hardware model unverified</span></span></div>
      {notice&&<div className="immersive-toast" role="status"><Check size={16}/>{notice}</div>}
      {error&&<div className="immersive-toast immersive-error" role="alert"><span>{error}</span><button onClick={()=>setError('')} aria-label="Dismiss simulation error"><X size={16}/></button></div>}
    </div>
    {showAbout&&<div className="public-demo-about-backdrop" onClick={event=>{if(event.target===event.currentTarget)setShowAbout(false)}}><section ref={aboutDialog} role="dialog" aria-modal="true" aria-labelledby="public-demo-about-title" className="public-demo-about"><button className="immersive-icon-button" aria-label="Close demo information" onClick={()=>setShowAbout(false)}><X size={18}/></button><span className="immersive-kicker">VELA · PUBLIC SIMULATION</span><h2 id="public-demo-about-title">Explore the room. See the physics.</h2><p>This demo runs the reference robot in your browser using MuJoCo WebAssembly. Drag to explore, then try joint movement or a table reach.</p><p>The geometry and mechanics are estimates for research. No physical robot or hospital is connected.</p><h3>The complete local workspace</h3><p>The repository also includes patient assistance, staff operations, safety-gated task workflows, evidence tools, and learning pipelines. Those services run locally with the Python backend.</p>{REPOSITORY_URL&&<a className="button primary" href={REPOSITORY_URL} target="_blank" rel="noreferrer">View the project<ArrowUpRight size={15}/></a>}<button className="button secondary" onClick={()=>setShowAbout(false)}>Back to the simulation</button></section></div>}
    {showDemos&&<SimulationDemoGallery ready={connected&&loaded&&!busy} onClose={()=>setShowDemos(false)} onStart={startExtraDemo}/>}
    <footer className="immersive-transport"><div className="immersive-playback"><button aria-label={paused?'Resume simulation':'Pause simulation'} disabled={!connected||busy} onClick={()=>command('pause')} className="immersive-play-button">{paused?<Play size={20} fill="currentColor"/>:<Pause size={19} fill="currentColor"/>}</button><button className={demoActive?'immersive-icon-button immersive-reset-label':'immersive-icon-button'} aria-label="Reset simulation" disabled={!connected||busy} onClick={()=>command('reset')}><RotateCcw size={19}/>{demoActive&&<span>Reset to switch</span>}</button><div className="immersive-clock"><span>SIMULATION TIME</span><strong>{Number(state?.simulation_time??0).toFixed(2)}<small>s</small></strong></div><div className="immersive-playback-state"><i className={connected&&!paused?'live':''}/>{runningLabel}</div></div><div className="immersive-demo-controls"><button disabled={!connected||busy||!loaded||demoActive} onClick={()=>{chooseView('robot');command('joint_demo')}}><Move3D size={16}/>Joint movement<ArrowUpRight size={14}/></button><button disabled={!connected||busy||!loaded||demoActive} onClick={()=>{chooseView('bedside');command('reach_demo')}}><Play size={14}/>Table reach demo<ArrowUpRight size={14}/></button><button disabled={!connected||busy||!loaded||demoActive} onClick={()=>{chooseView('robot');command('lift_demo')}}><MoveVertical size={16}/>Vertical travel<ArrowUpRight size={14}/></button><button className="immersive-pickup-button" disabled={!connected||busy||!loaded||demoActive} onClick={()=>{chooseView('pickup');command('pickup_demo')}}><Smartphone size={16}/>Pick up phone<ArrowUpRight size={14}/></button><button className="immersive-more-demos-button" onClick={()=>setShowDemos(true)}><Layers3 size={16}/>More demos</button></div><div className="immersive-transport-note">{PUBLIC_DEMO?"Physics runs on your device.":"Visual reference + simulated motion."}<br/>No physical robot connected.</div></footer>
  </div>;
}
