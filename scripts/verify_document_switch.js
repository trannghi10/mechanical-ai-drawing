// A slow earlier document response must not replace the newly opened file.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('frontend/index.html','utf8').split('<script>')[1].split('</script>')[0];
const nodes=new Map();const $=id=>{if(!nodes.has(id))nodes.set(id,{textContent:'',value:'',hidden:false,replaceChildren(){},add(){}});return nodes.get(id)};
let releaseOld;
const context={$,doc:'A',documentLoad:0,items:[],selected:new Set(),revisionItems:[],URLSearchParams,
 location:{search:'?doc=B'},Option:class{},setTimeout,show:async()=>{},render(){},
 refreshHistory:async()=>{},refreshRevisions:async()=>{},loadDocumentsList:async()=>{},
 loadCapabilities:async()=>{},restorePlanning:async()=>{},
 api:async url=>{
  const id=url.split('/')[2];
  if(url.endsWith('/catalog')){if(id==='A')return new Promise(r=>releaseOld=r);return {items:[{id:'B-item',kind:'block'}],layouts:['Model'],warnings:[]}}
  if(url.endsWith('/sheets'))return {items:[]};
  if(url.endsWith('/selection'))return {ids:[]};
  return {filename:id,status:'ready'};
 }};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('async function load(){'),source.indexOf('let documentGraph=')),context);
(async()=>{
 const old=context.load();await new Promise(r=>setImmediate(r));
 assert(releaseOld,'The old catalog request is still in progress');
 context.doc='B';await context.load();
 releaseOld({items:[{id:'A-item',kind:'block'}],layouts:['Model'],warnings:[]});await old;
 assert.equal(context.items[0].id,'B-item');assert($('status').textContent.startsWith('B ·'));
 const initialization=source.slice(source.indexOf('doc=new URLSearchParams(location.search)'),source.indexOf('loadDocumentsList().then'));
 context.localStorage={getItem:()=> 'previous-file'};
 for(const query of ['?doc=explicit-file','?document=explicit-file']){
  context.location.search=query;vm.runInContext(initialization,context);
  assert.equal(context.doc,'explicit-file','The URL must take precedence over the previous file saved in localStorage');
 }
 console.log('Switching documents ignores late status/catalog responses: passed');
})().catch(e=>{console.error(e);process.exitCode=1});
