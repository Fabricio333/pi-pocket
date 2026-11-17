// Full NIP-46 exchange over a loopback-only relay; no real user keys or public posts.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import WebSocket,{WebSocketServer} from 'ws';
import {once} from 'node:events';
import {Nip46Signer} from 'nostr-wot-sdk/signers';
import {SimplePool,useWebSocketImplementation} from 'nostr-tools/pool';
import {generateSecretKey,getPublicKey,finalizeEvent,verifyEvent} from 'nostr-tools';
import * as nip44 from 'nostr-tools/nip44';
import {PERMISSIONS,START,motionTemplate,assertSignedEvent} from './protocol.mjs';
import {startPairing,waitForApproval} from './approval.mjs';

for(const implementation of ['SDK','persistent'])test(implementation+' pairs, ignores wrong secrets, and preserves pending approvals',{timeout:15000},async t=>{
 useWebSocketImplementation(WebSocket);globalThis.WebSocket=WebSocket;
 const server=new WebSocketServer({host:'127.0.0.1',port:0});await once(server,'listening');
 const url='ws://127.0.0.1:'+server.address().port;
 const remote=generateSecretKey(),account=generateSecretKey(),accountPk=getPublicKey(account);
 const pool=new SimplePool();let signer=null,uri=null,pairSent=false;
 t.after(async()=>{
  await signer?.close().catch(()=>{});pool.close([url]);pool.destroy?.();
  for(const socket of server.clients)socket.terminate();
  await new Promise(resolve=>server.close(resolve));
 });
 server.on('connection',socket=>{
  const subscriptions=new Map();
  const deliver=(client,response)=>{
   const key=nip44.v2.utils.getConversationKey(remote,client);
   const event=finalizeEvent({kind:24133,created_at:Math.floor(Date.now()/1000),tags:[['p',client]],
    content:nip44.v2.encrypt(JSON.stringify(response),key)},remote);
   for(const [id,filter]of subscriptions)
    if(filter['#p']?.includes(client))socket.send(JSON.stringify(['EVENT',id,event]));
  };
  socket.on('message',raw=>{
   const m=JSON.parse(raw.toString());
   if(m[0]==='REQ'){
    subscriptions.set(m[1],m[2]);socket.send(JSON.stringify(['EOSE',m[1]]));
    if(!pairSent&&uri&&m[2]['#p']?.[0]){
     pairSent=true;const client=new URL(uri).hostname,secret=new URL(uri).searchParams.get('secret');
     setTimeout(()=>deliver(client,{id:'wrong',result:'invalid-pairing-secret'}),10);
     setTimeout(()=>deliver(client,{id:'correct',result:secret}),80);
    }
   }else if(m[0]==='CLOSE')subscriptions.delete(m[1]);
   else if(m[0]==='EVENT'){
    const event=m[1];assert.ok(verifyEvent(event));socket.send(JSON.stringify(['OK',event.id,true,'']));
    const key=nip44.v2.utils.getConversationKey(remote,event.pubkey);
    const request=JSON.parse(nip44.v2.decrypt(event.content,key));
    let result;
    if(request.method==='get_public_key')result=accountPk;
    else if(request.method==='switch_relays')result='null';
    else if(request.method==='sign_event'){
     result=JSON.stringify(finalizeEvent(JSON.parse(request.params[0]),account));
     setTimeout(()=>deliver(event.pubkey,{id:request.id,result}),40);return;
    }
    else result='ack';
    deliver(event.pubkey,{id:request.id,result});
   }
  });
 });
 const options={pool,relays:[url],clientSecretKey:generateSecretKey(),perms:PERMISSIONS,
  secret:'loopback-pairing-secret',metadata:{name:'Pocket offline test'},pairTimeoutMs:implementation==='SDK'?8000:30};
 const handle=implementation==='SDK'?Nip46Signer.startNostrConnect(options):startPairing(options);
 uri=handle.uri;
 assert.equal(new URL(uri).searchParams.get('perms'),PERMISSIONS);
 signer=await handle.ready;
 assert.notEqual(signer.bunkerPubkey||signer.bp.pubkey,accountPk);
 assert.equal(await signer.getPublicKey(),accountPk);
 const template=motionTemplate({p:START,moving:false});
 let waiting=0;
 const signed=await waitForApproval(signer.signEvent(template),{noticeAfterMs:5,onWaiting:()=>waiting++});
 assert.equal(waiting,1);
 assert.equal(assertSignedEvent(signed,template,accountPk,verifyEvent).pubkey,accountPk);
});

test('pending approval ends on explicit cancellation, not the waiting notice',async()=>{
 const abort=new AbortController();let noticed=false;
 const pending=waitForApproval(new Promise(()=>{}),{signal:abort.signal,noticeAfterMs:1,onWaiting:()=>noticed=true});
 await new Promise(resolve=>setTimeout(resolve,15));assert.equal(noticed,true);
 abort.abort();await assert.rejects(pending,/cancelled/);
});
