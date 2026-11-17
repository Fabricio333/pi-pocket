// Compatible with Sky's client/src/nostr/motion.ts. No browser or network imports.
export const MOTION_KIND = 20390;
export const GROUP_RELAYS = ['wss://public.obelisk.ar', 'wss://lacrypta-relay.obelisk.ar'];
export const PERMISSIONS = 'sign_event:20390,sign_event:22242';
export const START = {x:0,z:3.2};
export const EMOTES = new Set(['groove','dance','lotus','pushup','jacks','yes','no','arms','crouch','sangre']);
export function allowedPosition(p) {
  return p && Number.isFinite(p.x) && Number.isFinite(p.z) && Math.abs(p.x)<=4.5 && p.z>=-4 && p.z<=5
    && !(Math.abs(p.x)<1.95 && Math.abs(p.z-.5)<1.95);
}
export function stepPosition(p,input,dt) {
  const dx=Math.max(-1,Math.min(1,Number(input.x)||0));
  const dz=Math.max(-1,Math.min(1,Number(input.z)||0));
  const length=Math.hypot(dx,dz);
  if (!length) return {...p};
  const speed=input.run?2.6:.78;
  const distance=speed*Math.min(.15,Math.max(0,dt));
  const desired={x:p.x+dx/length*distance,z:p.z+dz/length*distance};
  if(allowedPosition(desired))return desired;
  const horizontal={x:desired.x,z:p.z},vertical={x:p.x,z:desired.z};
  if(allowedPosition(horizontal))return horizontal;
  if(allowedPosition(vertical))return vertical;
  return {...p};
}
export function motionTemplate(state,now=Date.now()) {
  if(!allowedPosition(state.p))throw Error('Position outside the plaza');
  const at=Math.floor(now/1000),round=n=>Math.round(n*100)/100;
  const c={v:1,t:Math.round(now),p:[round(state.p.x),round(state.p.z)],y:round(state.yaw||0)};
  // A finite destination makes a lost connection stop safely, rather than drift.
  if(state.moving&&state.dest&&allowedPosition(state.dest)) {
    c.mv=1;c.d=[round(state.dest.x),round(state.dest.z)];if(state.run)c.run=1;
  }
  if(state.jump)c.j=1;
  if(!state.moving&&state.emote){c.e=state.emote;c.es=state.emoteSince||now;}
  return {kind:MOTION_KIND,created_at:at,tags:[['t','obelisk-sky-motion'],['expiration',String(at+60)]],content:JSON.stringify(c)};
}
export function assertRequestedEvent(template,relay) {
  if(template.kind===22242) {
    const relays=template.tags.filter(t=>t[0]==='relay'),challenges=template.tags.filter(t=>t[0]==='challenge');
    if(relays.length!==1||new URL(relays[0][1]).href!==new URL(relay).href||challenges.length!==1||!challenges[0][1]||template.content!=='')
      throw Error('Invalid relay authentication request');
    return;
  }
  if(template.kind!==MOTION_KIND)throw Error('Event kind is outside controller permissions');
  const c=JSON.parse(template.content);
  if(c.v!==1||!Array.isArray(c.p)||!allowedPosition({x:c.p[0],z:c.p[1]}))throw Error('Invalid movement');
  if(!template.tags.some(t=>t[0]==='t'&&t[1]==='obelisk-sky-motion'))throw Error('Missing movement tag');
}
export function assertSignedEvent(signed,template,pubkey,verify) {
  // Copy explicit wire fields: nostr-tools attaches a cached verification symbol.
  const event=signed&&{id:signed.id,pubkey:signed.pubkey,sig:signed.sig,kind:signed.kind,
    created_at:signed.created_at,tags:signed.tags,content:signed.content};
  if(!event||event.pubkey!==pubkey||!verify(event) ||
    JSON.stringify([event.kind,event.created_at,event.tags,event.content])!==
    JSON.stringify([template.kind,template.created_at,template.tags,template.content]))
    throw Error('Signer returned a different or invalid event');
  return event;
}
