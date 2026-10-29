const fs=require('fs'),vm=require('vm'),assert=require('assert');
const src=fs.readFileSync('frontend/index.html','utf8').split('<script>')[1].split('</script>')[0];
function element(tag='div'){return {tag,children:[],attributes:{},style:{},hidden:false,disabled:false,isConnected:true,value:'',textContent:'',
 append(...nodes){for(const n of nodes){this.children.push(n);n.parentElement=this}},add(option){this.append(option);if(this.children.length===1)this.value=option.value},replaceChildren(...nodes){this.children=[];this.value='';this.append(...nodes)},
 setAttribute(k,v){this.attributes[k]=v},remove(){this.isConnected=false;if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(n=>n!==this)}}}
const view=element(),walk=n=>[n,...n.children.flatMap(walk)],find=label=>walk(view).find(n=>n.attributes['aria-label']===label);
const Option=function(text,value){const n=element('option');n.textContent=text;n.value=value;return n};
let links=[],posts=[],release;
const model={source_hash:'a'.repeat(64),scope_ids:['root'],parts:['A','B','C'].map(id=>({id,identity_kind:'bom_code'})),representations:['A','B','C'].map((id,i)=>({part_id:id,ownership_proof:i?'native_part_identity':'local_bom_leader_profile',sheet_ids:[i?'other':'root'],parameters:[{dimension_ref:'D'+(i+1),measurement:[2,25.6,30][i],anchor_points:[[0,0,0],[[2,25.6,30][i],0,0]]}]}))};
const context={doc:'document',workItem:{id:'root'},activeItem:null,items:[{id:'root',kind:'sheet'},{id:'other',kind:'sheet'}],analyzing:false,creatingRevision:false,Option,
 document:{createElement:element,createTextNode:text=>({...element('text'),textContent:text})},$:()=>view,showSource(){},
 api:async(url,options)=>{if(options?.method==='POST'){const body=JSON.parse(options.body);posts.push(body);links=[{id:'link',driver_code:'A',receiver_code:'B',rule:body.rule}];return links[0]}if(options?.method==='DELETE'){links=[];return {removed:'link'}}return {source_hash:model.source_hash,links}}};
vm.createContext(context);vm.runInContext(src.slice(src.indexOf('function renderParameterLinkEditor('),src.indexOf('let designModelLoad=')),context);
(async()=>{
 context.renderParameterLinkEditor(model);await new Promise(r=>setImmediate(r));
 assert(find('DIM chi tiết thứ nhất').children.some(n=>n.value==='D1'));
 let section=view.children[0],save=section.children.find(n=>n.textContent==='Lưu liên kết để tự đồng bộ');await save.onclick();assert.equal(posts.length,0);
 find('DIM chi tiết thứ nhất').value='D1';find('DIM chi tiết liên quan').value='D2';find('DIM ngoài giữ nguyên').value='D3';find('Quan hệ').value='wall_clearance';find('Quan hệ').onchange();assert(!find('DIM ngoài giữ nguyên').parentElement.hidden);
 const check=walk(section).find(n=>n.type==='checkbox');check.checked=true;await save.onclick();
 assert.equal(posts.length,1);assert(posts[0].confirmed&&posts[0].source_hash===model.source_hash);assert.equal(posts[0].rule.receiver_ref,'D2');assert.equal(posts[0].rule.outside_ref,'D3');assert.equal(posts[0].rule.driver_anchor,'first');assert(!check.checked);
 const remove=walk(section).find(n=>n.textContent==='Xóa liên kết');await remove.onclick();assert.equal(links.length,0);
 const extra=find('Khung liên quan để đọc thêm');extra.value='other';const read=section.children.find(n=>n.textContent==='Đọc thêm khung');context.api=()=>new Promise(r=>release=r);const pending=read.onclick();await new Promise(r=>setImmediate(r));context.doc='another';release(model);await pending;
 assert.equal(view.children.length,1);assert.equal(view.children[0],section);assert(!read.disabled);
 console.log('Parameter link confirmation, exact source hash/DIM/anchors, deletion and stale scope protection: passed');
})().catch(e=>{console.error(e);process.exitCode=1});
