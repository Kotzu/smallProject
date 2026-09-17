(function(){
  const MAX_POINTS=51;
  const players={a:null,b:null};
  const listeners=new Set();
  const F=()=>window.WOW_FOREVER_TALENTS;
  const clone=v=>JSON.parse(JSON.stringify(v));

  function emptyBuild(className){
    const api=F();
    const info=api?.classInfo?.(className);
    const ranks={};
    for(const id of Object.values(info?.treeIds||{}))for(const n of api.treeById(id)||[])ranks[String(n.id)]=0;
    return {ruleset:'forever',className,points:0,ranks,updatedAt:Date.now()};
  }
  function ensure(p,className){
    if(!players[p]||players[p].className!==className)players[p]=emptyBuild(className);
    return players[p];
  }
  function nodeById(id){
    const api=F();
    if(!api?.raw?.talents)return null;
    for(const tree of Object.values(api.raw.talents)){
      const n=tree?.[String(id)]||tree?.[id];
      if(n)return {...n,maxRank:Array.isArray(n.ranks)?n.ranks.length:Object.keys(n.descriptions||{}).length};
    }
    return null;
  }
  function treeForNode(id){
    const api=F();
    for(const [treeId,tree] of Object.entries(api?.raw?.talents||{}))if(tree?.[String(id)]||tree?.[id])return Number(treeId);
    return null;
  }
  function treePoints(build,treeId){
    const api=F();let total=0;
    for(const n of api?.treeById?.(treeId)||[])total+=Number(build.ranks[String(n.id)]||0);
    return total;
  }
  function prereqsMet(build,node){
    const reqs=Array.isArray(node.requires)?node.requires:[];
    return reqs.every(r=>Number(build.ranks[String(r.id)]||0)>=Number(r.qty||1));
  }
  function canAdd(p,className,nodeId){
    const api=F();if(!api||api.status!=='ready')return{ok:false,reason:'Forever dataset not ready'};
    const build=ensure(p,className),node=nodeById(nodeId);if(!node)return{ok:false,reason:'Unknown talent'};
    const cur=Number(build.ranks[String(nodeId)]||0);if(cur>=node.maxRank)return{ok:false,reason:'Max rank reached'};
    if(build.points>=MAX_POINTS)return{ok:false,reason:'51-point cap reached'};
    const treeId=treeForNode(nodeId),spent=treePoints(build,treeId),requiredByRow=Number(node.row||0)*5;
    if(spent<requiredByRow)return{ok:false,reason:`Need ${requiredByRow} points in this tree`};
    const requiredPoints=Number(node.requiredPoints||0);if(requiredPoints>0&&spent<requiredPoints)return{ok:false,reason:`Need ${requiredPoints} points in this tree`};
    if(!prereqsMet(build,node))return{ok:false,reason:'Prerequisite talent not met'};
    return{ok:true};
  }
  function dependents(build,nodeId){
    const api=F(),out=[];
    for(const tree of Object.values(api?.raw?.talents||{}))for(const n of Object.values(tree||{})){
      if(Number(build.ranks[String(n.id)]||0)<=0)continue;
      if((n.requires||[]).some(r=>String(r.id)===String(nodeId)))out.push(n);
    }
    return out;
  }
  function canRemove(p,className,nodeId){
    const build=ensure(p,className),node=nodeById(nodeId);if(!node)return{ok:false,reason:'Unknown talent'};
    const cur=Number(build.ranks[String(nodeId)]||0);if(cur<=0)return{ok:false,reason:'No points invested'};
    if(dependents(build,nodeId).length)return{ok:false,reason:'A selected talent depends on this one'};
    const treeId=treeForNode(nodeId),afterTree=treePoints(build,treeId)-1;
    const api=F();
    for(const n of api?.treeById?.(treeId)||[]){
      if(String(n.id)===String(nodeId))continue;
      if(Number(build.ranks[String(n.id)]||0)<=0)continue;
      const gate=Math.max(Number(n.row||0)*5,Number(n.requiredPoints||0));
      if(afterTree<gate)return{ok:false,reason:'Would invalidate a deeper selected talent'};
    }
    return{ok:true};
  }
  function notify(p){
    const snapshot=get(p);for(const fn of listeners){try{fn(p,snapshot);}catch(e){console.warn('[ForeverBuilds listener]',e);}}
    document.dispatchEvent(new CustomEvent('wow-forever-build-changed',{detail:{player:p,build:snapshot}}));
  }
  function add(p,className,nodeId){const check=canAdd(p,className,nodeId);if(!check.ok)return check;const b=ensure(p,className);b.ranks[String(nodeId)]=(b.ranks[String(nodeId)]||0)+1;b.points++;b.updatedAt=Date.now();notify(p);return{ok:true,build:get(p)};}
  function remove(p,className,nodeId){const check=canRemove(p,className,nodeId);if(!check.ok)return check;const b=ensure(p,className);b.ranks[String(nodeId)]--;b.points--;b.updatedAt=Date.now();notify(p);return{ok:true,build:get(p)};}
  function clear(p,className){players[p]=emptyBuild(className);notify(p);return get(p);}
  function get(p){return players[p]?clone(players[p]):null;}
  function rank(p,className,nodeId){return Number(ensure(p,className).ranks[String(nodeId)]||0);}
  function pointsInTree(p,className,treeId){return treePoints(ensure(p,className),treeId);}
  function selected(p,className){const b=ensure(p,className);return Object.entries(b.ranks).filter(([,r])=>r>0).map(([id,rank])=>({node:nodeById(id),rank})).filter(x=>x.node);}
  function audit(p,className){const b=ensure(p,className),issues=[];if(b.points>MAX_POINTS)issues.push('More than 51 points');for(const {node,rank} of selected(p,className)){if(rank>node.maxRank)issues.push(`${node.name}: over max rank`);const treeId=treeForNode(node.id),spent=treePoints(b,treeId),gate=Math.max(Number(node.row||0)*5,Number(node.requiredPoints||0));if(spent<gate)issues.push(`${node.name}: tier gate invalid`);if(!prereqsMet(b,node))issues.push(`${node.name}: prerequisite invalid`);}return{pass:issues.length===0,points:b.points,remaining:MAX_POINTS-b.points,issues};}
  function exportBuild(p){const b=get(p);if(!b)return null;return{...b,db:F()?.db||null,source:'Wowhead Forever runtime dataset',status:'USER_SELECTED_PROVISIONAL'};}
  function onChange(fn){listeners.add(fn);return()=>listeners.delete(fn);}

  window.WOW_FOREVER_BUILDS={MAX_POINTS,get,rank,pointsInTree,selected,audit,add,remove,clear,canAdd,canRemove,exportBuild,onChange,version:'0.31'};
})();
