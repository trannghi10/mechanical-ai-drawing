const fs=require('fs'),vm=require('vm'),assert=require('assert');
class Node{constructor(){this.children=[];this.textContent='';}append(...items){this.children.push(...items)}}
const host=new Node(),context={document:{createElement:()=>new Node()},$:()=>host};
const source=fs.readFileSync('frontend/index.html','utf8');
vm.createContext(context);vm.runInContext(source.slice(source.indexOf('function renderLooseRelationships('),source.indexOf('function resetDesignModel(')),context);
context.renderLooseRelationships({});assert.equal(host.children.length,0);
context.renderLooseRelationships({loose_planar_relationships:{bodies:[{},{}],contacts:[{source_part:'<svg onload=attack()>',target_part:'NEW-B',source_gap_mm:0}]}});
const section=host.children[0];assert(section.children[1].textContent.includes('2 chi tiết'));assert(section.children[1].textContent.includes('1 mặt'));
const row=section.children[2].children[1];assert.equal(row.children[0].textContent,'<svg onload=attack()>');assert(row.children[2].textContent.includes('0 mm'));
context.renderLooseRelationships({loose_planar_relationships:{bodies:[{},{}],contacts:[{kind:'planar_measured_clearance',source_part:'NEW-A',target_part:'NEW-B',source_gap_mm:12.5,dimension_refs:['A7<cad>']}]}});
const gap=host.children[1];assert(gap.children[1].textContent.includes('1 khe hở'));assert(gap.children[2].children[1].children[2].textContent.includes('12.5 mm · DIM #A7<cad>'));
console.log('Source mechanical relationships: body/contact counts and safe CAD identity rendering passed');
