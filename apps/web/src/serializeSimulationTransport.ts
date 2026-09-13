import type {SimulationTransport,ReferenceState} from './simulationTransport';

/** Keep reads and controls in invocation order. A late state request or visual
 * pause must settle before a subsequent reset/start can reach the runtime. */
export function serializeSimulationTransport(runtime:SimulationTransport):SimulationTransport{
  let tail:Promise<void>=Promise.resolve();
  let disposed=false;
  const aborted=()=>new DOMException('Simulation transport has been disposed','AbortError');
  const enqueue=(operation:()=>Promise<ReferenceState>):Promise<ReferenceState>=>{
    if(disposed)return Promise.reject(aborted());
    const result=tail.then(()=>{
      if(disposed)throw aborted();
      return operation();
    }).then(value=>{
      // An implementation may finish a read despite its disposal/abort signal.
      if(disposed)throw aborted();
      return value;
    });
    // Preserve the original rejection for its caller while allowing recovery
    // commands to proceed after a failed operation.
    tail=result.then(()=>undefined,()=>undefined);
    return result;
  };
  return{
    state:()=>enqueue(()=>runtime.state()),
    command:value=>enqueue(()=>runtime.command(value)),
    dispose:()=>{if(disposed)return;disposed=true;runtime.dispose()},
  };
}
