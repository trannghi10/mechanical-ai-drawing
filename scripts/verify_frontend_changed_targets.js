const fs=require('fs'),vm=require('vm'),assert=require('assert');
class Node{
  constructor(tag='div'){this.tagName=tag;this.children=[];this.style={};this.dataset={};this.textContent='';this.className=''}
  append(...items){this.children.push(...items)}
  removeAttribute(name){delete this[name]}
}
const source=fs.readFileSync('frontend/index.html','utf8');
const start=source.indexOf('function drawingDisplayName('),end=source.indexOf('function displayPlan(');
assert(start>=0&&end>start);
const context={document:{createElement:tag=>new Node(tag)},items:[{id:'43C372',kind:'sheet',name:'Tên sản phẩm :',texts:['8.1.07009.002','Bas sắt 2x25.6x444.5mm (Cắt laser)']}],previewUrl:target=>`/preview/${target.id}`,$:()=>({textContent:''}),show:()=>{},viewRevision:()=>Promise.resolve(),openComparison:()=>Promise.resolve()};
vm.createContext(context);vm.runInContext(source.slice(start,end),context);
const host=new Node();context.displayChangedTargetsCard([{id:'43C372',kind:'sheet',summary:'Sửa hình học',changes_count:12,reasons:['Đồng bộ BOM']}],host,null,true);
const section=host.children[0],rail=section.children[2],card=rail.children[0],body=card.children[0];
assert.equal(rail.className,'changed-targets-rail');assert.equal(card.className,'changed-target-card');
assert.equal(body.children[0].textContent,'Bas sắt 2x25.6x444.5mm (Cắt laser)');assert.equal(body.children[1].textContent,'Mã vật liệu: 8.1.07009.002');
assert.equal(card.children.some(child=>child.tagName==='img'),false);
assert.equal(section.children[0].children[0].textContent,'Mã vật liệu và chi tiết sẽ được thay đổi');
assert(!source.slice(start,end).includes('innerHTML'));
console.log('Changed material cards: horizontal rail, material code, source title and no preview image passed');
