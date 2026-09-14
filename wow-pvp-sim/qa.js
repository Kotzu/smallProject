(()=>{
  const D=window.WOW_DATA,E=window.WOW_ENGINE,DUEL=window.WOW_DUEL,A=window.WOW_ARMORY,T=window.WOW_TALENTS;
  const $=id=>document.getElementById(id);
  const cfg={a:{class:'Rogue',spec:'Subtlety',race:'Undead',gear:'Level 60 PvP BiS',build:'rogue_cb_hemo_21_3_27'},b:{class:'Mage',spec:'Frost',race:'Gnome',gear:'Level 60 PvP BiS',build:'mage_deep_frost_17_0_34'}};
  const checks=[];
  const add=(name,pass,details)=>checks.push({name,pass:!!pass,details});
  const nearly=(a,b,eps=1e-6)=>Math.abs(a-b)<=eps;

  try{
    add('Player A STAT AUDIT',A?.audit(cfg.a)?.pass===true,A?.audit(cfg.a)?.reason||'audit indisponibil');
    add('Player B STAT AUDIT',A?.audit(cfg.b)?.pass===true,A?.audit(cfg.b)?.reason||'audit indisponibil');
    const ta=T?.auditSelection(cfg.a),tb=T?.auditSelection(cfg.b);
    add('Rogue talent build audit',ta?.pass===true,ta?.reason||'talent audit indisponibil');
    add('Mage talent build audit',tb?.pass===true,tb?.reason||'talent audit indisponibil');
    add('Rogue level 60 talent points',T?.pointTotal(ta?.build?.points)===51,`${ta?.build?.points} = ${T?.pointTotal(ta?.build?.points)} points`);
    add('Mage level 60 talent points',T?.pointTotal(tb?.build?.points)===51,`${tb?.build?.points} = ${T?.pointTotal(tb?.build?.points)} points`);

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
    const fake={a:{...cfg.a,build:'unverified_build'},b:{...cfg.b}};
    add('Unverified build is blocked',DUEL.canRun(fake).ready===false,'strict mode must reject a non-calibrated build');
    const det=DUEL.selfTest(cfg);
    add('Deterministic replay',det.deterministic===true,`seed 1337 → ${det.winner} · ${det.duration}s · v${det.version}`);

    let finite=true,calibrated=true,buildsAttached=true;
    for(let i=1;i<=100;i++){
      const r=DUEL.run(i,cfg);
      if(r.error||!Number.isFinite(r.duration)||!Number.isFinite(r.final?.rogue?.hp)||!Number.isFinite(r.final?.mage?.hp)||!Number.isFinite(r.final?.mage?.mana))finite=false;
      if(r.kernelStatus!=='FIRST_MATCHUP_CALIBRATED_WITH_TALENTS'||(r.calibrationRequired||[]).length)calibrated=false;
      if(r.builds?.a?.id!==cfg.a.build||r.builds?.b?.id!==cfg.b.build)buildsAttached=false;
    }
    add('100-seed numeric smoke test',finite,'100 deterministic duels fără NaN/Infinity/error');
    add('Talent-aware calibration gate',calibrated,'100/100 duels report calibrated-with-talents and 0 calibrări restante');
    add('Build identity preserved',buildsAttached,'selected build IDs are attached to all sampled duel results');

    const b=DUEL.batch(1337,100,cfg),total=Object.values(b.wins||{}).reduce((x,y)=>x+y,0);
    add('Batch accounting',total===100,`wins total ${total}/100`);
  }catch(err){add('QA runtime',false,String(err?.stack||err));}

  const passed=checks.filter(x=>x.pass).length,failed=checks.length-passed,root=$('qaReport');
  if(root)root.innerHTML=`<div class="duel-summary"><div class="${failed?'red':'winner'}">QA ${failed?'FAIL':'PASS'} · ${passed}/${checks.length}</div><div class="result-meta">Stats + formulas + talent builds + deterministic duel checks.</div></div><div class="rule-grid" style="margin-top:10px">${checks.map(c=>`<div class="rule-card"><h3 class="${c.pass?'green':'red'}">${c.pass?'✓':'✗'} ${c.name}</h3><p>${String(c.details??'')}</p></div>`).join('')}</div>`;
  window.WOW_QA={version:'0.16-qa',checks,passed,failed,pass:failed===0};
})();