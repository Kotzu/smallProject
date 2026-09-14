(()=>{
  const FENGARI_URLS=['/vendor/fengari-web.js','https://cdn.jsdelivr.net/npm/fengari-web@0.1.4/dist/fengari-web.js','https://unpkg.com/fengari-web@0.1.4/dist/fengari-web.js'];
  const sourceCache=new Map();
  let initPromise=null;

  function waitForFengari(timeoutMs=12000){
    return new Promise((resolve,reject)=>{const start=Date.now();const tick=()=>{if(window.fengari?.load){resolve(window.fengari);return;}if(Date.now()-start>=timeoutMs){reject(new Error('Fengari API timeout'));return;}setTimeout(tick,50);};tick();});
  }
  function loadScript(src){
    return new Promise((resolve,reject)=>{
      if(window.fengari?.load){resolve(window.fengari);return;}
      let s=[...document.scripts].find(x=>x.src===new URL(src,location.href).href);
      const cleanup=()=>{s?.removeEventListener('load',onload);s?.removeEventListener('error',onerror);};
      const onload=()=>{cleanup();waitForFengari(3000).then(resolve,reject);};
      const onerror=()=>{cleanup();reject(new Error('Nu pot încărca '+src));};
      if(!s){s=document.createElement('script');s.src=src;s.async=true;s.addEventListener('load',onload,{once:true});s.addEventListener('error',onerror,{once:true});document.head.appendChild(s);}
      else{s.addEventListener('load',onload,{once:true});s.addEventListener('error',onerror,{once:true});waitForFengari(1500).then(resolve,()=>{});}
    });
  }
  async function init(){if(window.fengari?.load)return window.fengari;if(!initPromise)initPromise=(async()=>{let last;for(const url of FENGARI_URLS){try{return await loadScript(url);}catch(err){last=err;}}throw last||new Error('Fengari runtime unavailable');})();return initPromise;}

  async function policySource(className){const key=String(className||'');if(sourceCache.has(key))return sourceCache.get(key);const path=`combat/${key}/ClassCombat.lua`,r=await fetch(path+'?v='+Date.now(),{cache:'no-store'});if(!r.ok)throw new Error(`${path}: HTTP ${r.status}`);const src=await r.text();sourceCache.set(key,src);return src;}
  function luaString(s){return '"'+String(s??'').replace(/\\/g,'\\\\').replace(/"/g,'\\"').replace(/\r/g,'\\r').replace(/\n/g,'\\n')+'"';}
  function luaLiteral(v,seen=new Set()){if(v===null||v===undefined)return 'nil';if(typeof v==='boolean')return v?'true':'false';if(typeof v==='number')return Number.isFinite(v)?String(v):'0';if(typeof v==='string')return luaString(v);if(typeof v!=='object')return 'nil';if(seen.has(v))return '{}';seen.add(v);if(Array.isArray(v))return '{'+v.map(x=>luaLiteral(x,seen)).join(',')+'}';return '{'+Object.entries(v).filter(([,x])=>typeof x!=='function').map(([k,x])=>'['+luaString(k)+']='+luaLiteral(x,seen)).join(',')+'}';}
  function buildTalentNames(build){const out={};for(const t of build?.combatTalents||[]){const rank=Number(String(t.rank||'0').split('/')[0])||0;if(rank>0)out[t.name]=rank;}return out;}
  function sanitizeContext(ctx,build){return {self:ctx?.self||{},enemy:ctx?.enemy||{},range:Number(ctx?.range)||0,spec:ctx?.spec||build?.spec||'',buildId:ctx?.buildId||build?.id||'',behindTarget:ctx?.behindTarget===true,readyMap:ctx?.readyMap||{},talentNames:ctx?.talentNames||buildTalentNames(build),build:{id:build?.id||'',modifiers:build?.modifiers||{}},policy:ctx?.policy||null,castRemainingMs:Number(ctx?.castRemainingMs)||0};}
  function chunkFor(source,ctx,build){const c=sanitizeContext(ctx,build);return `
local Policy=(function()\n${source}\nend)()
local ctx=${luaLiteral(c)}
function ctx:ready(name) return self.readyMap[name] == true end
function ctx:hasTalent(name) return (self.talentNames[name] or 0) > 0 end
function ctx:modifier(name) return self.build.modifiers[name] end
local d=Policy.choose(ctx) or {}
return tostring(d.action or '') .. '\31' .. tostring(d.reason or '') .. '\31' .. tostring(d.range or '')
`;}
  async function choose(className,ctx,build){await init();const source=await policySource(className);const raw=window.fengari.load(chunkFor(source,ctx,build),`@${className}/ClassCombat.lua`)();const parts=String(raw??'').split('\x1f');return {action:parts[0]||'',reason:parts[1]||'',range:parts[2]===''?null:Number(parts[2]),runtime:'LUA_FENGARI'};}

  async function selfTest(){
    const T=window.WOW_TALENTS,hemo=T?.get?.('rogue_cb_hemo_21_3_27'),dagger=T?.get?.('rogue_imp_sprint_backstab_16_12_23'),mage=T?.get?.('mage_deep_frost_17_0_34');
    const ready={'Vanish':true,'Preparation':true,'Sprint':true,'Kick':true,'Kidney Shot':true,'Cold Blood':true,'Gouge':true};
    const champion=window.WOW_DATA?.roguePolicyChampion||{evisMinCp:4,hemoMinEnergy:65,kidneyMinCp:5,coldBloodMinCp:5,sprintMinRange:5.1,kickMinRemainingMs:0,kidneyEnergyReserve:0,executeEvisHpPct:0,executeEvisMinCp:4,vanishOnRoot:true,prepWhenRootedAndVanishDown:true,kickEnabled:true};
    const opener=await choose('Rogue',{spec:'Subtlety',buildId:hemo?.id,self:{stealthed:true,energy:100,comboPoints:0},enemy:{},range:5,readyMap:ready,policy:champion},hemo);
    const pool=await choose('Rogue',{spec:'Subtlety',buildId:hemo?.id,self:{stealthed:false,energy:60,comboPoints:0},enemy:{healthPct:100},range:5,readyMap:ready,policy:champion},hemo);
    const builder=await choose('Rogue',{spec:'Subtlety',buildId:hemo?.id,self:{stealthed:false,energy:65,comboPoints:0},enemy:{healthPct:100},range:5,readyMap:ready,policy:champion},hemo);
    const evis4=await choose('Rogue',{spec:'Subtlety',buildId:hemo?.id,self:{stealthed:false,energy:35,comboPoints:4,coldBloodActive:false},enemy:{healthPct:100},range:5,readyMap:ready,policy:champion},hemo);
    const daggerRear=await choose('Rogue',{spec:'Subtlety',buildId:dagger?.id,self:{stealthed:true,energy:100,comboPoints:0},enemy:{},range:5,behindTarget:false,readyMap:ready},dagger);
    const daggerAmbush=await choose('Rogue',{spec:'Subtlety',buildId:dagger?.id,self:{stealthed:true,energy:100,comboPoints:0},enemy:{},range:5,behindTarget:true,readyMap:ready},dagger);
    const mageBlink=await choose('Mage',{spec:'Frost',buildId:mage?.id,self:{stunned:true,healthPct:100,manaShieldAbsorb:855,iceBarrierAbsorb:878},enemy:{},range:5,readyMap:{'Blink':true}},mage);
    const checks=[
      {name:'CB/Hemo opener',pass:opener.action==='Cheap Shot',actual:opener.action},
      {name:'g3 pool below 65',pass:pool.action==='WAIT',actual:pool.action},
      {name:'g3 Hemorrhage at 65',pass:builder.action==='Hemorrhage',actual:builder.action},
      {name:'g3 Eviscerate at 4 CP',pass:evis4.action==='Eviscerate',actual:evis4.action},
      {name:'Dagger seeks rear arc',pass:daggerRear.action==='MOVE_BEHIND',actual:daggerRear.action},
      {name:'Dagger Ambush from behind',pass:daggerAmbush.action==='Ambush',actual:daggerAmbush.action},
      {name:'Mage Blink policy',pass:mageBlink.action==='Blink',actual:mageBlink.action}
    ];
    return {pass:checks.every(x=>x.pass),checks,version:'0.27-lua-runtime'};
  }

  window.WOW_LUA_RUNTIME={version:'0.27',init,choose,selfTest,policySource,status:'LOADING'};
  init().then(async()=>{window.WOW_LUA_RUNTIME.status='READY';try{window.WOW_LUA_RUNTIME.lastSelfTest=await selfTest();}catch(err){window.WOW_LUA_RUNTIME.lastError=String(err?.stack||err);window.WOW_LUA_RUNTIME.status='ERROR';}document.dispatchEvent(new CustomEvent('wow-lua-runtime-ready',{detail:window.WOW_LUA_RUNTIME}));}).catch(err=>{window.WOW_LUA_RUNTIME.status='ERROR';window.WOW_LUA_RUNTIME.lastError=String(err?.stack||err);document.dispatchEvent(new CustomEvent('wow-lua-runtime-ready',{detail:window.WOW_LUA_RUNTIME}));});
})();
