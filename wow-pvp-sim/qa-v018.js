(()=>{
  const D=window.WOW_DATA,T=window.WOW_TALENTS,DUEL=window.WOW_DUEL,A=window.WOW_ARMORY;
  const base=window.WOW_QA||{checks:[]};
  const checks=[...(base.checks||[])];
  const add=(name,pass,details)=>checks.push({name,pass:!!pass,details});

  try{
    const canonicalId='rogue_imp_sprint_backstab_16_12_23';
    const variantId='rogue_imp_sprint_backstab_17_12_22';
    const canonical=T?.get(canonicalId),variant=T?.get(variantId);
    const canonicalCfg={
      a:{class:'Rogue',spec:'Subtlety',race:'Undead',gear:'Level 60 PvP BiS',build:canonicalId},
      b:{class:'Mage',spec:'Frost',race:'Gnome',gear:'Level 60 PvP BiS',build:'mage_deep_frost_17_0_34'}
    };

    add('Canonical Rogue dagger build registered',!!canonical,canonical?`${canonical.name} · ${canonical.points}`:'missing');
    add('Canonical 16/12/23 = 51 points',T?.pointTotal(canonical?.points)===51,`${canonical?.points} = ${T?.pointTotal(canonical?.points)} points`);
    add('Canonical calculator identity',canonical?.calculator==='305020105-320302002-05024303030012',canonical?.calculator||'missing');
    add('Canonical dagger build remains strict-locked',T?.auditSelection(canonicalCfg.a)?.status==='VERIFIED_LOCKED'&&DUEL?.canRun(canonicalCfg)?.ready===false,'verified build cannot enter duel until positional/mechanic calibration passes');
    add('Forum 17/12/22 variant kept separate',variant?.calculator==='005320124-320302002-05024303030011'&&variant?.points==='17/12/22',`${variant?.name||'missing'} · ${variant?.points||'—'}`);

    const canonicalArmory=A?.audit(canonicalCfg.a),canonicalProfile=A?.rogueProfile(canonicalCfg.a);
    add('Canonical dagger Armory audit',canonicalArmory?.pass===true,canonicalArmory?.reason||'missing');
    add('Canonical build uses dagger loadout',canonicalProfile?.slots?.['Main Hand']===22802&&canonicalProfile?.slots?.['Off Hand']===21126,'Kingsfall #22802 / Death\'s Sting #21126');

    const backstab=D?.pvpSpellbooks?.Rogue?.backstab;
    add('Backstab R9 exact data',backstab?.id===11281&&backstab?.cost===60&&backstab?.weaponDamagePct===150&&backstab?.flatDamage===210&&backstab?.requiresBehind===true,'spell 11281 · 60 Energy · 150% weapon +210 · behind');

    const gouge=D?.pvpSpellbooks?.Rogue?.gouge;
    add('Gouge R5 exact data',gouge?.id===11286&&gouge?.cost===45&&gouge?.damage===75&&gouge?.incapacitateMs===4000&&gouge?.cooldownMs===10000,'spell 11286 · 45 Energy · 75 dmg · 4s incap · 10s CD');

    const prep=D?.pvpSpellbooks?.Rogue?.preparation;
    add('Preparation reset semantics',prep?.id===14185&&prep?.resetsRogueFamilyCooldowns===true&&prep?.excludesSelf===true,'CMaNGOS: resets Rogue-family cooldowns except Preparation itself');

    const mods=canonical?.modifiers||{};
    add('16/12/23 combat modifiers',mods.improvedSprint===true&&mods.backstabCritBonusPct===30&&mods.ambushCritBonusPct===45&&mods.initiativeProcPct===75&&mods.cheapShotEnergy===40,'Imp Sprint · Backstab +30 crit · Ambush +45 crit · Initiative 75% · Cheap Shot 40');
  }catch(err){
    add('v0.18 QA runtime',false,String(err?.stack||err));
  }

  const passed=checks.filter(x=>x.pass).length,failed=checks.length-passed;
  const root=document.getElementById('qaReport');
  if(root){
    root.innerHTML=`<div class="duel-summary"><div class="${failed?'red':'winner'}">QA ${failed?'FAIL':'PASS'} · ${passed}/${checks.length}</div><div class="result-meta">Stats + gear + talent builds + Rogue ability data + strict kernel gates.</div></div><div class="rule-grid" style="margin-top:10px">${checks.map(c=>`<div class="rule-card"><h3 class="${c.pass?'green':'red'}">${c.pass?'✓':'✗'} ${c.name}</h3><p>${String(c.details??'')}</p></div>`).join('')}</div>`;
  }
  window.WOW_QA={version:'0.18-qa',checks,passed,failed,pass:failed===0};
})();
