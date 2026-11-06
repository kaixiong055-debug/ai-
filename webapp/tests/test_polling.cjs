const {test}=require('node:test');
const assert=require('node:assert/strict');
const {createPoller}=require('../static/polling.js');
test('slow polls do not overlap; next timer starts after completion',async()=>{
 let release,calls=0,timers=[];
 const p=createPoller({refresh:()=>{calls++;return new Promise(r=>release=r)},hidden:()=>false,setTimer:(fn,ms)=>{timers.push(ms);return 1},clearTimer:()=>{},error:()=>{}});
 const first=p.poll();const second=p.poll();await Promise.resolve();assert.equal(calls,1);assert.deepEqual(timers,[]);
 release(30000);await Promise.all([first,second]);assert.deepEqual(timers,[30000]);
});
test('hidden pages pause; returning resumes; errors retry slowly',async()=>{
 let hidden=true,calls=0,delay;
 const p=createPoller({refresh:async()=>{calls++;throw Error('offline')},hidden:()=>hidden,setTimer:(fn,ms)=>{delay=ms;return 1},clearTimer:()=>{},error:()=>{}});
 await p.poll();assert.equal(calls,0);assert.equal(delay,undefined);
 hidden=false;await p.poll();assert.equal(calls,1);assert.equal(delay,30000);
});
test('user changes during an in-flight request trigger one immediate follow-up',async()=>{
 let release,delay;
 const p=createPoller({refresh:()=>new Promise(r=>release=r),hidden:()=>false,setTimer:(fn,ms)=>{delay=ms;return 1},clearTimer:()=>{},error:()=>{}});
 const request=p.poll();await Promise.resolve();p.wake();p.wake();release(30000);await request;
 assert.equal(delay,0);
});
