'use strict';
// One refresh at a time; schedule from completion, never from request start.
function createPoller({refresh,hidden,error,setTimer=setTimeout,clearTimer=clearTimeout}){
 let timer=null,inFlight=null,pending=false;
 function pause(){if(timer!==null)clearTimer(timer);timer=null;}
 function wake(){pause();if(inFlight){pending=true;return}if(!hidden())timer=setTimer(()=>{void poll()},0);}
 function poll(){
  pause();
  if(inFlight)return inFlight;
  if(hidden())return Promise.resolve();
  let delay=30000;
  // Assign the shared promise before refresh can trigger another wake.
  inFlight=Promise.resolve().then(refresh).then(ms=>{delay=ms}).catch(error).finally(()=>{
   inFlight=null;
   if(!hidden()){pause();timer=setTimer(()=>{void poll()},pending?0:delay);pending=false;}
  });
  return inFlight;
 }
 return {poll,wake,pause};
}
if(typeof module!=='undefined')module.exports={createPoller};
