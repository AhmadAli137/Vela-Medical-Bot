import { useId } from 'react';
import { type Bootstrap, type RoomObject, human } from './api';

type Props = { room: Bootstrap['room']; selected?: string; onSelect?: (object: RoomObject) => void; robot?: Record<string, any> };

export default function RoomScene({room, selected, onSelect, robot}: Props) {
  const uid = useId().replaceAll(':', '');
  const w = Number(room.geometry?.width ?? room.dimensions?.x ?? 6);
  const h = Number(room.geometry?.depth ?? room.dimensions?.y ?? 5);
  const scale = Math.min(590 / w, 390 / h);
  const sx = (x: number) => 64 + x * scale;
  const sy = (y: number) => 53 + y * scale;
  const zones = Array.isArray(room.zones) ? room.zones : [];
  const doorway=room.doorways?.[0]?.pose;
  return <svg viewBox="0 0 720 510" className="room-svg" role="img" aria-label={`Illustrative top-down view of ${room.name || 'Room 417'}, with ${room.objects.length} synthetic objects. Select an object to inspect its permissions.`}>
    <defs>
      <pattern id={`${uid}-grid`} width="26" height="26" patternUnits="userSpaceOnUse"><path d="M 26 0 L 0 0 0 26" fill="none" stroke="#dddcd3" strokeWidth=".55" /></pattern>
      <filter id={`${uid}-shadow`} x="-30%" y="-30%" width="160%" height="180%"><feDropShadow dx="0" dy="5" stdDeviation="4" floodColor="#354b45" floodOpacity=".13" /></filter>
      <pattern id={`${uid}-hatch`} width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="8" stroke="#aa786d" strokeOpacity=".18" strokeWidth="2" /></pattern>
    </defs>
    <rect x="47" y="35" width={w*scale+34} height={h*scale+34} rx="10" fill="#d9dcd5"/>
    <rect x="57" y="45" width={w*scale+14} height={h*scale+14} rx="5" fill="#f2f0e8" stroke="#fafbf7" strokeWidth="3"/>
    <rect x="64" y="53" width={w*scale} height={h*scale} fill={`url(#${uid}-grid)`}/>
    {zones.map((zone: any, i: number) => {
      const lower=zone.bounds?.min ?? zone.min ?? {x:zone.x??0,y:zone.y??0};
      const upper=zone.bounds?.max ?? zone.max ?? {x:(zone.x??0)+(zone.width??0),y:(zone.y??0)+(zone.depth??0)};
      const zw = Math.max(0,(upper.x-lower.x)*scale); const zh = Math.max(0,(upper.y-lower.y)*scale);
      if (!zw || !zh) return null;
      const blocked=String(zone.type??zone.id).includes('patient')||String(zone.type??zone.id).includes('keepout');
      return <g key={zone.id??i}><rect x={sx(lower.x)} y={sy(lower.y)} width={zw} height={zh} rx="12" fill={blocked?`url(#${uid}-hatch)`:'#daeee5'} fillOpacity=".6" stroke={blocked?'#c39b91':'#8db9a7'} strokeDasharray="5 5"/><text x={sx(lower.x)+8} y={sy(lower.y)+15} fontSize="9" fill={blocked?'#986f66':'#557f6c'} letterSpacing="1">{human(zone.name??zone.id).toUpperCase()}</text></g>;
    })}
    {room.objects.map((object) => {
      const kind=object.semantic_class.toLowerCase();
      const x=sx(object.pose.x); const y=sy(object.pose.y);
      const ow=Math.max(14, (object.dimensions?.x??.35)*scale); const oh=Math.max(12, (object.dimensions?.y??.35)*scale);
      const prohibited=object.policy.includes('PROHIBITED');
      const active=selected===object.id;
      return <g key={object.id} transform={`translate(${x},${y})`} onClick={() => onSelect?.(object)} onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();onSelect?.(object)}}} tabIndex={onSelect?0:undefined} role={onSelect?'button':undefined} aria-label={`${object.label}, ${human(object.policy)}`} className={`scene-object ${active?'selected':''}`}>
        {active&&<rect x={-ow/2-9} y={-oh/2-9} width={ow+18} height={oh+18} rx="12" fill="#78b8a21a" stroke="#2d8067" strokeWidth="1.8" strokeDasharray="4 3"/>}
        <g filter={`url(#${uid}-shadow)`}>
          {kind.includes('bed')&&!kind.includes('table')?<>
            <rect x={-ow/2-4} y={-oh/2-3} width={ow+8} height={oh+6} rx="9" fill="#c8d0cb"/>
            <rect x={-ow/2} y={-oh/2} width={ow} height={oh} rx="8" fill="#fafaf5" stroke="#d5dad4"/>
            <rect x={-ow/2+7} y={-oh/2+9} width={ow-14} height={oh*.21} rx="7" fill="white" stroke="#e1e5df"/>
            <rect x={-ow/2+5} y={-oh/2+oh*.35} width={ow-10} height={oh*.58} rx="5" fill="#c1d4c8"/>
            <path d={`M ${-ow/2+6} ${-oh/2+oh*.41} h ${ow-12}`} stroke="#e2ebe1" strokeWidth="3"/>
            <rect x={-ow/2-7} y={-oh/2+oh*.29} width="4" height={oh*.48} rx="2" fill="#9eaaa3"/>
            <rect x={ow/2+3} y={-oh/2+oh*.29} width="4" height={oh*.48} rx="2" fill="#9eaaa3"/>
          </>:kind.includes('chair')?<>
            <rect x={-ow/2} y={-oh/2} width={ow} height={oh} rx="9" fill="#a5b5a2" stroke="#899b87"/>
            <rect x={-ow/2+5} y={-oh/2+oh*.23} width={ow-10} height={oh*.62} rx="5" fill="#bbc7b4"/>
            <path d={`M ${-ow/2+2} ${-oh/2+oh*.18} h ${ow-4}`} stroke="#869981" strokeWidth="5"/>
          </>:kind.includes('phone')||kind.includes('remote')?<>
            <rect x={-ow/2} y={-oh/2} width={ow} height={oh} rx="3" fill="#374744" stroke="#183d34"/>
            <rect x={-ow/2+2} y={-oh/2+3} width={Math.max(2,ow-4)} height={Math.max(2,oh-7)} rx="1" fill="#9bbcae"/>
          </>:kind.includes('table')||kind.includes('cabinet')||kind.includes('drawer')?<>
            <rect x={-ow/2} y={-oh/2} width={ow} height={oh} rx="5" fill="#d9c5a8" stroke="#bba584"/>
            <path d={`M ${-ow/2+5} ${-oh/2+6} h ${ow-10} M ${-ow/2+5} ${oh/2-6} h ${ow-10}`} stroke="#ebdac3" strokeWidth="2"/>
          </>:<>
            <rect x={-ow/2} y={-oh/2} width={ow} height={oh} rx="5" fill={prohibited?'#dec6bf':'#d6dace'} stroke={prohibited?'#bc9185':'#a9b5a0'}/>
            {kind.includes('bag')&&<path d={`M -8 ${-oh/2+3} v -6 a 8 8 0 0 1 16 0 v 6`} fill="none" stroke="#85977c" strokeWidth="3"/>}
            {prohibited&&<path d="M -5 -5 5 5 M 5 -5 -5 5" stroke="#936658" strokeWidth="2"/>}
          </>}
        </g>
        {ow>45&&<text y={oh/2+17} textAnchor="middle" fontSize="10" fill="#5f6d65">{object.label}</text>}
        {kind.includes('phone')&&<g transform={`translate(${ow/2+9},-10)`}><rect x="0" y="-9" width="57" height="23" rx="6" fill="#fffdf7" stroke="#d5dfd3"/><circle cx="10" cy="2" r="3" fill="#629781"/><text x="18" y="5" fontSize="10" fill="#385b4c">Phone</text></g>}
      </g>;
    })}
    {robot?.pose&&<g transform={`translate(${sx(robot.pose.x)},${sy(robot.pose.y)})`}><circle r="31" fill="#9acbb626" stroke="#75ab93" strokeDasharray="3 5"/><circle r="19" fill="#315e4f" stroke="#e7efe5" strokeWidth="3"/><path d="M -6 -2 0 -9 6 -2 M 0 -8 V 9" fill="none" stroke="#e3eee2" strokeWidth="2"/><text y="46" textAnchor="middle" fill="#335b4b" fontSize="10">Vela · simulated</text></g>}
    {doorway&&<g><path d={`M ${sx(doorway.x)-27} ${sy(doorway.y)-8} h 54`} stroke="#f6f7ef" strokeWidth="20"/><path d={`M ${sx(doorway.x)-27} ${sy(doorway.y)-8} v 54 a 54 54 0 0 0 54 -54`} fill="none" stroke="#b7bfb3" strokeWidth="1"/><text x={sx(doorway.x)} y={sy(doorway.y)-30} textAnchor="middle" fill="#7e887c" fontSize="10" letterSpacing="2">ENTRANCE</text></g>}
    <text x={sx(w/2)} y={sy(h)+36} textAnchor="middle" fill="#7e887c" fontSize="10" letterSpacing="1.5">{w} × {h} m · SYNTHETIC ROOM</text>
    <g transform="translate(659 424)"><path d="M 0 0 h 22 m-5-3 5 3 -5 3 M0 0 v22 m-3-5 3 5 3-5" stroke="#8b998c" fill="none"/><text x="32" y="3" textAnchor="middle" fontSize="10" fill="#798b7b">x</text><text x="0" y="35" textAnchor="middle" fontSize="10" fill="#798b7b">y</text></g>
  </svg>;
}
