import { useState, type MutableRefObject } from 'react';
import { Camera, ChevronDown, ChevronUp, MapPin, RotateCcw, ScanEye } from 'lucide-react';
import { SENSOR_NAMES, type SensorName, type SensorCanvasSet, type SensorSnapshot } from './robotSensors';

const LABELS={head_rgb:'Head · left RGB',head_stereo_right:'Head · right RGB',left_wrist:'Left wrist',right_wrist:'Right wrist'};
export default function RobotPerceptionPanel({canvases,snapshot,onReset,guardEnabled,onGuardChange,visionPaused}:{canvases:MutableRefObject<SensorCanvasSet>;snapshot?:SensorSnapshot;onReset:()=>void;guardEnabled:boolean;onGuardChange:(value:boolean)=>void;visionPaused:boolean}){
  const [expanded,setExpanded]=useState(()=>window.innerWidth>1000),[tab,setTab]=useState<'cameras'|'map'>('cameras');
  const slam=snapshot?.slam,pose=slam?.pose;
  const [expandedCamera,setExpandedCamera]=useState<SensorName|null>(null);
  const track=slam?.trajectory??[];
  // A camera-frame top view: right is initial-camera +X, up is forward +Z.
  const points=(slam?.map??[]).filter(point=>point.position.every(Number.isFinite));
  const extent=Math.max(1,...track.map(p=>Math.max(Math.abs(p.position[0]),Math.abs(p.position[2]))),...points.map(p=>Math.min(8,Math.max(Math.abs(p.position[0]),Math.abs(p.position[2])))));
  const project=(p:number[])=>[160+p[0]/extent*95,140-p[2]/extent*95];
  const paths:string[][]=[];
  track.forEach((p,index)=>{if(!index||p.timestampMs-track[index-1].timestampMs>1500)paths.push([]);paths.at(-1)!.push(project(p.position).join(','))});
  const current=pose?project(pose.position):null;
  return <section className={`robot-perception ${expanded?'expanded':'collapsed'}`} aria-label="Robot vision" data-testid="robot-perception" data-status={slam?.status??'initializing'} data-frames={snapshot?.frames??0} data-slam-metrics={JSON.stringify(slam?{status:slam.status,confidence:slam.confidence,pose:slam.pose,mapSize:slam.map.length,...slam.metrics}:null)} data-slam-evaluation={JSON.stringify(snapshot?.evaluation??null)}>
    <button className="robot-perception-heading" onClick={()=>setExpanded(!expanded)} aria-expanded={expanded}><span><ScanEye size={17}/>Robot vision</span><span><i className={pose?'tracking':''}/>{pose?'Tracking':slam?.status==='lost'?'Tracking lost':'Starting'}{expanded?<ChevronUp size={15}/>:<ChevronDown size={15}/>}</span></button>
    <div className="robot-perception-body" hidden={!expanded}>
      <div className="robot-perception-tabs" role="group" aria-label="Robot vision display"><button aria-pressed={tab==='cameras'} onClick={()=>setTab('cameras')}><Camera size={13}/>Camera views</button><button aria-pressed={tab==='map'} onClick={()=>setTab('map')}><MapPin size={13}/>Visual map</button></div>
      <div className="robot-camera-grid" hidden={tab!=='cameras'}>{SENSOR_NAMES.map(name=><figure key={name} className={expandedCamera===name?'camera-enlarged':''}><canvas ref={node=>{canvases.current[name]=node}} width={320} height={240} aria-label={`${LABELS[name]} camera view`} data-camera={name}/>{name==='head_rgb'&&<svg className="camera-feature-overlay" viewBox={`0 0 ${snapshot?.width??640} ${snapshot?.height??480}`} aria-hidden="true">{slam?.features.filter(feature=>feature.tracked).map((feature,index)=><circle key={index} cx={feature.x} cy={feature.y} r="1.7" fill="none" stroke="#70d899" strokeWidth=".8"/>)}</svg>}<figcaption><button onClick={()=>setExpandedCamera(expandedCamera===name?null:name)} aria-pressed={expandedCamera===name} aria-label={`Enlarge ${LABELS[name]} camera`}>{LABELS[name]}<span>{expandedCamera===name?'−':'+'}</span></button></figcaption></figure>)}</div>
      {tab==='map'&&<div className="robot-visual-map"><svg viewBox="0 0 320 240" role="img" aria-label="Map and camera path estimated from stereo images"><defs><pattern id="vision-grid" width="32" height="24" patternUnits="userSpaceOnUse"><path d="M 32 0 L 0 0 0 24" fill="none" stroke="#dce5d6" strokeWidth=".5"/></pattern></defs><rect width="320" height="240" fill="url(#vision-grid)"/>{points.map((point,index)=>{const p=project(point.position);return <circle key={index} cx={p[0]} cy={p[1]} r="1.8" fill="#91a583"/>})}{paths.map((segment,index)=><polyline key={index} points={segment.join(" ")} fill="none" stroke="#486d47" strokeWidth="2"/>)}<circle cx="160" cy="140" r="4" fill="#b2beaa"/>{current&&<circle cx={current[0]} cy={current[1]} r="5" fill="#335f42" stroke="#fff" strokeWidth="2"/>}<text x="12" y="20" fill="#748568" fontSize="10">Initial camera frame · {extent.toFixed(1)} m scale</text></svg><p>{pose?'Position estimated from stereo landmarks.':slam?.status==='lost'?'No valid visual pose. Waiting to recognize mapped features.':'Move the robot to build and track visual landmarks.'}</p></div>}
      <div className="robot-vision-stats"><span><strong>{slam?.metrics.inliers??0}</strong> tracked points</span><span><strong>{slam?.map.length??0}</strong> map points</span><span><strong>{snapshot?.frameRate.toFixed(1)??'—'}</strong> fps</span></div>
      <p className="robot-vision-note">Stereo visual SLAM prototype · simulated camera pixels. The map can drift. Tasks follow planned routes; visual tracking can pause motion when localization is lost.</p>
      <label className="robot-vision-guard"><input type="checkbox" checked={guardEnabled} onChange={event=>onGuardChange(event.target.checked)}/>Pause motion if tracking is lost</label>
      {visionPaused&&<p className="robot-vision-pause" role="status" data-testid="vision-pause">Motion paused: visual tracking was lost. Resume manually when ready.</p>}
      <button className="robot-map-reset" onClick={onReset}><RotateCcw size={12}/>Restart visual map</button>
    </div>
  </section>;
}
