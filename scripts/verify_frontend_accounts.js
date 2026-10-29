// Verify the shipped account flow: safe redirects, role views and errors.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
class Element {
  constructor(){this.children=[];this.value='';this.textContent='';this.hidden=false;this.disabled=false;}
  append(...children){this.children.push(...children)}
  replaceChildren(...children){this.children=children}
  setAttribute(){}
  querySelectorAll(){return this.children}
  reset(){this.resetCalled=true}
}
const nodes=new Map(),el=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id)};
let status={setup_needed:true,user:null},calls=[],nextResponse=null;
const context={document:{getElementById:el,createElement:()=>new Element()},URL,URLSearchParams,Date,
  location:{origin:'http://127.0.0.1:8766',search:'',assign:path=>context.redirect=path},
  fetch:async(path,options)=>{calls.push([path,options]);if(nextResponse){const value=nextResponse;nextResponse=null;return value}
    return {ok:true,json:async()=>path==='/auth/status'?status:{items:[]}};
  }};
const source=fs.readFileSync('frontend/accounts.js','utf8');
vm.createContext(context);vm.runInContext(source,context);
(async()=>{
  await context.load();assert.equal(el('entryTitle').textContent,'Thiết lập quản trị viên');assert.equal(el('displayField').hidden,false);
  status={setup_needed:false,user:null};await context.load();assert.equal(el('entryTitle').textContent,'Đăng nhập');assert.equal(el('displayField').hidden,true);
  for(const value of ['https://foreign.example/','//foreign.example/','/\\foreign.example/','/\t/foreign.example/','javascript:alert(1)']){
    context.location.search='?next='+encodeURIComponent(value);assert.equal(context.nextPage(),'/');
  }
  context.location.search='?next='+encodeURIComponent('/relationship-review?document=abc#scope');
  assert.equal(context.nextPage(),'/relationship-review?document=abc#scope');
  status={setup_needed:false,user:{username:'viewer',display_name:'<img src=x onerror=attack()>',role:'viewer'}};
  await context.load();assert.equal(el('admin').hidden,true);assert.equal(el('entry').hidden,true);
  assert.equal(el('profileTitle').textContent,status.user.display_name);
  calls=[];status.user.role='admin';await context.load();assert.equal(el('admin').hidden,false);
  assert(calls.some(c=>c[0]==='/auth/users')&&calls.some(c=>c[0]==='/auth/audit'));
  nextResponse={ok:false,json:async()=>({detail:'Phiên đăng nhập đã hết hạn'})};
  const form=new Element(),button=new Element();form.append(button);
  await context.submit(form,async()=>{assert(button.disabled);await context.api('/auth/users')});
  assert(!button.disabled);assert.equal(el('message').textContent,'Phiên đăng nhập đã hết hạn');
  assert(calls.every(c=>c[1].cache==='no-store'));assert(!source.includes('innerHTML'));
  console.log('Accounts: setup/login, roles, escaping, safe redirects, cache and busy/error recovery passed');
})().catch(error=>{console.error(error);process.exitCode=1});
