const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Element{constructor(){this.value='';this.hidden=true;this.children=[];this.textContent='';}addEventListener(n,f){this['on'+n]=f}replaceChildren(){this.children=[]}append(c){this.children.push(c)}}
const nodes=new Map(['document','inspection','polyline','source-hash','proposal-form','submit','message','result','rows','preview','preview-caption','scope','state','reasons','json-link','revision-controls','revision-state','revision-download','apply-repair','undo-repair','redo-repair','native-review','propose-native'].map(id=>[id,new Element()]));
const calls=[];let failure=false,pending=false;
const doc='a'.repeat(32),proposal='c'.repeat(32);
const result={id:proposal,inspection_id:'b'.repeat(32),source_sha256:'e'.repeat(64),edit_authorization:false,release_gate:{allowed:false,reasons:['Cần đối chiếu']},scope_sha256:'d'.repeat(64),plan:{polyline_handle:'3DFA1C',repairs:[{dimension_handle:'3DFA25',a_vertex:2,b_vertex:3}]}};
let cursor=-1,version=0;
const context={URLSearchParams,setTimeout:(fn,ms)=>ms===3000?1:fn(),clearTimeout(){},location:{search:''},history:{replaceState(){}},document:{getElementById:id=>nodes.get(id),createElement:()=>new Element()},fetch:async(url,options)=>{calls.push({url,options});let data=result;
 if(url.endsWith('/undo')){cursor=-1;version++}if(url.endsWith('/redo')){cursor=0;version++}
 if(url.includes('/relationship-history'))data={cursor,version,entries:['f'.repeat(32)],active_revision_id:cursor<0?null:'f'.repeat(32),pending_revision:pending?{id:'9'.repeat(32),status:'running'}:null};
 if(url.endsWith('/apply')){cursor=0;version++;data={id:'f'.repeat(32),status:'ready'}}
 if(url.includes('/relationship-revisions/'))data={status:'ready',native_endpoint_review:{endpoints:[{dimension_handle:'3DFA24',field:'defpoint2',source_bound:false,candidate_vertex_indices:[1]},{dimension_handle:'3DFA29',field:'defpoint2',source_bound:false,candidate_vertex_indices:[0]}]}};
 return {ok:!failure,json:async()=>failure?{detail:'Nguồn đã đổi'}:data}}};
vm.createContext(context);vm.runInContext(fs.readFileSync('frontend/relationship-review.js','utf8'),context);
(async()=>{
 assert.equal(calls.length,0);
 nodes.get('document').value=doc;nodes.get('inspection').value='b'.repeat(32);nodes.get('polyline').value='3DFA1C';nodes.get('source-hash').value='e'.repeat(64);
 const submit=()=>nodes.get('proposal-form').onsubmit({preventDefault(){}});
 await submit();await new Promise(setImmediate);assert.ok(calls[0].url.endsWith('/relationship-proposals'));
 assert.equal(nodes.get('result').hidden,false);assert.equal(nodes.get('rows').children.length,1);
 assert.equal(nodes.get('inspection').value,result.inspection_id);assert.equal(nodes.get('polyline').value,'3DFA1C');
 assert.equal(nodes.get('rows').children[0].children[2].textContent,'Đỉnh 3');
 assert.ok(nodes.get('preview').src.endsWith(proposal+'/preview'));assert.equal(nodes.get('submit').disabled,false);
 await nodes.get('apply-repair').onclick();assert.equal(cursor,0);assert.equal(nodes.get('revision-download').hidden,false);
 await nodes.get('undo-repair').onclick();assert.equal(cursor,-1);assert.equal(nodes.get('revision-download').hidden,true);
 await nodes.get('redo-repair').onclick();assert.equal(cursor,0);
 assert.equal(nodes.get('propose-native').hidden,false);
 await nodes.get('propose-native').onclick();await new Promise(setImmediate);
 const nativeCall=calls.filter(c=>c.options?.body && JSON.parse(c.options.body).adapter==='native_pointrefs').at(-1);
 assert.ok(nativeCall);assert.equal(JSON.parse(nativeCall.options.body).base_revision_id,'f'.repeat(32));
 pending=true;await submit();await new Promise(setImmediate);
 assert.equal(nodes.get('apply-repair').disabled,true);assert.equal(nodes.get('undo-repair').disabled,true);assert.equal(nodes.get('redo-repair').disabled,true);
 assert.equal(nodes.get('propose-native').hidden,true);assert.ok(nodes.get('revision-state').textContent.includes('Đang kiểm'));
 pending=false;await submit();await new Promise(setImmediate);assert.equal(nodes.get('apply-repair').disabled,false);
 result.adapter='native_pointrefs';result.base={revision_id:'0'.repeat(32)};
 await submit();await new Promise(setImmediate);assert.equal(nodes.get('apply-repair').disabled,true);
 await nodes.get('apply-repair').onclick();assert.equal(nodes.get('apply-repair').disabled,true);
 delete result.adapter;delete result.base;
 failure=true;await submit();assert.equal(nodes.get('result').hidden,true);assert.equal(nodes.get('message').textContent,'Nguồn đã đổi');
 assert.ok(calls.every(c=>!c.url.includes('native-edits')));
 assert.equal(nodes.get('revision-controls').hidden,true);
 console.log('Relationship review frontend proposal/apply/undo/redo/error logic passed.');
})().catch(e=>{console.error(e);process.exitCode=1});
