// Source-bound table regressions; actual browser rendering is also inspected.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('frontend/index.html','utf8');
const source=html.split('<script>')[1].split('</script>')[0];
new vm.Script(source);
assert(html.includes('id="cadTechnicalDetails"')&&html.includes('id="proposalMaterialsMount"'));
assert(source.includes('function clearProposalMaterials()')&&source.includes('mount.append(section)'));
const context={};vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('function friendlyQuestion('),source.indexOf('function displayPlan(')),context);
const incomplete={execution_available:false,root_bom_refs:['BOM'],plan:{questions:['Công đoạn chưa kiểm tra đủ ảnh hưởng lắp ghép cho mã chi tiết: P','Công đoạn chưa kiểm tra đủ ảnh hưởng lắp ghép cho mã chi tiết: P']},impact_graph:{nodes:[{code:'P',bom_occurrences:[{table_ref:'BOM',part_number:'6'}]}]},preview_reviews:{packaging_review:[{status:'unresolved_packaging',product_code:'PRODUCT',reason:'Chưa gắn lớp đệm trên'}]}};
const blockers=context.planBlockers(incomplete);assert.equal(blockers.length,2);assert(blockers[0].includes('chi tiết 6 (P)'));assert(blockers[1].includes('Chưa gắn lớp đệm trên'));
assert.equal(context.planBlockers({...incomplete,execution_available:true}).length,0);
vm.runInContext(source.slice(source.indexOf('function cleanProposalText('),source.indexOf('function displayProposalMaterials(')),context);
const readPlan=JSON.parse(fs.readFileSync('storage/documents/34ee84f35e1a44fb81c56044397a0fff/change-plans/65f1111cc5344c5c9ddd2d09eee1c0d1.json','utf8'));
delete readPlan.checked_preview_plan; // Public API deliberately keeps it server-side.
const snapshot=JSON.stringify(readPlan),rows=context.proposalMaterials(readPlan),root=rows.filter(r=>r.selectedScope);
assert.deepEqual(Array.from(root,r=>Number(r.number)),[4,5,8,9,10,11,12,13,14,15,16,17,18,21]);
const curved=root.find(r=>r.number==='16');assert.equal(curved.code,'8.1.05417.258');
assert(Array.from(curved.changes.values()).some(c=>c.before.includes('1.5x382x724')&&c.after.includes('1x382x697')));
for(const row of rows)for(const note of row.notes.values())assert(!note.before.includes('"defpoint"')&&!note.after.includes('"defpoint"'));
assert.equal(new Set(rows.map(r=>r.code)).size,rows.length);assert.equal(JSON.stringify(readPlan),snapshot);
const sample={root_target_ids:['ROOT'],root_bom_refs:['R'],plan:{edits:[
 {part_number:'A',purpose:'bom',entity_ref:'R/cell',before:'Plate 2x20x100',after:'Plate 1x20x100'},
 {part_number:'A',purpose:'annotation',entity_ref:'D/note',before:'Plate 2x20x100',after:'Plate 1x20x100'},
 {part_number:'A',purpose:'bom',entity_ref:'OTHER/cell',before:'Plate 2x20x100',after:'Plate 1x20x100'},
 {part_number:'A',purpose:'annotation',entity_ref:'DIM',before:JSON.stringify({defpoint:[0,0],text:'2'}),after:JSON.stringify({defpoint:[0,0],text:'1'})},
 {part_number:'B',purpose:'geometry',entity_ref:'LINE',before:'',after:''}
]},impact_graph:{nodes:[{code:'A',bom_occurrences:[{table_ref:'R',part_number:'10',description:'Plate 2x20x100',sheet_ids:['ROOT'],description_cell:{mirror_ref:'R/cell'}}]},
{code:'B',bom_occurrences:[{table_ref:'OTHER',part_number:'10',description:'Bas 2x20x100',sheet_ids:['ELSEWHERE'],description_cell:{mirror_ref:'OTHER/other'}}]}]}};
const testRows=context.proposalMaterials(sample);assert.equal(testRows.length,2);assert.equal(testRows[0].code,'A');assert.equal(testRows[0].changes.size,1);assert.equal(testRows[0].geometry.size,1);assert.equal(testRows[1].code,'B');assert.equal(testRows[1].selectedScope,false);
console.log('Source STT/code binding, duplicate mirrors, JSON DIM snapshots, partial plan and immutable proposal: passed');

const element=()=>({value:'',children:[],replaceChildren(...items){this.children=items;this.value=items[0]?.value||''},add(item){this.children.push(item)}});
const elements={planHistory:element(),changeStatus:element()},pending=[];
context.doc='DOC';context.$=id=>elements[id];context.Option=function(text,value){return {text,value}};
context.api=()=>new Promise(resolve=>pending.push(resolve));
vm.runInContext(source.slice(source.indexOf('let historyGeneration='),source.indexOf('let revisionItems=')),context);
(async()=>{
 const one=context.refreshHistory('FIRST'),two=context.refreshHistory('SECOND');pending[1]({items:[{id:'SECOND',request:'current'}]});await two;
 pending[0]({items:[{id:'FIRST',request:'old'}]});await one;assert.equal(elements.planHistory.value,'SECOND');
 const refreshing=context.refreshHistory();pending[2]({items:[{id:'SECOND',request:'current'}]});await refreshing;assert.equal(elements.planHistory.value,'SECOND');
 const stale=context.refreshHistory();context.doc='ANOTHER';pending[3]({items:[{id:'FIRST',request:'wrong document'}]});await stale;assert.equal(elements.planHistory.value,'SECOND');
 console.log('Selected history preservation, out-of-order requests and stale document protection: passed');
})().catch(e=>{console.error(e);process.exitCode=1});
