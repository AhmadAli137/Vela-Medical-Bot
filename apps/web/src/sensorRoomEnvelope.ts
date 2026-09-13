import * as THREE from 'three';

/** Complete the room's cutaway surfaces for on-robot cameras. The outside
 * overview hides these surfaces so the patient and furniture remain visible. */
export function createSensorRoomEnvelope(){
  const group=new THREE.Group();group.name='camera_room_enclosure';group.visible=false;
  const wall=new THREE.MeshStandardMaterial({color:'#eeece3',roughness:.91});
  const wood=new THREE.MeshStandardMaterial({color:'#a89378',roughness:.55});
  const trim=new THREE.MeshStandardMaterial({color:'#e1e6e1',roughness:.43});
  const dark=new THREE.MeshStandardMaterial({color:'#50656a',roughness:.35,metalness:.3});
  const metal=new THREE.MeshStandardMaterial({color:'#9ca6a7',roughness:.24,metalness:.8});
  const box=(name:string,p:number[],s:number[],material:THREE.Material)=>{const mesh=new THREE.Mesh(new THREE.BoxGeometry(...s as [number,number,number]),material);mesh.name=name;mesh.position.fromArray(p);mesh.receiveShadow=true;group.add(mesh);return mesh};
  box('Cutaway right wall',[3.55,-1.1,1.5],[.1,3.8,3],wall);
  box('Cutaway front wall',[0,-3.05,1.5],[7,.1,3],wall);
  box('Cutaway ceiling',[0,0,3.05],[7,6,.1],wall);
  box('Right baseboard',[3.485,-1.1,.08],[.025,3.8,.16],trim);
  box('Front baseboard',[0,-2.985,.08],[7,.025,.16],trim);
  box('Room door frame',[3.47,-1.3,1.08],[.07,1.13,2.16],trim);
  box('Room door',[3.423,-1.3,1.05],[.026,.97,2.1],wood);
  box('Door kick plate',[3.405,-1.3,.20],[.009,.92,.33],metal);
  box('Door observation frame',[3.405,-1.30,1.61],[.012,.42,.43],trim);
  box('Door observation glazing',[3.395,-1.30,1.61],[.009,.36,.37],dark);
  box('Door handle plate',[3.397,-1.66,1.05],[.016,.048,.21],metal);
  box('Door lever',[3.367,-1.60,1.10],[.045,.18,.025],metal);
  box('Room entry plaque',[3.474,-.57,1.53],[.025,.23,.16],dark);
  for(const z of [1.50,1.54,1.57])box('Plaque raised lettering',[3.457,-.57,z],[.004,.14,.008],trim);
  for(const [x,y] of [[-1.3,-.7],[1.3,1.25]]){
    box('Ceiling light trim',[x,y,2.985],[.68,1.2,.035],metal);
    const diffuser=new THREE.MeshStandardMaterial({color:'#fbfaf2',emissive:'#fff8e5',emissiveIntensity:.22,roughness:.6});
    box('Ceiling light diffuser',[x,y,2.962],[.63,1.15,.018],diffuser);
  }
  for(const x of [-2,-.4,1.2]){
    box('Front wall framed art',[x,-2.981,1.65],[.55,.03,.72],wood);
    box('Front wall art mat',[x,-2.96,1.65],[.49,.009,.66],trim);
    box('Front wall botanical print',[x,-2.952,1.65],[.34,.008,.47],dark);
  }
  return group;
}
