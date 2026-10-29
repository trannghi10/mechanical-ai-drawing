const fs=require('fs'),vm=require('vm'),assert=require('assert');
class Element {constructor(){this.children=[];this.dataset={};this.textContent='';}append(...items){this.children.push(...items)}replaceChildren(...items){this.children=items}}
const nodes=new Map(),el=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id)};
const source=fs.readFileSync('frontend/release-review.js','utf8');
let releases=[],answer={ok:true,json:async()=>({passed_count:1,auto_release_allowed:true,checks:[{id:'coverage',status:'blocked',label:'<svg onload=attack()>',detail:'Missing links'}],edit_gate:{mode:'REVIEW',checks:[{status:'review',detail:'Need engineer confirmation'}]}})};
const ctx={URLSearchParams,document:{getElementById:el,createElement:()=>new Element()},
  location:{search:'?document='+'a'.repeat(32)+'&revision='+'b'.repeat(32)},fetch:async(url,options)=>{releases.push([url,options]);return answer}};
vm.createContext(ctx);vm.runInContext(source,ctx);
(async()=>{
  await new Promise(r=>setImmediate(r));assert.equal(el('checks').children.length,1);
  assert(el('checks').children[0].children[0].textContent.includes('<svg onload=attack()>'));
  assert(el('gate').children[0].children[0].textContent.includes('REVIEW'));
  assert(el('status').textContent.includes('Chưa bật tự phát hành'));
  assert(releases[0][1].cache==='no-store');assert(!releases[0][1].method);
  answer={ok:false,json:async()=>({detail:'Phiên đăng nhập hết hạn'})};await el('refresh').onclick();
  assert.equal(el('status').textContent,'Phiên đăng nhập hết hạn');assert.equal(el('refresh').disabled,false);
  const invalid={...ctx,location:{search:'?document=../secrets&revision='+'b'.repeat(32)},fetch:()=>{throw Error('Invalid request escaped')}};
  vm.runInNewContext(source,invalid);assert(el('status').textContent.includes('Chọn một bản sửa'));
  assert(!source.includes('innerHTML'));assert(!source.includes("method:'POST'"));
  console.log('Release review: source identity, read-only UI, escaping, missing certification and API error feedback passed');
})().catch(error=>{console.error(error);process.exitCode=1});
