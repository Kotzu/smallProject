(()=>{
  const D=window.WOW_DATA,E=window.WOW_ENGINE,DUEL=window.WOW_DUEL,A=window.WOW_ARMORY,T=window.WOW_TALENTS,CE=window.WOW_CHARACTER_ENGINE,CD=window.WOW_CHARACTER_DATA;
  const $=id=>document.getElementById(id);
  const cfg={a:{class:'Rogue',spec:'Subtlety',race:'Undead',gear:'Level 60 PvP BiS',build:'rogue_cb_hemo_21_3_27'},b:{class:'Mage',spec:'Frost',race:'Gnome',gear:'Level 60 PvP BiS',build:'mage_deep_frost_17_0_34'}};
  const daggerCfg={a:{...cfg.a,build:'rogue_imp_sprint_backstab_17_12_22'},b:{...cfg.b}};
  const checks=[];
  const add=(name,pass,details)=>checks.push({name,pass:!!pass,details});
  const nearly=(a,b,eps=1e-6)=>Math.abs(a-b)<=eps;

  try{
    add('Player A STAT AUDIT',A?.audit(cfg.a)?.pass===true,A?.audit(cfg.a)?.reason||'audit indisponibil');
    add('Player B STAT AUDIT',A?.audit(cfg.b)?.pass===true,A?.audit(cfg.b)?.reason||'audit indisponibil');
    const ta=T?.auditSelection(cfg.a),tb=T?.auditSelection(cfg.b);
    add('Rogue CB/Hemo talent audit',ta?.pass===true&&ta?.kernelReady===true,ta?.reason||'talent audit indisponibil');
    add('Mage Frost talent audit',tb?.pass===true&&tb?.kernelReady===true,tb?.reason||'talent audit indisponibil');
    add('Rogue CB/Hemo 51 points',T?.pointTotal(ta?.build?.points)===51,`${ta?.build?.points} = ${T?.pointTotal(ta?.build?.points)} points`);
    add('Mage Frost 51 points',T?.pointTotal(tb?.build?.points)===51,`${tb?.build?.points} = ${T?.pointTotal(tb?.build?.points)} points`);

    const da=T?.auditSelection(daggerCfg.a),db=da?.build,dm=db?.modifiers||{};
    add('Rogue Imp Sprint build verified',da?.pass===true&&da?.status==='VERIFIED_LOCKED',da?.reason||'missing');
    add('Rogue Imp Sprint 51 points',T?.pointTotal(db?.points)===51,`${db?.points} = ${T?.pointTotal(db?.points)} points`);
    add('Imp Sprint talent modifiers',dm.improvedSprint===true&&dm.backstabCritBonusPct===30&&dm.opportunityDamagePct===20,'Sprint break + Backstab +30 crit + Opportunity +20 dmg');
    add('Imp Sprint kernel remains blocked',DUEL.canRun(daggerCfg).ready===false,'verified build must not run before positional dagger kernel calibration');

    const daggerProfile=A?.rogueProfile(daggerCfg.a),daggerAudit=A?.audit(daggerCfg.a),daggerChar=daggerProfile?CE?.rogue60Baseline(CD.level60.undeadRogue,daggerProfile):null;
    add('Dagger Armory STAT AUDIT',daggerAudit?.pass===true,daggerAudit?.reason||'missing');
    add('Dagger weapons exact IDs',daggerProfile?.slots?.['Main Hand']===22802&&daggerProfile?.slots?.['Off Hand']===21126,'Kingsfall #22802 / Death\'s Sting #21126');
    add('Dagger build STR/AGI/STA',daggerChar?.stats?.str===153&&daggerChar?.stats?.agi===317&&daggerChar?.stats?.sta===314,`STR ${daggerChar?.stats?.str} · AGI ${daggerChar?.stats?.agi} · STA ${daggerChar?.stats?.sta}`);
    add('Dagger build HP/AP/Armor',daggerChar?.health===4583&&daggerChar?.attackPower===1070&&daggerChar?.armor===2130,`HP ${daggerChar?.health} · AP ${daggerChar?.attackPower} · Armor ${daggerChar?.armor}`);
    add('Superior Striking applied',nearly(daggerProfile?.mainHandFlatDamage||0,5),'Kingsfall +5 weapon damage');

    const mp=D.pvpProfiles?.mage_frost_gnome_p6_core;
    add('Mage mana formula',mp?.stats?.mana===6258,`expected 6258 · actual ${mp?.stats?.mana}`);
    const mageArmor=Math.trunc((mp?.stats?.armorBeforeTalents||0)+(mp?.stats?.intellect||0)*0.5);
    add('Arcane Resilience armor',mageArmor===1197,`expected 1197 · actual ${mageArmor}`);

    const poison=D.pvpMechanics?.v010?.poisonBinaryResistance;
    add('Binary Nature resistance',nearly(poison?.totalResistPct||0,9),`expected 9% · actual ${poison?.totalResistPct}%`);
    const cp=D.pvpMechanics?.v010?.poisons?.cripplingII,mn=D.pvpMechanics?.v010?.poisons?.mindNumbingIII;
    add('Crippling effective application',nearly(cp?.procPct||0,27.3),`30% raw × 91% success = ${cp?.procPct}%`);
    add('Mind-numbing effective application',nearly(mn?.procPct||0,18.2),`20% raw × 91% success = ${mn?.procPct}%`);

    const armorReduction=E.physicalArmorReduction(3000,60)*100;
    add('Armor formula smoke test',nearly(armorReduction,35.294117647058826,1e-9),`3000 armor @60 = ${armorReduction.toFixed(6)}%`);
    add('Same-level spell floor',E.sameLevelSpellMiss(99)===1,`expected 1% · actual ${E.sameLevelSpellMiss(99)}%`);
    add('Same-level melee special cap',E.sameLevelMeleeSpecialMiss(5)===0,`expected 0% · actual ${E.sameLevelMeleeSpecialMiss(5)}%`);

    const gate=DUEL.canRun(cfg);
    add('Strict duel + talent gate',gate.ready===true,gate.ready?'ready':gate.missing.join(' · '));
    add('Talent-aware combat core active',DUEL.engineCoreVersion==='0.18.0',`core ${DUEL.engineCoreVersion||'missing'} · wrapper ${DUEL.version}`);
    const fake={a:{...cfg.a,build:'unverified_build'},b:{...cfg.b}};
    add('Unverified build is blocked',DUEL.canRun(fake).ready===false,'strict mode rejects unknown build');
    const det=DUEL.selfTest(cfg);
    add('Deterministic replay',det.deterministic===true,`seed 1337 → ${det.winner} · ${det.duration}s · v${det.version}`);

    let finite=true,calibrated=true,buildsAttached=true,runtimeAttached=true;
    for(let i=1;i<=100;i++){
      const r=DUEL.run(i,cfg);
      if(r.error||!Number.isFinite(r.duration)||!Number.isFinite(r.final?.rogue?.hp)||!Number.isFinite(r.final?.mage?.hp)||!Number.isFinite(r.final?.mage?.mana))finite=false;
      if(r.kernelStatus!=='ACTIVE_TALENT_RUNTIME'||(r.calibrationRequired||[]).length)calibrated=false;
      if(r.builds?.a?.id!==cfg.a.build||r.builds?.b?.id!==cfg.b.build)buildsAttached=false;
      if(!r.talentRuntime||r.talentRuntime.preparation!==true)runtimeAttached=false;
    }
    add('100-seed numeric smoke test',finite,'100 deterministic duels fără NaN/Infinity/error');
    add('Talent runtime calibration gate',calibrated,'100/100 active-kernel duels report ACTIVE_TALENT_RUNTIME');
    add('Build identity preserved',buildsAttached,'selected build IDs attached to sampled results');
    add('Talent runtime preserved',runtimeAttached,'runtime talent state attached to sampled results');

    const b=DUEL.batch(1337,100,cfg),total=Object.values(b.wins||{}).reduce((x,y)=>x+y,0);
    add('Batch accounting',total===100,`wins total ${total}/100`);
  }catch(err){add('QA runtime',false,String(err?.stack||err));}

  const passed=checks.filter(x=>x.pass).length,failed=checks.length-passed,root=$('qaReport');
  if(root)root.innerHTML=`<div class="duel-summary"><div class="${failed?'red':'winner'}">QA ${failed?'FAIL':'PASS'} · ${passed}/${checks.length}</div><div class="result-meta">Stats + gear + talent builds + active talent runtime + strict kernel gate + deterministic duel checks.</div></div><div class="rule-grid" style="margin-top:10px">${checks.map(c=>`<div class="rule-card"><h3 class="${c.pass?'green':'red'}">${c.pass?'✓':'✗'} ${c.name}</h3><p>${String(c.details??'')}</p></div>`).join('')}</div>`;
  window.WOW_QA={version:'0.20-qa',checks,passed,failed,pass:failed===0};
})();