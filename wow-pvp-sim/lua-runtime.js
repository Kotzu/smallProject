(()=>{
  const FENGARI_URL='https://cdn.jsdelivr.net/npm/fengari-web@0.1.4/dist/fengari-web.min.js';
  const sourceCache=new Map();
  let initPromise=null;

  function loadScript(src){
    return new Promise((resolve,reject)=>{
      const existing=[...document.scripts].find(s=>s.src===src);
      if(existing&&window.fengari){resolve();return;}
      const s=existing||document.createElement('script');
      if(!existing){s.src=src;s.async=true;document.head.appendChild(s);}
      s.addEventListener('load',()=>resolve(),{once:true});
      s.addEventListener('error',()=>reject(new Error('Nu pot încărca Fengari runtime')),{once:true});
    });
  }

  function init(){
    if(window.fengari?.load)return Promise.resolve(window.fengari);
    if(!initPromise)initPromise=loadScript(FENGARI_URL).then(()=>{
      if(!window.fengari?.load)throw new Error('Fengari s-a încărcat fără API-ul load()');
      return window.fengari;
    });
    return initPromise;
  }

  async function policySource(className){
    const key=String(className||'');
    if(sourceCache.has(key))return sourceCache.get(key);
    const path=`combat/${key}/ClassCombat.lua`;
    const r=await fetch(path+'?v='+Date.now(),{cache:'no-store'});
    if(!r.ok)throw new Error(`${path}: HTTP ${r.status}`);
    const src=await r.text();sourceCache.set(key,src);return src;
  }

  function luaString(s){
    return '"'+String(s??'').replace(/\\/g,'\\\\').replace(/"/g,'\\"').replace(/\r/g,'\\r').replace(/\n/g,'\\n')+'"';
  }
  function luaLiteral(v,seen=new Set()){
    if(v===null||v===undefined)return 'nil';
    if(typeof v==='boolean')return v?'true':'false';
    if(typeof v==='number')return Number.isFinite(v)?String(v):'0';
    if(typeof v==='string')return luaString(v);
    if(typeof v!=='object')return 'nil';
    if(seen.has(v))return '{}';seen.add(v);
    if(Array.isArray(v))return '{'+v.map(x=>luaLiteral(x,seen)).join(',')+'}';
    return '{'+Object.entries(v).filter(([,x])=>typeof x!=='function').map(([k,x])=>'['+luaString(k)+']='+luaLiteral(x,seen)).join(',')+'}';
  }

  function buildTalentNames(build){
    const out={};
    for(const t of build?.combatTalents||[]){
      const rank=Number(String(t.rank||'0').split('/')[0])||0;
      if(rank>0)out[t.name]=rank;
    }
    return out;
  }

  function sanitizeContext(ctx,build){
    return {
      self:ctx?.self||{},enemy:ctx?.enemy||{},range:Number(ctx?.range)||0,spec:ctx?.spec||build?.spec||'',
      buildId:ctx?.buildId||build?.id||'',behindTarget:ctx?.behindTarget===true,
      readyMap:ctx?.readyMap||{},talentNames:ctx?.talentNames||buildTalentNames(build),
      build:{id:build?.id||'',modifiers:build?.modifiers||{}}
    };
  }

  function chunkFor(source,ctx,build){
    const c=sanitizeContext(ctx,build);
    return `
local Policy=(function()\n${source}\nend)()
local ctx=${luaLiteral(c)}
function ctx:ready(name) return self.readyMap[name] == true end
function ctx:hasTalent(name) return (self.talentNames[name] or 0) > 0 end
function ctx:modifier(name) return self.build.modifiers[name] end
local d=Policy.choose(ctx) or {}
return tostring(d.action or '') .. '\31' .. tostring(d.reason or '') .. '\31' .. tostring(d.range or '')
`;
  }

  async function choose(className,ctx,build){
    await init();
    const source=await policySource(className);
    const chunk=chunkFor(source,ctx,build);
    const raw=window.fengari.load(chunk,`@${className}/ClassCombat.lua`)();
    const parts=String(raw??'').split('\x19');
    return {action:parts[0]||'',reason:parts[1]||'',range:parts[2]===''?null:Number(parts[2]),runtime:'LUA_FENGARI'};
  }

  async function selfTest(){
    const T=window.WOW_TALENTS;
    const hemo=T?.get?.('rogue_cb_hemo_21_3_27');
    const dagger=T?.get?.('rogue_imp_sprint_backstab_16_12_23');
    const mage=T?.get?.('mage_deep_frost_17_0_34');
    const baseReady={'Vanish':true,'Preparation':true,'Sprint':true,'Kick':true,'Kidney Shot':true,'Cold Blood':true,'Gouge':true};
    const a=await choose('Rogue',{spec:'Subtlety',buildId:hemo?.id,self:{stealthed:true,energy:100,comboPoints:0},enemy:{},range:5,readyMap:baseReady},hemo);
    const b=await choose('Rogue',{spec:'Subtlety',buildId:dagger?.id,self:{stealthed:true,energy:100,comboPoints:0},enemy:{},range:5,behindTarget:false,readyMap:baseReady},dagger);
    const c=await choose('Rogue',{spec:'Subtlety',buildId:dagger?.id,self:{stealthed:true,energy:100,comboPoints:0},enemy:{},range:5,behindTarget:true,readyMap:baseReady},dagger);
    const d=await choose('Mage',{spec:'Frost',buildId:mage?.id,self:{stunned:true,healthPct:100,manaShieldAbsorb:855,iceBarrierAbsorb:878},enemy:{},range:5,readyMap:{'Blink':true}},mage);
    const checks=[
      {name:'CB/Hemo opener',pass:a.action==='Cheap Shot',actual:a.action},
      {name:'Dagger seeks rear arc',pass:b.action==='MOVE_BEHIND',actual:b.action},
      {name:'Dagger Ambush from behind',pass:c.action==='Ambush',actual:c.action},
      {name:'Mage Blink policy',pass:d.action==='Blink',actual:d.action}
    ];
    return {pass:checks.every(x=>x.pass),checks,version:'0.22-lua-runtime'};
  }

  window.WOW_LUA_RUNTIME={version:'0.22',init,choose,selfTest,policySource,status:'LOADING'};
  init().then(async()=>{
    window.WOW_LUA_RUNTIME.status='READY';
    try{window.WOW_LUA_RUNTIME.lastSelfTest=await selfTest();}catch(err){window.WOW_LUA_RUNTIME.lastError=String(err?.stack||err);window.WOW_LUA_RUNTIME.status='ERROR';}
    document.dispatchEvent(new CustomEvent('wow-lua-runtime-ready',{detail:window.WOW_LUA_RUNTIME}));
  }).catch(err=>{window.WOW_LUA_RUNTIME.status='ERROR';window.WOW_LUA_RUNTIME.lastError=String(err?.stack||err);document.dispatchEvent(new CustomEvent('wow-lua-runtime-ready',{detail:window.WOW_LUA_RUNTIME}));});
})();