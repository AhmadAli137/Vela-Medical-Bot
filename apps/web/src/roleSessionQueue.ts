/** Serialize cookie-changing logins; only the latest requested role may commit.
 * Automatic route changes and explicit role selections share this queue.
 */
export type RoleCredentials={role:string;token?:string};
export type RoleSessionResult<T>={revision:number;role:string;data:T};

export class RoleSessionQueue<T>{
  private tail:Promise<void>=Promise.resolve();
  private generation=0;
  private disposed=false;
  private waiting=false;
  private controller=new AbortController();
  constructor(private login:(credentials:RoleCredentials,signal:AbortSignal)=>Promise<unknown>,private bootstrap:(signal:AbortSignal)=>Promise<T>){}
  get revision(){return this.generation}
  get pending(){return this.waiting}
  isCurrent(revision:number){return !this.disposed&&revision===this.generation}
  request(credentials:RoleCredentials):{revision:number;promise:Promise<RoleSessionResult<T>|null>}{
    const revision=++this.generation;
    this.waiting=!this.disposed;
    const promise=this.tail.then(async()=>{
      if(!this.isCurrent(revision))return null;
      // Await an old login before issuing the new one. Ignoring its UI result
      // alone would still let its late Set-Cookie overwrite the current role.
      await this.login(credentials,this.controller.signal);
      if(!this.isCurrent(revision))return null;
      const data=await this.bootstrap(this.controller.signal);
      return this.isCurrent(revision)?{revision,role:credentials.role,data}:null;
    }).catch(error=>{
      if(!this.isCurrent(revision))return null;
      throw error;
    }).finally(()=>{if(this.isCurrent(revision))this.waiting=false});
    this.tail=promise.then(()=>undefined,()=>undefined);
    return {revision,promise};
  }
  dispose(){this.disposed=true;this.waiting=false;this.generation++;this.controller.abort()}
}
