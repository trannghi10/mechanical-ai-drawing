const fs=require('fs'),vm=require('vm'),assert=require('assert');
const src=fs.readFileSync('frontend/index.html','utf8').split('<script>')[1].split('</script>')[0];
function element(tag='div'){return {tag,children:[],attributes:{},style:{},hidden:false,disabled:false,isConnected:true,value:'',textContent:'',checked:false,
 append(...nodes){for(const n of nodes){this.children.push(n);n.parentElement=this}},add(option){this.append(option);if(this.children.length===1)this.value=option.value},replaceChildren(...nodes){this.children=[];this.value='';this.append(...nodes)},setAttribute(k,v){this.attributes[k]=v}}}
const view=element(),walk=n=>[n,...n.children.flatMap(walk)],find=label=>walk(view).find(n=>n.attributes['aria-label']===label);
const Option=function(text,value){return {...element('option'),textContent:text,value}};
const hash='a'.repeat(64),model={source_hash:hash,representations:[{part_id:'P',ownership_proof:'native_part_identity',sheet_ids:['source'],parameters:[{dimension_ref:'D1',measurement:100}]}]};
const candidate={id:'1'.repeat(24),part_code:'P',source_hash:hash,candidates:[{id:'2'.repeat(24),before_spec_mm:[2,80,100],refs:['a'],sheet_ids:['target'],vertices:[{label:'A',point:[0,0,0]}]}]};
let links=[],saved=[],reads=[],release;const context={doc:'doc',workItem:{id:'source'},activeItem:null,items:[{id:'source',kind:'sheet'},{id:'target',kind:'sheet'}],analyzing:false,creatingRevision:false,Option,
 document:{createElement:element,createTextNode:text=>({...element('text'),textContent:text})},$:()=>view,showSource(){},
 api:async(url,options)=>{if(url.endsWith('/cuboid-candidates')){reads.push(JSON.parse(options.body));return candidate}if(options?.method==='POST'){const b=JSON.parse(options.body);saved.push(b);links=[{part_code:'P',anchor:b.anchor,body_id:b.body_id}];return links[0]}if(options?.method==='DELETE'){links=[];return {removed:true}}return {source_hash:hash,links}}};
vm.createContext(context);vm.runInContext(src.slice(src.indexOf('function renderCuboidLinkEditor('),src.indexOf('let rowStructureLoad=')),context);
(async()=>{
 context.renderCuboidLinkEditor(model);await new Promise(r=>setImmediate(r));find('DIM nguồn cho hình hộp').value='D1';find('Khung có hình hộp cần gắn').value='target';
 const read=walk(view).find(n=>n.textContent==='Đọc các hình hộp có thể gắn');await read.onclick();
 assert.deepEqual(reads[0].ids,['source','target']);assert.equal(reads[0].source_hash,hash);assert.equal(reads[0].dimension_ref,'D1');
 let save=walk(view).find(n=>n.textContent==='Lưu gắn hình hộp');await save.onclick();assert.equal(saved.length,0);
 let check=walk(view).find(n=>n.type==='checkbox');check.checked=true;const anchor=find('Mốc giữ hình hộp');anchor.value='A';anchor.onchange();assert(!check.checked);
 check.checked=true;await save.onclick();assert.equal(saved.length,1);assert(saved[0].confirmed);assert.equal(saved[0].anchor,'vertex');assert.equal(saved[0].vertex,'A');assert.equal(saved[0].body_id,candidate.candidates[0].id);
 const remove=walk(view).find(n=>n.textContent==='Xóa gắn hình hộp');await remove.onclick();assert.equal(links.length,0);
 context.api=()=>new Promise(r=>release=r);const pending=read.onclick();await new Promise(r=>setImmediate(r));context.doc='other';release(candidate);await pending;
 assert(!walk(view).some(n=>n.textContent==='Lưu gắn hình hộp'));assert(!read.disabled);
 console.log('Cuboid source DIM, explicit identity/datum confirmation, vertex change reset, deletion and stale reply protection: passed');
})().catch(e=>{console.error(e);process.exitCode=1});
