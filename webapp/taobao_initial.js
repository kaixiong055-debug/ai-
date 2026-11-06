// Runs inside the product page. Only allowlisted product fields leave the browser.
({itemId}) => {
 const names=['__ICE_APP_CONTEXT__','__ICE_DATA__','__INITIAL_STATE__','__INITIAL_DATA__','__INIT_DATA__','__NEXT_DATA__','__PRELOADED_STATE__'];
 const roots=[],seen=new WeakSet(),results=[];
 for(const name of names){try{if(window[name])roots.push(window[name]);}catch{}}
 // Decode a JSON literal prefix; never evaluate script code or callback functions.
 function literal(text){
  text=text.trimStart();const first=text[0];if(!['{','[','"'].includes(first))return null;
  let depth=0,string=false,escaped=false;
  for(let i=0;i<text.length;i++){
   const c=text[i];
   if(string){if(escaped)escaped=false;else if(c==='\\')escaped=true;else if(c==='"'){string=false;if(first==='"'){try{return JSON.parse(text.slice(0,i+1))}catch{return null}}}continue;}
   if(c==='"'){string=true;continue;}
   if(c==='{'||c==='[')depth++;
   if(c==='}'||c===']'){depth--;if(depth===0){try{return JSON.parse(text.slice(0,i+1))}catch{return null}}}
  }
  return null;
 }
 let bytes=0;
 for(const script of Array.from(document.querySelectorAll('script:not([src])')).slice(0,100)){
  const text=script.textContent||'';bytes+=text.length;if(bytes>4000000)break;
  if(script.type==='application/json'||script.type==='application/ld+json'){
   try{roots.push(JSON.parse(text))}catch{}continue;
  }
  for(const name of names){
   const match=new RegExp('(?:window\\.)?'+name+'\\s*=\\s*(?:JSON\\.parse\\(\\s*)?').exec(text);
   if(match){let value=literal(text.slice(match.index+match[0].length));if(typeof value==='string'){try{value=JSON.parse(value)}catch{value=null}}if(value)roots.push(value);}
  }
 }
 function textValue(v){return typeof v==='string'?v.slice(0,1000000):v&&typeof v.content==='string'?{content:v.content.slice(0,1000000)}:'';}
 const stack=roots.map(value=>({value,depth:0}));let visited=0;
 while(stack.length&&visited++<12000&&results.length<30){
  let {value:v,depth}=stack.pop();if(depth>18)continue;
  if(typeof v==='string'&&v.length<2000000&&/^[\s]*[\[{]/.test(v)){try{v=JSON.parse(v)}catch{continue}}
  if(!v||typeof v!=='object'||seen.has(v))continue;seen.add(v);
  const item=v.item;
  if(item&&typeof item==='object'&&String(item.itemId||item.id||'')===itemId&&Array.isArray(item.images)){
   const clean={item:{itemId,title:typeof item.title==='string'?item.title.slice(0,200):'',images:item.images.slice(0,300).map(i=>typeof i==='string'?i:{url:i?.url||i?.image})}};
   for(const key of ['pcDescContent','desc','description']){clean[key]=textValue(v[key]);clean.item[key]=textValue(item[key]);}
   if(Array.isArray(v.skuBase?.props))clean.skuBase={props:v.skuBase.props.slice(0,100).map(p=>({values:Array.isArray(p.values)?p.values.slice(0,500).map(i=>({image:i.image})):[]}))};
   results.push(clean);
  }
  // Product JSON-LD is accepted only when its own URL identifies the requested item.
  if(v['@type']==='Product'&&typeof v.url==='string'){
   try{const u=new URL(v.url);if(['item.taobao.com','detail.tmall.com'].includes(u.hostname)&&u.searchParams.get('id')===itemId){
    const images=Array.isArray(v.image)?v.image:typeof v.image==='string'?[v.image]:[];
    results.push({item:{itemId,title:typeof v.name==='string'?v.name:'',images},description:textValue(v.description)});
   }}catch{}
  }
  for(const [key,value] of Object.entries(v).slice(0,1000)){
   if(/recommend|related|seller|shop|account|cookie|token|user|cart|basket/i.test(key))continue;
   if(value&&['object','string'].includes(typeof value))stack.push({value,depth:depth+1});
  }
 }
 return results;
}
