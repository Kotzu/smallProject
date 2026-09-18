(function(){
  const EXPECTED_CLASSES=['Mage','Warrior','Rogue','Priest','Shaman','Druid','Warlock','Hunter','Paladin'];
  function run(){
    const F=window.WOW_FOREVER_TALENTS,B=window.WOW_FOREVER_BUILDS;if(!F||F.status!=='ready')return null;
    const checks=[];const add=(name,pass,details)=>checks.push({name,pass:!!pass,details});
    const cov=F.coverage||{};
    add('Forever-only ruleset',!document.getElementById('rulesetMode')&&document.title.includes('WoW Forever'),'No Classic/Forever mode selector; project is fixed to WoW Forever');
    add('Forever live dataset loaded',F.status==='ready',`db ${F.db||'—'} · ${F.provenance?.status||'—'}`);
    add('Forever 9 classes',cov.classes===9,`${cov.classes||0}/9 classes`);
    add('Forever 27 trees',cov.totalTrees===27,`${cov.totalTrees||0}/27 trees`);
    add('Forever live talent nodes',Number(cov.totalNodes)>0,`${cov.totalNodes||0} current Wowhead talent nodes (live dataset; count may change)`);
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
    add('Legacy preset selectors removed',!document.getElementById('abuild')&&!document.getElementById('bbuild'),'Forever build allocation comes only from the interactive talent trees/presets');
    add('Armory talent renderer available',!!window.WOW_ARMORY_TALENTS,'Player A + Player B Forever talent-tree renderer');
    add('Forever build allocator available',!!B&&B.MAX_POINTS===51,`allocator ${B?.version||'missing'} · cap ${B?.MAX_POINTS||'—'}`);
    add('Forever Fight remains gated',document.getElementById('runBtn')?.disabled===true&&document.getElementById('fightRunBtn')?.disabled===true,'No legacy calibration may unlock a Forever fight');
    const AD=window.WOW_FOREVER_ARMORY_DATA,ra=AD?.audit?.({class:'Rogue',spec:'Subtlety',race:'Undead'}),ma=AD?.audit?.({class:'Mage',spec:'Frost',race:'Gnome'});
    add('Forever Armory data module',AD?.version==='0.41-wowhead-forever-items-enchants',AD?.version||'missing');
    add('Rogue Armory 17/17',ra?.gearIdentityPass===true&&ra?.verifiedItems===17,`${ra?.verifiedItems||0}/17 verified Forever items`);
    add('Mage Armory 17/17 slot state',ma?.gearIdentityPass===true&&ma?.verifiedItems===16&&ma?.emptyVerified===1,`${ma?.verifiedItems||0} items + ${ma?.emptyVerified||0} verified empty off-hand`);
    add('Rogue Forever enchants',ra?.verifiedEnchants===11&&ra?.totalEnchants===11,`${ra?.verifiedEnchants||0}/${ra?.totalEnchants||0} verified`);
    add('Mage Forever enchants',ma?.verifiedEnchants===9&&ma?.totalEnchants===9,`${ma?.verifiedEnchants||0}/${ma?.totalEnchants||0} verified`);
    add('No Classic item links in Armory',!document.querySelector('#armory a[href*="/classic/"]'),'Forever item URLs only');
    add('Armory UI v0.42 optimized',window.WOW_ARMORY_UI?.version==='0.42-optimized-armory-presets',window.WOW_ARMORY_UI?.version||'missing');
    add('Armory talent UI v0.42 presets',window.WOW_ARMORY_TALENTS?.version==='0.42-popular-presets',window.WOW_ARMORY_TALENTS?.version||'missing');
    const P=window.WOW_FOREVER_PRESETS;
    add('Popular preset registry',P?.version==='0.2-popular-public-builds',P?.version||'missing');
    add('Rogue popular Subtlety preset',P?.defaultFor?.('Rogue','Subtlety')?.distribution==='22/3/26',P?.defaultFor?.('Rogue','Subtlety')?.label||'missing');
    add('Mage popular Frost preset',P?.defaultFor?.('Mage','Frost')?.distribution==='18/0/33',P?.defaultFor?.('Mage','Frost')?.label||'missing');
    if(P){
      const allPresets=P.all?.()||[],pointFailures=allPresets.filter(x=>P.points?.(x)!==51);
      add('All registered presets are 51 points',allPresets.length>=10&&pointFailures.length===0,`${allPresets.length} presets · bad: ${pointFailures.map(x=>x.id).join(', ')||'none'}`);
      if(B){
        const liveFailures=[];
        for(const preset of allPresets){
          const qp='__qa_preset_'+preset.id;
          const applied=B.applyPreset(qp,preset);
          const aud=applied.ok?B.audit(qp,preset.className,{requireMax:true}):null;
          if(!applied.ok||!aud?.pass||aud.points!==51)liveFailures.push(`${preset.id}: ${applied.reason||aud?.issues?.join('; ')||'audit fail'}`);
          B.clear(qp,preset.className);
        }
        add('All presets pass live Forever tree audit',liveFailures.length===0,liveFailures.join(' · ')||`${allPresets.length}/${allPresets.length} presets valid`);
      }
    }
    if(B&&P){
      const rp=P.defaultFor('Rogue','Subtlety'),mp=P.defaultFor('Mage','Frost');
      const rr=rp?B.applyPreset('__qa_rogue__',rp):{ok:false},mr=mp?B.applyPreset('__qa_mage__',mp):{ok:false};
      const ra2=B.audit('__qa_rogue__','Rogue',{requireMax:true}),ma2=B.audit('__qa_mage__','Mage',{requireMax:true});
      add('Rogue popular preset live-tree audit',rr.ok&&ra2.pass&&ra2.points===51,rr.ok?`${ra2.points}/51 · ${rp.label}`:(rr.reason||'apply failed'));
      add('Mage popular preset live-tree audit',mr.ok&&ma2.pass&&ma2.points===51,mr.ok?`${ma2.points}/51 · ${mp.label}`:(mr.reason||'apply failed'));
      const before=JSON.stringify(B.get('__qa_rogue__'));
      const bad=B.applyPreset('__qa_rogue__',{id:'invalid',className:'Rogue',spec:'Subtlety',ranks:{'Definitely Missing Talent':51}});
      const after=JSON.stringify(B.get('__qa_rogue__'));
      add('Invalid preset is atomic',bad.ok===false&&before===after,bad.reason||'expected failure');
      B.clear('__qa_rogue__','Rogue');B.clear('__qa_mage__','Mage');
    }
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
    const root=document.getElementById('qaReport');if(root){let old=root.querySelector('.forever-qa-block');if(old)old.remove();const block=document.createElement('section');block.className='forever-qa-block';block.innerHTML=`<div class="duel-summary"><div class="${failed?'red':'winner'}">FOREVER DATA QA ${failed?'FAIL':'PASS'} · ${checks.length-failed}/${checks.length}</div><div class="result-meta">Forever-only · live Wowhead db ${F.db} · ${cov.totalNodes} nodes · ${cov.totalTrees} trees · combat strictly gated.</div></div><div class="rule-grid" style="margin-top:10px">${checks.map(c=>`<div class="rule-card"><h3 class="${c.pass?'green':'red'}">${c.pass?'✓':'✗'} ${c.name}</h3><p>${String(c.details??'')}</p></div>`).join('')}</div>`;root.prepend(block);}
    return window.WOW_FOREVER_QA;
  }
  document.addEventListener('wow-forever-talents-ready',()=>setTimeout(run,0));
  document.addEventListener('wow-forever-build-changed',e=>{const p=e.detail?.player;if(p==='a'||p==='b')setTimeout(run,0);});
  document.addEventListener('wow-ruleset-changed',()=>setTimeout(run,0));
  if(window.WOW_FOREVER_TALENTS?.status==='ready')setTimeout(run,0);
  window.WOW_FOREVER_QA_RUN=run;
})();
