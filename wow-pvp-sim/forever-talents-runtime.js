(function(){
  const CLASS_PREFIX={Mage:'Mage',Warrior:'Warrior',Rogue:'Rogue',Priest:'Priest',Shaman:'Shaman',Druid:'Druid',Warlock:'Warlock',Hunter:'Hunter',Paladin:'Paladin'};
  const TREE_ALIASES={
    ShamanElementalCombat:'Elemental',DruidFeralCombat:'Feral',WarlockCurses:'Affliction',WarlockSummoning:'Demonology',WarlockDestruction:'Destruction',PaladinCombat:'Retribution'
  };
  const state={status:'loading',error:null,data:null,provenance:null};
  const listeners=new Set();
  const notify=()=>{for(const fn of listeners){try{fn(api);}catch(e){console.warn('[ForeverTalents listener]',e);}}document.dispatchEvent(new CustomEvent('wow-forever-talents-ready',{detail:api}));};
  function displayTreeName(tree,className){
    const raw=String(tree?.description||'');if(TREE_ALIASES[raw])return TREE_ALIASES[raw];
    const prefix=CLASS_PREFIX[className]||'';return raw.startsWith(prefix)?raw.slice(prefix.length):raw;
  }
  function classTrees(className){
    const prefix=CLASS_PREFIX[className];if(!prefix||!state.data?.trees)return [];
    return Object.values(state.data.trees).filter(t=>String(t.description||'').startsWith(prefix)).sort((a,b)=>a.id-b.id);
  }
  function nodesForTree(treeId){
    const src=state.data?.talents?.[String(treeId)]||state.data?.talents?.[treeId]||{};
    return Object.values(src).map(n=>({...n,maxRank:Array.isArray(n.ranks)?n.ranks.length:Object.keys(n.descriptions||{}).length,treeId:Number(treeId)})).sort((a,b)=>(a.row-b.row)||(a.col-b.col)||(a.id-b.id));
  }
  function tree(className,treeName){
    const norm=String(treeName||'').toLowerCase();
    const t=classTrees(className).find(x=>displayTreeName(x,className).toLowerCase()===norm||String(x.description||'').toLowerCase()===norm);
    return t?nodesForTree(t.id):null;
  }
  function classInfo(className){
    const trees=classTrees(className);if(!trees.length)return null;
    const out={className,trees:{},treeIds:{},sourceDescriptions:{}};
    for(const t of trees){const name=displayTreeName(t,className);out.trees[name]=nodesForTree(t.id).length;out.treeIds[name]=t.id;out.sourceDescriptions[name]=t.description;}
    return out;
  }
  function classTotal(className){return classTrees(className).reduce((n,t)=>n+nodesForTree(t.id).length,0);}
  function allCoverage(){
    const classes=Object.keys(CLASS_PREFIX),perClass={};let totalNodes=0,totalTrees=0;
    for(const c of classes){const info=classInfo(c);const count=classTotal(c);perClass[c]=count;totalNodes+=count;totalTrees+=info?Object.keys(info.trees).length:0;}
    return {classes:classes.length,totalTrees,totalNodes,perClass};
  }
  const api={
    get status(){return state.status;},get error(){return state.error;},get snapshotDate(){return state.provenance?.fetchedAt||null;},
    get db(){return state.provenance?.db||null;},get officialSource(){return 'https://www.wowhead.com/forever/talent-calc';},
    get coverage(){return allCoverage();},get raw(){return state.data;},get provenance(){return state.provenance;},
    classInfo,classTotal,tree,nodesForTree,displayTreeName,
    treeById:id=>nodesForTree(id),
    onReady(fn){listeners.add(fn);if(state.status==='ready')queueMicrotask(()=>fn(api));return()=>listeners.delete(fn);}
  };
  window.WOW_FOREVER_TALENTS=api;
  fetch('/api/forever-talents',{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error(`HTTP ${r.status}`);return r.json();}).then(payload=>{
    state.data=payload.data;state.provenance=payload.provenance;state.status='ready';notify();
  }).catch(err=>{state.status='error';state.error=String(err?.message||err);console.error('[ForeverTalents]',err);notify();});
})();
