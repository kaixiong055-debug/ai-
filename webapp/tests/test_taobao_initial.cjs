const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../taobao_initial.js'),'utf8');
function read(window,scripts=[]){return vm.runInNewContext('('+source+')',{
 window,document:{querySelectorAll:()=>scripts.map(textContent=>({textContent,type:'text/javascript'}))},URL
})({itemId:'42'});}
const data={item:{itemId:'42',title:'本商品',images:['//img.alicdn.com/a']},skuBase:{props:[{values:[{image:'//img.alicdn.com/sku'}]}]},pcDescContent:'<img src="//img.alicdn.com/detail">',account:{cookie:'must-not-leave-browser'}};
test('extracts target from initial SSR state, excluding account fields',()=>{
 const result=read({__ICE_APP_CONTEXT__:{loaderData:{home:{data}}}});
 assert.equal(result.length,1);assert.equal(result[0].item.itemId,'42');
 assert.equal(result[0].skuBase.props[0].values[0].image,'//img.alicdn.com/sku');
 assert(!JSON.stringify(result).includes('must-not-leave-browser'));
});
test('reads inline JSON assignment without executing scripts',()=>{
 const result=read({},['window.__ICE_APP_CONTEXT__ = '+JSON.stringify({loaderData:{home:data}})+'; malicious();']);
 assert.equal(result.length,1);
});
test('does not promote unrelated/recommended or unidentified products',()=>{
 assert.equal(read({__ICE_APP_CONTEXT__:{recommendations:[data],other:{item:{itemId:'43',images:['x']}},unknown:{item:{images:['x']}}}}).length,0);
});
test('supports JSON.parse string literals and escaped braces safely',()=>{
 const script='window.__ICE_APP_CONTEXT__ = JSON.parse('+JSON.stringify(JSON.stringify({data:{...data,item:{...data.item,title:'title } " quoted'}}}))+');';
 const result=read({},[script]);assert.equal(result[0].item.title,'title } " quoted');
});
test('accepts JSON-LD only for a matching official product URL',()=>{
 const good={'@type':'Product',url:'https://item.taobao.com/item.htm?id=42',name:'JSON-LD',image:['https://img.alicdn.com/a']};
 assert.equal(read({__NEXT_DATA__:good})[0].item.title,'JSON-LD');
 assert.equal(read({__NEXT_DATA__:{...good,url:'https://item.taobao.com/item.htm?id=43'}}).length,0);
});
