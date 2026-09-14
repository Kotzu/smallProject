(()=>{
  const D=window.WOW_DATA,T=window.WOW_TALENTS;
  const base=window.WOW_QA||{checks:[]};
  const checks=[...(base.checks||[])];
  const add=(name,pass,details)=>checks.push({name,pass:!!pass,details});
  const nearly=(a,b,eps=1e-9)=>Math.abs((a??NaN)-b)<=eps;

  try{
    const w=D?.v019?.rogueDaggerWeaponSkill;
    add('Dagger skill PvP audit',w?.status==='VERIFIED'&&w?.weaponSkill===303&&w?.targetDefense===300,'303 weapon skill vs 300 defense');
    add('+3 Daggers miss reduction',nearly(w?.missReductionPct,0.12),`expected 0.12% · actual ${w?.missReductionPct}%`);
    add('+3 Daggers dodge reduction',nearly(w?.dodgeReductionPct,0.12),`expected 0.12% · actual ${w?.dodgeReductionPct}%`);
    add('+weapon skill no PvP crit bonus',w?.critBonusPctVsPlayer===0,`actual ${w?.critBonusPctVsPlayer}%`);

    const tm=D?.v019?.rogueTalentMechanics||{};
    add('Improved Sprint 2/2 exact',tm.improvedSprint?.procPct===100&&tm.improvedSprint?.removesMovementImpairingOnActivation===true,'100% movement-impair removal on activation');
    add('Initiative 3/3 exact',tm.initiative?.procPct===75&&tm.initiative?.extraComboPoints===1,'75% chance for +1 CP on Ambush/Garrote/Cheap Shot');
    add('Improved Gouge 3/3 exact',tm.improvedGouge?.totalDurationMs===5500,'4.0s base + 1.5s = 5.5s');
    add('Elusiveness 2/2 exact',tm.elusiveness?.vanishCooldownMs===210000&&tm.elusiveness?.blindCooldownMs===210000,'Vanish/Blind 300s → 210s');

    const canonical=T?.get('rogue_imp_sprint_backstab_16_12_23');
    const variant=T?.get('rogue_imp_sprint_backstab_17_12_22');
    add('Canonical blockers reduced',Array.isArray(canonical?.kernelBlockers)&&!canonical.kernelBlockers.some(x=>String(x).includes('weapon-skill'))&&!canonical.kernelBlockers.some(x=>String(x).includes('Elusiveness')),canonical?.kernelBlockers?.join(' · ')||'missing');
    add('Variant weapon-skill blocker resolved',Array.isArray(variant?.kernelBlockers)&&!variant.kernelBlockers.some(x=>String(x).includes('weapon-skill')),variant?.kernelBlockers?.join(' · ')||'missing');

    const p=D?.profiles?.rogue_subtlety_lvl60_pvp_bis_p6_daggers;
    add('Dagger profile carries weapon-skill audit',p?.weaponSkillAudit?.status==='VERIFIED',p?.weaponSkillAudit?.note||'missing');
  }catch(err){
    add('v0.19 QA runtime',false,String(err?.stack||err));
  }

  const passed=checks.filter(x=>x.pass).length,failed=checks.length-passed;
  const root=document.getElementById('qaReport');
  if(root){
    root.innerHTML=`<div class="duel-summary"><div class="${failed?'red':'winner'}">QA ${failed?'FAIL':'PASS'} · ${passed}/${checks.length}</div><div class="result-meta">Stats + gear + talent builds + Rogue dagger PvP mechanics + strict kernel gates.</div></div><div class="rule-grid" style="margin-top:10px">${checks.map(c=>`<div class="rule-card"><h3 class="${c.pass?'green':'red'}">${c.pass?'✓':'✗'} ${c.name}</h3><p>${String(c.details??'')}</p></div>`).join('')}</div>`;
  }
  window.WOW_QA={version:'0.19-qa',checks,passed,failed,pass:failed===0};
})();
