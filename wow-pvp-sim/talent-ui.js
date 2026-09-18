(function(){
  const $=id=>document.getElementById(id);
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const timers={a:null,b:null};
  function read(p){return{class:$(p+'c')?.value||'—',spec:$(p+'s')?.value||'—'};}
  function renderOne(p){
    const root=$(p+'TalentPanel');if(!root)return;
    const s=read(p),F=window.WOW_FOREVER_TALENTS,B=window.WOW_FOREVER_BUILDS;
    if(!F||F.status==='loading'){root.innerHTML='<div class="muted">Loading Forever talents…</div>';return;}
    if(F.status==='error'){root.innerHTML='<div class="red">Forever talent dataset unavailable.</div>';return;}
    const audit=B?.audit?.(p,s.class)||{points:0,remaining:51,issues:[]};
    const info=F.classInfo?.(s.class),dist=Object.entries(info?.treeIds||{}).map(([name,id])=>[name,B?.pointsInTree?.(p,s.class,id)||0]);
    const selected=B?.selected?.(p,s.class)||[],build=B?.get?.(p),preset=build?.preset;
    const buildLabel=preset?.id?(preset.label+(preset.status==='CUSTOMIZED'?' · customized':'')):'Custom / manual';
    root.innerHTML='<div class="talent-head"><div><h3>'+esc(s.class)+' · '+esc(s.spec)+'</h3><p>'+esc(buildLabel)+' · Wowhead db '+esc(F.db||'—')+'</p></div><span class="'+(audit.points===51?'green':'amber')+'">'+audit.points+'/51</span></div>'+
      '<div class="talent-points">'+dist.map(([n,v])=>'<div><span>'+esc(n)+'</span><b>'+v+'</b></div>').join('')+'</div>'+
      '<div class="talent-list">'+(selected.length?selected.map(x=>'<div class="talent-row"><b>'+esc(x.node.name)+' <span>'+x.rank+'/'+x.node.maxRank+'</span></b><p>'+esc(x.node.descriptions?.[String(x.rank)]||'')+'</p></div>').join(''):'<div class="muted">No points allocated. Configure the full tree in Armory.</div>')+'</div>'+
      '<div class="note">Forever-only. Popular public pre-builds are selectable in Armory and are not labeled as “best”; manual builds remain supported.</div>';
  }
  function schedule(p){clearTimeout(timers[p]);timers[p]=setTimeout(()=>renderOne(p),0);}
  function render(){schedule('a');schedule('b');}
  ['ac','as'].forEach(id=>$(id)?.addEventListener('change',()=>schedule('a')));
  ['bc','bs'].forEach(id=>$(id)?.addEventListener('change',()=>schedule('b')));
  document.addEventListener('wow-forever-talents-ready',render);
  document.addEventListener('wow-forever-build-changed',e=>{if(e.detail?.player==='a'||e.detail?.player==='b')schedule(e.detail.player);});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',render,{once:true});else render();
  window.WOW_TALENT_UI={render,renderPlayer:schedule,version:'0.42-forever-presets'};
})();