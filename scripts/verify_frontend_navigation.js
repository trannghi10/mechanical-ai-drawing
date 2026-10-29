// Exercise the shipped navigation functions with controlled async responses.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('frontend/index.html','utf8').split('<script>')[1].split('</script>')[0];
const nodes=new Map();let scrolls=0;
function node(id){if(!nodes.has(id))nodes.set(id,{hidden:false,dataset:{},textContent:'',scrollIntoView(){scrolls++}});return nodes.get(id)}
let release;
const context={$:node,doc:'document',items:[{id:'root',kind:'sheet'}],workItem:{id:'root'},activeItem:null,
 analyzing:false,creatingRevision:false,generation:0,setZoom(){},focusItem(){throw Error('Review navigation must retain the editing scope')},
 URL:{createObjectURL:x=>'blob:'+x,revokeObjectURL(){}},fetch:async url=>({ok:true,blob:async()=>url.includes('slow')?await new Promise(r=>release=r):url}),console};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('function previewUrl('),source.indexOf('function focusItem(')),context);
vm.runInContext(source.slice(source.indexOf('function revealViewer('),source.indexOf("$('upload').onsubmit")),context);
vm.runInContext(source.slice(source.indexOf('function revisionPreviewUrl('),source.indexOf('let comparisonState=')),context);
(async()=>{
 await context.showSource('linked-detail-outside-catalog');
 assert(node('title').textContent.includes('linked-detail-outside-catalog'));
 assert(node('preview').src.includes('/sheets/linked-detail-outside-catalog/preview'));
 assert.equal(context.workItem.id,'root');assert.equal(node('viewerBack').hidden,false);assert(scrolls>0);
 await node('viewerBack').onclick();assert.equal(node('viewerBack').hidden,true);
 const pending=context.showSource('slow');await new Promise(r=>setImmediate(r));
 await context.showSource('newer');release('stale');await pending;
 assert(node('title').textContent.includes('newer'));assert(!node('preview').src.includes('stale'));
 await context.viewRevision({id:'revision',targets:[{id:'child',kind:'sheet'}]},{id:'child',kind:'sheet'});
 assert.equal(context.workItem.id,'root');assert(node('viewerContext').textContent.includes('CAD đã sửa'));
 assert(node('preview').src.includes('/revisions/revision/sheets/child/preview'));
 assert.equal(node('viewerBack').hidden,false);
 context.fetch=async()=>({ok:false,json:async()=>({detail:'Preview unavailable'})});
 await context.showSource('missing');assert.equal(node('previewStatus').textContent,'Preview unavailable');
 assert(node('preview').hidden);console.log('CAD review navigation, scroll, scope retention, stale response and error feedback: passed');
})().catch(e=>{console.error(e);process.exitCode=1});
