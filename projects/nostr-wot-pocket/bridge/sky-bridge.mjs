import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import readline from 'node:readline';
import {randomBytes} from 'node:crypto';
import WebSocket from 'ws';
import {BunkerSigner} from 'nostr-tools/nip46';
import {Relay,useWebSocketImplementation} from 'nostr-tools/relay';
import {SimplePool,useWebSocketImplementation as usePoolWebSocket} from 'nostr-tools/pool';
import {generateSecretKey,verifyEvent,nip19} from 'nostr-tools';
import {GROUP_RELAYS,PERMISSIONS,START,EMOTES,stepPosition,motionTemplate,assertRequestedEvent,assertSignedEvent} from './protocol.mjs';
import {startPairing,waitForApproval} from './approval.mjs';

globalThis.WebSocket=WebSocket;useWebSocketImplementation(WebSocket);usePoolWebSocket(WebSocket);
const emit=(type,data={})=>process.stdout.write(JSON.stringify({type,...data})+'\n');
const clean=e=>String(e?.message||e).replace(/(?:nsec1|bunker:\/\/|nostrconnect:\/\/)\S+/gi,'[private]').slice(0,150);
const lifetime=new AbortController();
const approval=(promise,stage)=>{
  emit('approval',{stage,waiting:true});
  return waitForApproval(promise,{signal:lifetime.signal,onWaiting:()=>emit('approval',{stage,waiting:true})})
    .then(value=>{emit('approval',{stage,waiting:false,approved:true});return value;},
          error=>{emit('approval',{stage,waiting:false,approved:false});throw error;});
};
const stateDir=process.env.POCKET_STATE_DIR||path.join(os.homedir(),'.local/share/nostr-wot-pocket');
fs.mkdirSync(stateDir,{recursive:true,mode:0o700});
const sessionFile=path.join(stateDir,'sky-session.json');
let group=GROUP_RELAYS.includes(process.env.POCKET_SKY_RELAY)?process.env.POCKET_SKY_RELAY:GROUP_RELAYS[0];
let signer=null,user=null,relay=null,pairing=null,signerPool=null,closed=false,connected=false,authing=false;
let signing=Promise.resolve(),sending=false,lastSent=0,lastSignature='',slowdown=1,lastState=0;
let position={...START},yaw=0,input={x:0,z:0,run:false},lastInput=Date.now(),lastStep=Date.now();
let jumpAt=0,emote=null,emoteSince=0,accepted=0,seen=0,peers=new Map(),timer=null;
function checkedSign(template){
  assertRequestedEvent(template,group);
  const operation=async()=>{
    const stage=template.kind===22242?'relay':'movement';let requested=template;
    return approval((async()=>{
      while(!closed){
        const event=assertSignedEvent(await signer.signEvent(requested),requested,user,verifyEvent);
        if(requested.kind===22242&&Date.now()/1000-requested.created_at>45){
          requested={...requested,created_at:Math.floor(Date.now()/1000)};continue;
        }
        return event;
      }
      throw Error('Signer request cancelled');
    })(),stage);
  };
  const job=signing.then(operation,operation);signing=job.catch(()=>{});return job;
}
function persist(clientSecret,bunker,relays){
  const value={v:1,clientSecret,bunker,relays,user,group};
  const temporary=sessionFile+'.tmp';fs.writeFileSync(temporary,JSON.stringify(value),{mode:0o600});
  fs.chmodSync(temporary,0o600);fs.renameSync(temporary,sessionFile);
}
function authChallenge(url){
  try{if(new URL(url).protocol==='https:')emit('auth',{uri:url});}catch{}
}
async function pair(){
  user=null;
  emit('status',{status:'pairing'});
  const secret=generateSecretKey();
  pairing=startPairing({clientSecretKey:secret,relays:['wss://nos.lol','wss://relay.primal.net'],
    secret:randomBytes(16).toString('hex'),perms:PERMISSIONS,
    metadata:{name:'Nostr WoT Pocket · Sky',url:'https://github.com/Fabricio333/nostr-wot-pocket'},onAuthChallenge:authChallenge});
  emit('pairing',{uri:pairing.uri});
  signer=await pairing.ready;emit('paired');
  persist(Buffer.from(secret).toString('hex'),signer.bp.pubkey,signer.bp.relays);
  user=await approval(signer.getPublicKey(),'account');
  if(!/^[0-9a-f]{64}$/.test(user))throw Error('Signer returned an invalid account');
  persist(Buffer.from(secret).toString('hex'),signer.bp.pubkey,signer.bp.relays);
}
async function restore(){
  if(!fs.existsSync(sessionFile))return false;
  const s=JSON.parse(fs.readFileSync(sessionFile,'utf8'));
  if(s.v!==1||!/^[0-9a-f]{64}$/.test(s.clientSecret)||(s.user!==null&&!/^[0-9a-f]{64}$/.test(s.user))||!Array.isArray(s.relays))throw Error('Invalid stored signer session');
  emit('status',{status:'restoring'});
  signerPool=new SimplePool();
  signer=BunkerSigner.fromBunker(Uint8Array.from(Buffer.from(s.clientSecret,'hex')),
    {pubkey:s.bunker,relays:s.relays,secret:null},{pool:signerPool,onauth:authChallenge});
  user=await approval(signer.getPublicKey(),'account');
  if(!/^[0-9a-f]{64}$/.test(user))throw Error('Signer returned an invalid account');
  if(s.user&&user!==s.user)throw Error('Remote signer account changed');
  if(GROUP_RELAYS.includes(s.group))group=s.group;
  persist(s.clientSecret,s.bunker,s.relays);
  return true;
}
async function connectRelay(){
  if(closed)return;
  emit('status',{status:'connecting',pubkey:user,relay:group});
  relay=new Relay(group,{enableReconnect:false,enablePing:true});relay.publishTimeout=12000;
  relay.onauth=t=>{authing=true;emit('status',{status:'authorizing'});return checkedSign(t).finally(()=>{authing=false;});};
  relay.onclose=()=>{
    if(closed)return;connected=false;emit('status',{status:'reconnecting'});
    setTimeout(()=>connectRelay().catch(failed),3000);
  };
  relay.onnotice=()=>{};
  await relay.connect({timeout:10000});connected=true;
  const subscribe=()=>relay.subscribe([{kinds:[20390],since:Math.floor(Date.now()/1000)-10}],{
    onevent:e=>{
      try{
        const c=JSON.parse(e.content);if(c.v!==1||!Array.isArray(c.p)||!c.p.every(Number.isFinite))return;
        if(e.pubkey===user){seen++;emit('observed',{seen,id:e.id});}
        else peers.set(e.pubkey,{x:c.p[0],z:c.p[1],at:Date.now()});
      }catch{}
    },
    onclose:reason=>{
      if(!closed&&/auth|required|restricted/i.test(reason))
        waitForApproval(relay.auth(checkedSign),{signal:lifetime.signal}).then(subscribe).catch(e=>emit('status',{status:'refused',message:clean(e)}));
    },
  });subscribe();
  relay.subscribe([{kinds:[0],authors:[user],limit:1}],{onevent:e=>{
    try{const p=JSON.parse(e.content);emit('profile',{name:String(p.display_name||p.name||'').slice(0,32)});}catch{}
  }});
  emit('connected',{pubkey:user,npub:nip19.npubEncode(user),relay:group});
}
function failed(error){emit('error',{message:clean(error)});}
async function publishMotion(force=false){
  const now=Date.now();if(!signer||!connected||closed||sending||authing)return;
  const active=now-lastInput<500?input:{x:0,z:0,run:input.run};
  const dx=active.x||0,dz=active.z||0,length=Math.hypot(dx,dz),moving=length>0;
  let dest=null;
  if(moving){
    yaw=Math.atan2(dx,dz);dest={...position};
    // Bound a destination to roughly one second ahead; no endless heading if the Pi disappears.
    for(let i=0;i<8;i++)dest=stepPosition(dest,active,.125);
    if(Math.hypot(dest.x-position.x,dest.z-position.z)<.01)dest=null;
  }
  const jumpToken=jumpAt,jumping=!!jumpToken;
  const snapshot={p:position,moving:moving&&!!dest,dest,run:active.run,yaw,jump:!!jumping,emote,emoteSince};
  const signature=JSON.stringify([Math.sign(dx),Math.sign(dz),active.run,emote,emoteSince,!!jumping,!!dest]);
  const gap=(jumping?400:1000)*slowdown;
  if(!force&&(now-lastSent<gap||signature===lastSignature&&now-lastSent<(moving?2000:30000)*slowdown))return;
  sending=true;lastSent=now;lastSignature=signature;
  try{
    const template=motionTemplate(snapshot,now),event=await checkedSign(template);
    if(closed)return;
    if(Date.now()-now>15000){
      if(emote)emoteSince=Date.now();
      lastSent=0;lastSignature='';emit('status',{status:'approval-received'});return;
    }
    try{await relay.publish(event);}catch(e){
      if(!/auth|required|restricted/i.test(String(e)))throw e;
      await waitForApproval(relay.auth(checkedSign),{signal:lifetime.signal});await relay.publish(event);
    }
    accepted++;slowdown=Math.max(1,slowdown/2);if(jumping&&jumpAt===jumpToken)jumpAt=0;
    emit('published',{accepted,id:event.id});
  }catch(error){if(!closed){slowdown=Math.min(8,slowdown*2);failed(error);}}
  finally{sending=false;}
}
function tick(){
  const now=Date.now(),dt=Math.min(.15,(now-lastStep)/1000);lastStep=now;
  if(connected&&now-lastInput<500){position=stepPosition(position,input,dt);if(input.x||input.z)emote=null;}
  void publishMotion();
  if(now-lastState>200){
    for(const [pk,p]of peers)if(now-p.at>75000)peers.delete(pk);
    emit('state',{position,yaw,run:input.run,emote,sending,accepted,seen,peers:[...peers.values()].slice(0,24)});lastState=now;
  }
}
async function close(forget=false){
  if(closed)return;
  // Destinations are finite, so shutdown never leaves an avatar walking indefinitely.
  input={x:0,z:0,run:false};lastInput=Date.now();emote=null;
  if(!sending&&connected&&Date.now()-lastSent>=1000)await Promise.race([publishMotion(true),new Promise(r=>setTimeout(r,1800))]);
  closed=true;lifetime.abort();clearInterval(timer);pairing?.cancel();signerPool?.destroy();relay?.close();
  if(forget&&fs.existsSync(sessionFile))fs.unlinkSync(sessionFile);
  await Promise.race([signer?.close?.(),new Promise(r=>setTimeout(r,500))]);process.exit(0);
}
readline.createInterface({input:process.stdin}).on('line',line=>{
  try{
    const c=JSON.parse(line);
    if(c.op==='input'){
      input={x:Math.sign(Number(c.x)||0),z:Math.sign(Number(c.z)||0),run:!!c.run};lastInput=Date.now();
      if(input.x||input.z)emote=null;
    }else if(c.op==='jump'){jumpAt=Date.now();emote=null;}
    else if(c.op==='emote'){
      if(c.value===null||EMOTES.has(c.value)){emote=c.value;emoteSince=Date.now();}
    }else if(c.op==='close')void close();
    else if(c.op==='forget')void close(true);
  }catch{}
}).on('close',()=>void close());
process.on('SIGTERM',()=>void close());process.on('SIGINT',()=>void close());
try{
  let restored=false;
  try{restored=await restore();}catch(e){failed(e);await signer?.close?.();signerPool?.destroy();signerPool=null;signer=null;user=null;}
  if(!restored)await pair();
  await connectRelay();timer=setInterval(tick,50);
}catch(error){failed(error);emit('status',{status:'failed'});setTimeout(()=>void close(),1000);}
