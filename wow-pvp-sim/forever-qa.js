(function(){
  const EXPECTED_CLASSES=['Mage','Warrior','Rogue','Priest','Shaman','Druid','Warlock','Hunter','Paladin'];
  function run(){
    const F=window.WOW_FOREVER_TALENTS,B=window.WOW_FOREVER_BUILDS;if(!F||F.status!=='ready')return null;
    const checks=[];const add=(name,pass,details)=>checks.push({name,pass:!!pass,details});
    const cov=F.coverage||{};
    add('Forever live dataset loaded',F.status==='ready',`db ${F.db||'—'} · ${F.provenance?.status||'—'}`);
    add('Forever 9 classes',cov.classes===9,`${cov.classes||0}/9 classes`);
    add('Forever 27 trees',cov.totalTrees===27,`${cov.totalTrees||0}/27 trees`);
    add('Forever 351 current nodes',cov.totalNodes===351,`${cov.totalNodes||0}/351 current Wowhead talent nodes`);
    add('Every class has 3 trees',EXPECTED_CLASSES.every(c=>Object.keys(F.classInfo(c)?.trees||{}).length===3),EXPECTED_CLASSES.map(c=>`${c}:${Object.keys(F.classInfo(c)?.trees||{}).length}`).join(' · '));
    add('Every Forever tree has talents',EXPECTED_CLASSES.every(c=>Object.values(F.classInfo(c)?.treeIds||{}).every(id=>F.treeById(id).length>0)),`${cov.totalNodes||0} total nodes`);
    const rogue=F.classInfo('Rogue'),mage=F.classInfo('Mage');
    add('Rogue tree IDs current',rogue?.treeIds?.Combat===181&&rogue?.treeIds?.Assassination===182&&rogue?.treeIds?.Subtlety===183,JSON.stringify(rogue?.treeIds||{}));
    add('Mage tree IDs current',mage?.treeIds?.Fire===41&&mage?.treeIds?.Frost===61&&mage?.treeIds?.Arcane===81,JSON.stringify(mage?.treeIds||{}));
    add('Tree aliases normalized',F.classInfo('Warlock')?.treeIds?.Affliction===302&&F.classInfo('Warlock')?.treeIds?.Demonology===303&&F.classInfo('Paladin')?.treeIds?.Retribution===381,'Warlock Curses→Affliction · Summoning→Demonology · Paladin Combat→Retribution');
    const hemo=F.tree('Rogue','Subtlety')?.find(x=>x.name==='Hemorrhage');
    const thousand=F.tree('Rogue','Subtlety')?.find(x=>x.name==='Thousand Cuts');
    const venom=F.tree('Rogue','Assassination')?.find(x=>x.name==='Venom');
    const iceLance=F.tree('Mage','Frost')?.find(x=>x.name==='Ice Lance');
    add('Rogue updated Forever nodes present',!!hemo&&!!thousand&&!!venom,`Hemorrhage #${hemo?.id||'—'} · Thousand Cuts #${thousand?.id||'—'} · Venom #${venom?.id||'—'}`);
    add('Hemorrhage current tooltip',hemo?.descriptions?.['1']?.includes('145% if a Dagger is equipped')===true,hemo?.descriptions?.['1']||'missing');
    add('Mage updated Forever nodes present',!!iceLance,`Ice Lance #${iceLance?.id||'—'}`);
    add('Forever remains provisional',F.provenance?.status==='PROVISIONAL_UNTIL_BETA_DATAMINING',F.provenance?.status||'missing');
    add('Classic build not reused in Forever',document.getElementById('rulesetMode')?.value!=='forever'||(document.getElementById('abuild')?.disabled&&document.getElementById('bbuild')?.disabled),'Forever disables Classic build selectors');
    add('Armory talent renderer available',!!window.WOW_ARMORY_TALENTS,'Player A + Player B talent-tree renderer');
    add('Forever build allocator available',!!B&&B.MAX_POINTS===51,`allocator ${B?.version||'missing'} · cap ${B?.MAX_POINTS||'—'}`);
    if(B){
      const qp='__qa__';
      B.clear(qp,'Rogue');
      const first=F.tree('Rogue','Subtlety')?.find(x=>x.requiredPoints===0);
      const added=first?B.add(qp,'Rogue',first.id):{ok:false};
      const aud=B.audit(qp,'Rogue');
      add('Forever allocation smoke test',added.ok&&aud.pass&&aud.points===1,first?`${first.name} -> ${B.rank(qp,'Rogue',first.id)}/${first.maxRank}`:'no tier-1 node');
      B.clear(qp,'Rogue');
    }
    const failed=checks.filter(x=>!x.pass).length;
    window.WOW_FOREVER_QA={checks,passed:checks.length-failed,failed,pass:failed===0,db:F.db,totalNodes:cov.totalNodes,totalTrees:cov.totalTrees};
    const root=document.getElementById('qaReport');if(root){let old=root.querySelector('.forever-qa-block');if(old)old.remove();const block=document.createElement('section');block.className='forever-qa-block';block.innerHTML=`<div class="duel-summary"><div class="${failed?'red':'winner'}">FOREVER DATA QA ${failed?'FAIL':'PASS'} · ${checks.length-failed}/${checks.length}</div><div class="result-meta">Live Wowhead db ${F.db} · ${cov.totalNodes} nodes · ${cov.totalTrees} trees · user build allocator enabled · combat remains gated.</div></div><div class="rule-grid" style="margin-top:10px">${checks.map(c=>`<div class="rule-card"><h3 class="${c.pass?'green':'red'}">${c.pass?'✓':'✗'} ${c.name}</h3><p>${String(c.details??'')}</p></div>`).join('')}</div>`;root.prepend(block);}
    return window.WOW_FOREVER_QA;
  }
  document.addEventListener('wow-forever-talents-ready',()=>setTimeout(run,0));
  document.addEventListener('wow-forever-build-changed',e=>{const p=e.detail?.player;if(p==='a'||p==='b')setTimeout(run,0);});
  if(window.WOW_FOREVER_TALENTS?.status==='ready')run();
  window.WOW_FOREVER_QA_RUN=run;
})();
