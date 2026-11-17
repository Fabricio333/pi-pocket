import {getPublicKey} from 'nostr-tools';
import {BunkerSigner,createNostrConnectURI} from 'nostr-tools/nip46';
import {SimplePool} from 'nostr-tools/pool';

// Human approval is not a network timeout. Only explicit cancellation ends the wait.
export function waitForApproval(promise,{signal,onWaiting=()=>{},noticeAfterMs=1500}={}) {
  return new Promise((resolve,reject)=>{
    let settled=false;
    const finish=(error,value)=>{
      if(settled)return;settled=true;clearTimeout(notice);signal?.removeEventListener('abort',cancel);
      if(error)reject(error);else resolve(value);
    };
    const cancel=()=>finish(new Error('Signer request cancelled'));
    const notice=setTimeout(()=>{if(!settled)onWaiting();},noticeAfterMs);
    if(signal?.aborted){cancel();return;}
    signal?.addEventListener('abort',cancel,{once:true});
    Promise.resolve(promise).then(v=>finish(null,v),e=>finish(e||new Error('Signer rejected request')));
  });
}

// Same nostr-tools handshake used by the SDK, without the SDK's five-minute timer.
export function startPairing({clientSecretKey,relays,secret,perms,metadata={},onAuthChallenge,pool}) {
  const controller=new AbortController(),transport=pool||new SimplePool();let paired=null;
  const uri=createNostrConnectURI({clientPubkey:getPublicKey(clientSecretKey),relays,secret,
    perms:perms.split(','),name:metadata.name,url:metadata.url});
  const ready=BunkerSigner.fromURI(clientSecretKey,uri,{pool:transport,onauth:onAuthChallenge},controller.signal)
    .then(signer=>{paired=signer;return signer;});
  return {uri,ready,cancel:()=>{controller.abort();void paired?.close();if(!pool)transport.destroy();}};
}
