(function(){
  const EXPECTED_CLASSES=['Mage','Warrior','Rogue','Priest','Shaman','Druid','Warlock','Hunter','Paladin'];
  function run(){
    const F=window.WOW_FOREVER_TALENTS;if(!F||F.status!=='ready')return null;
    const checks=[];const add=(name,pass,details)=>checks.push({name,pass:!!pass,details});
    const cov=F.coverage||{};
    add('Forever live dataset loaded',F.status==='ready',`db ${F.db||'—'} · ${F.provenance?.status||'—'}`);
    add('Forever 9 classes',cov.classes===9,`${cov.classes||0}/9 classes`);
    add('Forever 27 trees',cov.totalTrees===27,`${cov.totalTrees||0}/27 trees`);
    add('Every class has 3 trees',EXPECTED_CLASSES.every(c=>Object.keys(F.classInfo(c)?.trees||{}).length===3),EXPECTED_CLASSES.map(c=>`${c}:${Object.keys(F.classInfo(c)?.trees||{}).length}`).join(' · '));
    add('Every Forever tree has talents',EXPECTED_CLASSES.every(c=>Object.values(F.classInfo(c)?.treeIds||{}).every(id=>F.treeById(id).length>0)),`${cov.totalNodes||0} total nodes`);
    const rogue=F.classInfo('Rogue'),mage=F.classInfo('Mage');
    add('Rogue tree IDs current',rogue?.treeIds?.Combat===181&&rogue?.treeIds?.Assassination===182&&rogue?.treeIds?.Subtlety===183,JSON.stringify(rogue?.treeIds||{}));
    add('Mage tree IDs current',mage?.treeIds?.Fire===41&&mage?.treeIds?.Frost===61&&mage?.treeIds?.Arcane===81,JSON.stringify(mage?.treeIds||{}));
    const hemo=F.tree('Rogue','Subtlety')?.find(x=>x.name==='Hemorrhage');
    const thousand=F.tree('Rogue','Subtlety')?.find(x=>x.name==='Thousand Cuts');
    const venom=F.tree('Rogue','Assassination')?.find(x=>x.name==='Venom');
    const iceLance=F.tree('Mage','Frost')?.find(x=>x.name==='Ice Lance');
    add('Rogue updated Forever nodes present',!!hemo&&!!thousand&&!!venom,`Hemorrhage #${hemo?.id||'—'} · Thousand Cuts #${thousand?.id||'—'} · Venom #${venom?.id||'—'}`);
    add('Mage updated Forever nodes present',!!iceLance,`Ice Lance #${iceLance?.id||'—'}`);
    add('Forever remains provisional',F.provenance?.status==='PROVISIONAL_UNTIL_BETA_DATAMINING',F.provenance?.status||'missing');
    add('Classic build not reused in Forever',document.getElementById('rulesetMode')?.value!=='forever'||(document.getElementById('abuild')?.disabled&&document.getElementById('bbuild')?.disabled),'Forever disables Classic build selectors');
    add('Armory talent renderer available',!!window.WOW_ARMORY_TALENTS,'Player A + Player B talent-tree renderer');
    const failed=checks.filter(x=>!x.pass).length;
    window.WOW_FOREVER_QA={checks,passed:checks.length-failed,failed,pass:failed===0,db:F.db,totalNodes:cov.totalNodes,totalTrees:cov.totalTrees};
    const root=document.getElementById('qaReport');if(root){let old=root.querySelector('.forever-qa-block');if(old)old.remove();const block=document.createElement('section');block.className='forever-qa-block';block.innerHTML=`<div class="duel-summary"><div class="${failed?'red':'winner'}">FOREVER DATA QA ${failed?'FAIL':'PASS'} · ${checks.length-failed}/${checks.length}</div><div class="result-meta">Live Wowhead db ${F.db} · ${cov.totalNodes} nodes · ${cov.totalTrees} trees · source remains provisional until beta datamining.</div></div><div class="rule-grid" style="margin-top:10px">${checks.map(c=>`<div class="rule-card"><h3 class="${c.pass?'green':'red'}">${c.pass?'✓':'✗'} ${c.name}</h3><p>${String(c.details??'')}</p></div>`).join('')}</div>`;root.prepend(block);}
    return window.WOW_FOREVER_QA;
  }
  document.addEventListener('wow-forever-talents-ready',run);
  if(window.WOW_FOREVER_TALENTS?.status==='ready')run();
  window.WOW_FOREVER_QA_RUN=run;
})();