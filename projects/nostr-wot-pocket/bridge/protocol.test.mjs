import {test} from 'node:test';
import assert from 'node:assert/strict';
import {finalizeEvent,generateSecretKey,getPublicKey,verifyEvent} from 'nostr-tools';
import {motionTemplate,stepPosition,allowedPosition,assertRequestedEvent,assertSignedEvent,START} from './protocol.mjs';

test('movement uses the real Sky wire format and a finite destination',()=>{
 const template=motionTemplate({p:START,moving:true,dest:{x:1,z:3.2},run:false,yaw:1},1793990000000);
 assert.equal(template.kind,20390);
 assert.deepEqual(template.tags,[['t','obelisk-sky-motion'],['expiration','1793990060']]);
 const c=JSON.parse(template.content);assert.deepEqual(c.p,[0,3.2]);assert.deepEqual(c.d,[1,3.2]);assert.equal(c.mv,1);assert.equal(c.h,undefined);
});
test('plaza walking matches Sky speeds, blocks the plinth, and stays bounded',()=>{
 const p=stepPosition(START,{x:1,z:0,run:false},.1);assert.ok(Math.abs(p.x-.078)<1e-8);
 const running=stepPosition(START,{x:1,z:0,run:true},.1);assert.ok(Math.abs(running.x-.26)<1e-8);
 let current={x:0,z:2.5};for(let i=0;i<200;i++)current=stepPosition(current,{x:0,z:-1,run:true},.1);
 assert.ok(allowedPosition(current));assert.ok(current.z>=2.45);
 current=START;for(let i=0;i<500;i++)current=stepPosition(current,{x:1,z:1,run:true},.1);
 assert.ok(allowedPosition(current));assert.ok(current.x<=4.5&&current.z<=5);
});
test('only movement and AUTH for the selected relay can be signed',()=>{
 const relay='wss://public.obelisk.ar';
 assert.doesNotThrow(()=>assertRequestedEvent({kind:22242,content:'',tags:[['relay',relay+'/'],['challenge','test']]},relay));
 assert.throws(()=>assertRequestedEvent({kind:1,content:'post',tags:[]},relay));
 assert.throws(()=>assertRequestedEvent({kind:22242,content:'',tags:[['relay','wss://evil.example'],['challenge','test']]},relay));
});
test('signature validation rejects changed templates and switched accounts',()=>{
 const sk=generateSecretKey(),pubkey=getPublicKey(sk),template=motionTemplate({p:START,moving:false});
 const signed=finalizeEvent(template,sk);
 assert.equal(assertSignedEvent(signed,template,pubkey,verifyEvent).id,signed.id);
 assert.throws(()=>assertSignedEvent(signed,{...template,content:'changed'},pubkey,verifyEvent));
 assert.throws(()=>assertSignedEvent(signed,template,getPublicKey(generateSecretKey()),verifyEvent));
 assert.throws(()=>assertSignedEvent({...signed,sig:'00'.repeat(64)},template,pubkey,verifyEvent));
});
