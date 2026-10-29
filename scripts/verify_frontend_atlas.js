// Whole-file directory: paging, exact source navigation and stale response isolation.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
class Node{
 constructor(tag='div'){this.tag=tag;this.children=[];this.value='';this.textContent='';this.disabled=false;this.hidden=false;this.events={};}
 append(...children){this.children.push(...children)}
 replaceChildren(...children){this.children=[...children]}
 add(child){this.children.push(child)}
 addEventListener(name,handler){this.events[name]=handler}
 createTHead(){const head=new Node('thead');this.append(head);return head}
 createTBody(){const body=new Node('tbody');this.append(body);return body}
 insertRow(){const row=new Node('tr');this.append(row);return row}
 insertCell(){const cell=new Node('td');this.append(cell);return cell}
}
const nodes=new Map(),el=id=>{if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id)},events={};
const walk=n=>[n,...n.children.filter(c=>c instanceof Node).flatMap(walk)];
let delayed=null,release=null,failReport=false,opens=[];
function report(did){return {source_hash:'hash-'+did,placed_record_count:100,layouts:[{name:'Model'}],frames:[],unused_definition_count:0,
 traversal_complete:true,metadata_only_types:{OLE2FRAME:1},partial_types:{},gap_count:0,gaps:[],parts:Array.from({length:23},(_,i)=>({part_code:did+'-'+i,
 descriptions:[i===22?'<img src=x onerror=alert(1)>':'Plate'],materials:[],bom_occurrences:[{part_number:'7'}],native_instances:[],detail_sheet_ids:['s'+i],frames:[{id:'s'+i,layout:'Model',kind:'sheet'}]}))};}
const context={document:{getElementById:el,createElement:tag=>new Node(tag)},window:{addEventListener:(name,fn)=>events[name]=fn},
 doc:'A',items:[],analyzing:false,creatingRevision:false,URLSearchParams,Option:function(text,value){this.textContent=text;this.value=value},
 setTimeout:fn=>fn(),show:async(frame,focus)=>opens.push({frame,focus}),console,
 api:async(url,options)=>{
  const did=url.split('/')[2];
  if(url.endsWith('/atlas'))return {id:'job-'+did,status:'ready'};
  if(url.endsWith('/report')){if(failReport)throw Error('Nguồn đã thay đổi');if(delayed===did)return new Promise(resolve=>release=()=>resolve(report(did)));return report(did);}
  if(url.includes('/entities?'))return {items:[{ref:'H/D',type:'DIMENSION',layout:'Model',role:'drawing',read_status:'read'}],next_offset:null,match_count:1};
  throw Error('Unexpected URL '+url);
 }};
vm.createContext(context);vm.runInContext(fs.readFileSync('frontend/document-atlas.js','utf8'),context);
(async()=>{
 await events['cad-document-ready']();assert(el('atlasStatus').textContent.includes('sẵn sàng'));
 assert.equal(walk(el('atlasParts')).filter(n=>n.tag==='tr').length,21);
 el('atlasSearch').value='A-22';el('atlasSearch').oninput();
 assert.equal(walk(el('atlasParts')).filter(n=>n.tag==='tr').length,2);
 assert(walk(el('atlasParts')).some(n=>n.textContent.includes('<img src=x')));
 const open=walk(el('atlasParts')).find(n=>n.tag==='button');
 await open.onclick();assert.equal(opens.length,1);assert.equal(opens[0].frame.id,'s22');assert(opens[0].focus);
 context.analyzing=true;await open.onclick();assert.equal(opens.length,1);context.analyzing=false;
 failReport=true;await open.onclick();assert.equal(opens.length,1);assert(el('atlasStatus').textContent.includes('thay đổi'));failReport=false;
 await el('atlasEntityRead').onclick();assert(el('atlasEntityCount').textContent.startsWith('1 thực thể'));assert(el('atlasNext').disabled);
 delayed='A';const pending=events['cad-document-ready']();await new Promise(r=>setImmediate(r));
 context.doc='B';events['cad-document-changed']();assert.equal(el('atlasParts').children.length,0);
 await events['cad-document-ready']();release();await pending;
 assert(walk(el('atlasParts')).some(n=>n.textContent.startsWith('B-0')));
 assert(!walk(el('atlasParts')).some(n=>n.textContent.startsWith('A-0')));
 assert(!fs.readFileSync('frontend/document-atlas.js','utf8').includes('.innerHTML'));
 console.log('Whole-file directory, all-part search, source-bound navigation, busy guard, CAD text escaping, paging and stale document isolation: passed');
})().catch(error=>{console.error(error);process.exitCode=1});
