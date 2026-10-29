const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const nodes=new Map();
class Element{
 constructor(tag='div'){this.tagName=tag;this.children=[];this.value='';this.textContent='';this.disabled=false;this.style={};this.dataset={};}
 set id(value){this._id=value;nodes.set(value,this)}get id(){return this._id}
 append(...children){this.children.push(...children)}insertBefore(child){this.children.push(child)}replaceChildren(...children){this.children=[...children]}
 setAttribute(name,value){this[name]=value}addEventListener(name,fn){this['on'+name]=fn}
}
for(const id of ['apsPanel','apsJobs','nativeProvider']){const node=new Element();node.id=id}
nodes.get('nativeProvider').value='autocad';
const calls=[];let refreshed=0;
const pair={polyline_handle:'2F',dimension_handle:'30',layout:'Model',width_mm:100,height_mm:50};
const found={inspection_id:'i'.repeat(32),source_hash:'a'.repeat(64),items:[pair]};
const context={doc:'d'.repeat(32),document:{getElementById:id=>nodes.get(id),createElement:tag=>new Element(tag)},encodeURIComponent,Number,Math,Promise,setTimeout:fn=>fn(),console};
context.window=context;context.refreshApsJobs=async()=>{refreshed++};
context.api=async(url,options)=>{
 calls.push({url,options,body:options?.body?JSON.parse(options.body):undefined});
 if(url.endsWith('/rectangle-candidates'))return found;
 if(url.endsWith('/rectangle-stretch'))return {id:'e'.repeat(32),status:'queued'};
 if(url.endsWith('/jobs/'+'e'.repeat(32)))return {id:'e'.repeat(32),status:'ready'};
 if(url.endsWith('/jobs'))return {items:[{id:found.inspection_id,mode:'inspect',status:'ready'}]};
 throw Error('Unexpected API '+url);
};
function descendants(node,tag){return node.children.flatMap(child=>[...(child.tagName===tag?[child]:[]),...descendants(child,tag)])}
vm.createContext(context);vm.runInContext(fs.readFileSync('frontend/rectangle-ui.js','utf8'),context);
(async()=>{
 const section=nodes.get('rectangleEditor'),find=nodes.get('rectangleFind');
 assert.equal(calls.length,0,'No upload or edit on startup');await find.onclick();
 const input=nodes.get('rectangleWidth'),apply=nodes.get('rectangleApply');
 assert.equal(input.value,'100');assert.equal(calls.filter(c=>c.options?.method==='POST').length,0);
 for(const value of ['0','100','bad']){input.value=value;await apply.onclick()}
 assert.equal(calls.filter(c=>c.url.endsWith('/rectangle-stretch')).length,0,'Reject invalid or unchanged width');
 input.value='120';await apply.onclick();
 const request=calls.find(c=>c.url.endsWith('/rectangle-stretch'));
 assert.deepEqual(request.body,{inspection_id:found.inspection_id,source_hash:found.source_hash,polyline_handle:'2F',dimension_handle:'30',target_width_mm:120});
 assert.ok(request.url.includes('/autocad/'));assert.equal(refreshed,2);
 const images=descendants(section,'img');assert.equal(images.length,2);assert.ok(images[1].src.includes('/'+'e'.repeat(32)+'/rectangle-preview'));
 assert.ok(descendants(section,'p').some(p=>p.textContent.includes('100 → 120')));
 const originalApi=context.api;let release;
 context.api=(url,options)=>url.endsWith('/rectangle-stretch')?new Promise(resolve=>release=resolve):originalApi(url,options);
 input.value='130';const pending=apply.onclick();
 context.doc='f'.repeat(32);context.syncRectangleEditor();
 release({id:'e'.repeat(32),status:'ready'});await pending;
 assert.equal(descendants(section,'img').length,0,'Late edit response must not change another document');
 assert.equal(nodes.get('rectangleFind').disabled,false);
 context.api=originalApi;context.doc='d'.repeat(32);nodes.get('nativeProvider').value='aps';context.syncRectangleEditor();
 await find.onclick();nodes.get('rectangleWidth').value='125';await nodes.get('rectangleApply').onclick();
 assert.ok(calls.some(c=>c.url.includes('/aps/rectangle-stretch')),'APS choice uses explicit cloud endpoint');
 assert.ok(nodes.get('rectangleApply').textContent.includes('gửi Autodesk'));
 console.log('Rectangle UI: discovery, explicit target, local/cloud routing, pending job, comparison and stale document checks passed.');
})().catch(error=>{console.error(error);process.exitCode=1});
