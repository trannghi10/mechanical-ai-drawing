// Pure proposal formatting check; browser interactions are verified separately.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('frontend/index.html','utf8');
const source=html.split('<script>')[1].split('</script>')[0];
new vm.Script(source); // syntax check of the actual shipped page
const formatter=source.slice(source.indexOf('function planChangeRows('),source.indexOf('function displayPlan('));
const context={};vm.createContext(context);vm.runInContext(formatter,context);
const files=fs.readdirSync('storage/documents/baf461e9c2764a5ba9000a48772f846c/change-plans');
let proposal;
for(const file of files){const candidate=JSON.parse(fs.readFileSync('storage/documents/baf461e9c2764a5ba9000a48772f846c/change-plans/'+file,'utf8'));if(candidate.plan?.operations?.length===1480){proposal=candidate;break}}
assert(proposal,'Production linked-part proposal fixture is available');
const rows=context.planChangeRows(proposal.plan);
assert.equal(new Set(rows).size,rows.length);
assert(rows.length<proposal.plan.edits.filter(e=>e.purpose!=='geometry').length+2);
assert(rows.some(r=>r.includes('đồng bộ 3 vị trí')));
assert(rows.some(r=>r.includes('đồng bộ 4 vị trí')));
console.log(JSON.stringify({proposed_rows:rows.length,rows}));

const fitSource=source.slice(source.indexOf('function fittedSize('),source.indexOf('function setZoom('));
vm.runInContext(fitSource,context);
for(const [w,h,bw,bh] of [[2300,1620,1200,430],[1620,2300,1200,430],[2300,1620,380,600]]){
 const size=context.fittedSize(w,h,bw,bh);
 assert(size.width<=bw+1e-8&&size.height<=bh+1e-8);
 assert(Math.abs(size.width/size.height-w/h)<1e-8);
}
assert.equal(context.fittedSize(0,0,100,100),null);
const double=context.fittedSize(2300,1620,1200,430,2);
assert(Math.abs(double.height-860)<1e-8);
const sample={plan:{process_assessments:[{part_code:'A',stage_id:'cut_laser',status:'unresolved',reason:'Contact missing'}]},impact_graph:{process_groups:[{stage_id:'cut_laser',label:'Cắt laser',members:[{part_code:'A',part_number:'1',description:'Bas (Cắt laser)'}]},{stage_id:'cut_laser',label:'Cắt laser',members:[{part_code:'A',part_number:'1',description:'Bas (Cắt laser)'}]}]}};
const processRows=context.processReviewRows(sample);
assert.equal(processRows.length,1);assert(processRows[0].status.includes('Chưa đủ'));
assert.equal(context.needsProcessVision(sample),true);
assert.equal(context.needsProcessVision({...sample,execution_available:true}),false);
assert.equal(context.needsProcessVision({...sample,process_vision:{status:'reviewed'}}),false);
assert.equal(context.needsProcessVision({plan:{process_assessments:[]}}),false);
console.log('Fit portrait/landscape/mobile and deduplicated process review: passed');
const ordered=context.proposalMaterials({edits:[
 {part_number:'10',purpose:'bom',entity_ref:'T1',before:'Old',after:'New'},
 {part_number:'2',purpose:'bom',entity_ref:'T2',before:'Old two',after:'New two'},
 {part_number:'1',purpose:'geometry',entity_ref:'L1'},
 {part_number:'2',purpose:'annotation',entity_ref:'T3',before:'Old two',after:'New two'}
]});
assert.deepEqual(Array.from(ordered,p=>p.number),['1','2','10']);
assert.equal(ordered[1].changes.size,1);
vm.runInContext(source.slice(source.indexOf('function changedSpan('),source.indexOf('function specCell(')),context);
const diff=context.changedSpan('Sắt hộp 2x30x60','Sắt hộp 1.2x30x60');
assert.equal('Sắt hộp 2x30x60'.slice(diff.left,-diff.right),'2');
assert.equal('Sắt hộp 1.2x30x60'.slice(diff.left,-diff.right),'1.2');
console.log('BOM number ordering, duplicate descriptions and precise specification highlighting: passed');

const concise=context.compactProposalChange('La xương trái - Sắt tấm 1.5x131x540mm (Cắt laser nhám)','La xương trái - Sắt tấm 1x131x540mm (Cắt laser nhám)');
assert.equal(concise.before,'1.5 × 131 × 540mm');assert.equal(concise.after,'1 × 131 × 540mm');
assert.equal(context.compactProposalChange('Bas 2x20x100','Tấm 1x20x100').before,'Bas 2x20x100');
assert.equal(context.compactProposalChange('A 2x20 và B 3x40','A 1x20 và B 2x40').after,'A 1x20 và B 2x40');
assert.equal(context.compactProposalChange('Dày 1,5 mm','Dày 1 mm').before,'Dày 1,5 mm');
function el(tag=''){return {tag,children:[],rows:[],textContent:'',append(...children){this.children.push(...children)},replaceChildren(...children){this.children=children},createTHead(){const x=el('thead');this.append(x);return x},createTBody(){const x=el('tbody');this.append(x);return x},insertRow(){const x=el('tr');this.rows.push(x);this.append(x);return x},insertCell(){const x=el('td');this.append(x);return x}}}
const output=el('output');context.document={createElement:el,createTextNode:text=>({textContent:text,children:[]})};context.$=()=>output;
vm.runInContext(source.slice(source.indexOf('function specCell('),source.indexOf('async function loadRevisionMaterials(')),context);
context.displayProposalMaterials(proposal);
const walk=n=>[n,...n.children.flatMap(walk)],rendered=walk(output),table=rendered.find(n=>n.className==='material-table proposal-compact');
assert(table);assert.equal(table.children[0].rows[0].children.length,2);
assert.equal(table.children[1].rows.length,context.proposalMaterials(proposal).length);
assert(!walk(table).some(n=>n.textContent.includes('đối tượng CAD trong kế hoạch')));
const full=rendered.find(n=>n.className==='proposal-full');assert(full&&!full.open);
assert(walk(full).some(n=>n.textContent.includes('đối tượng CAD trong kế hoạch')));
assert(walk(full).map(n=>n.textContent).join('').includes('306 pcs'));
assert(!walk(table).some(n=>n.textContent==='Vật liệu và ghi chú đi kèm'));
console.log('Compact two-column proposal, conservative summaries and complete collapsed source details: passed');
const materialOutput=el('output');context.displayMaterialInputReview({material_input_review:[{part_code:'NEW-PART',stock_code:'RAW-SHEET',status:'verified_single_blank_envelope',blank_mm:[2,20,76],stock_mm:[2,1220,2500],reason:'Giữ nguyên tấm; một phôi vừa khổ nguồn.'}]},materialOutput);
const stockText=walk(materialOutput).map(n=>n.textContent).join(' ');
assert(stockText.includes('Nguyên liệu và phôi gia công')&&stockText.includes('NEW-PART ← RAW-SHEET')&&stockText.includes('2 × 20 × 76'));
assert(!materialOutput.children[0].open);
console.log('Source-classified stock and single-blank check remain readable and collapsed: passed');
