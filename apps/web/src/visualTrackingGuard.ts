/** Opt-in visual-observation watchdog. It consumes no simulator pose or depth.
 * A pause latch never clears itself when tracking recovers. The caller resets
 * it on an explicit new motion, reset or manual resume and sends an idempotent
 * pause command once per latch. This is a simulation aid, not certified safety.
 */
export type VisualTrackingGuardInput={enabled:boolean;moving:boolean;nowMs:number;frameAtMs:number|null;status:string;hasPose:boolean};
export type VisualTrackingGuardOptions={lossGraceMs?:number;maxFrameAgeMs?:number};

export class VisualTrackingGuard{
  readonly lossGraceMs:number;
  readonly maxFrameAgeMs:number;
  private lossSince:number|null=null;
  private pauseLatched=false;
  private lastNow:number|null=null;
  constructor(options:VisualTrackingGuardOptions={}){
    this.lossGraceMs=options.lossGraceMs??1500;this.maxFrameAgeMs=options.maxFrameAgeMs??750;
    if(![this.lossGraceMs,this.maxFrameAgeMs].every(value=>Number.isFinite(value)&&value>0))throw new Error('Watchdog durations must be finite and positive');
  }
  get latched(){return this.pauseLatched}
  reset(){this.lossSince=null;this.pauseLatched=false;this.lastNow=null}
  evaluate(input:VisualTrackingGuardInput):boolean{
    if(this.pauseLatched)return true;
    if(!input.enabled||!input.moving){this.lossSince=null;this.lastNow=null;return false}
    // A broken or backwards monotonic clock cannot safely time the grace
    // interval. It requests a pause instead of extending it indefinitely.
    if(!Number.isFinite(input.nowMs)||input.nowMs<0||(this.lastNow!==null&&input.nowMs<this.lastNow)){
      this.pauseLatched=true;return true;
    }
    this.lastNow=input.nowMs;
    const age=input.frameAtMs===null?Infinity:input.nowMs-input.frameAtMs;
    const healthy=input.hasPose&&(input.status==='tracking'||input.status==='relocalized')
      &&Number.isFinite(age)&&age>=0&&age<=this.maxFrameAgeMs;
    if(healthy){this.lossSince=null;return false}
    if(this.lossSince===null)this.lossSince=input.nowMs;
    if(input.nowMs-this.lossSince>=this.lossGraceMs)this.pauseLatched=true;
    return this.pauseLatched;
  }
}
