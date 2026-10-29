// Dataset status must distinguish target, downloads, proposed labels and acceptance.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
class Node{
 constructor(tag='div'){this.tag=tag;this.children=[];this.textContent='';this.value='';this.disabled=false;this.hidden=false;this.events={}}
 append(...children){this.children.push(...children)}replaceChildren(...children){this.children=[...children]}
 addEventListener(name,handler){this.events[name]=handler}
 createTHead(){const n=new Node('thead');this.append(n);return n}createTBody(){const n=new Node('tbody');this.append(n);return n}
 insertRow(){const n=new Node('tr');this.append(n);return n}insertCell(){const n=new Node('td');this.append(n);return n}
}
const nodes=new Map(),el=id=>{if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id)};
const walk=n=>[n,...n.children.flatMap(c=>c instanceof Node?walk(c):[])];
let release,fail=false;
function row(title){return {title,source_id:'source',origin:'generated',group:'plates',group_review:'pending',rights:{license_id:'CC0',evaluation:true,training:true,redistribution:true},split:'unassigned',cad_formats:['STEP'],native_opened:false,label_count:2,relationship_count:0,edit_case_count:0,dossier_review:'pending'}}
const summary={accepted_dwg_dossiers:0,record_count:33,unique_dwg_files:20,label_count:378,relationship_count:0,engineer_approved_edit_cases:0,dwg_roundtrip_cases:0,training_ready:0,note:'Target only',integrity_checked:true,integrity_errors:{},split_errors:[],groups:[{name:'Plates',target:50,records:1,accepted:0}],sources:{public_sources:[]}};
const context={document:{getElementById:el,createElement:tag=>new Node(tag)},URLSearchParams,console,
 fetch:async url=>{
  if(fail)return {ok:false,json:async()=>({detail:'Hash không khớp'})};
  if(url==='/dataset/status')return {ok:true,json:async()=>summary};
  if(url.includes('query=slow'))return await new Promise(r=>release=()=>r({ok:true,json:async()=>({items:[row('old')],next_offset:null})}));
  return {ok:true,json:async()=>({items:[row(url.includes('query=new')?'new':'<img src=x onerror=alert(1)>')],next_offset:null})};
 }};
vm.createContext(context);vm.runInContext(fs.readFileSync('frontend/dataset.js','utf8'),context);
(async()=>{
 await new Promise(r=>setImmediate(r));
 assert(walk(el('datasetSummary')).some(n=>n.textContent.startsWith('0/500')));
 assert(walk(el('datasetSummary')).some(n=>n.textContent.startsWith('0 hồ sơ sẵn sàng')));
 assert(walk(el('datasetRecords')).some(n=>n.textContent.includes('<img src=x')));
 assert(!walk(el('datasetRecords')).some(n=>n.tag==='img'));
 el('datasetQuery').value='slow';const pending=el('searchDataset').onclick();await new Promise(r=>setImmediate(r));
 el('datasetQuery').value='new';el('datasetQuery').events.input();await el('searchDataset').onclick();release();await pending;
 assert(walk(el('datasetRecords')).some(n=>n.textContent.startsWith('new')));
 assert(!walk(el('datasetRecords')).some(n=>n.textContent.startsWith('old')));
 fail=true;await el('refreshDataset').onclick();assert.equal(el('datasetStatus').textContent,'Hash không khớp');assert(!el('refreshDataset').disabled);
 assert(!fs.readFileSync('frontend/dataset.js','utf8').includes('.innerHTML'));
 console.log('Dataset target vs accepted counts, pending labels, training gate, escaped source text, stale search isolation and integrity error feedback: passed');
})().catch(error=>{console.error(error);process.exitCode=1});
