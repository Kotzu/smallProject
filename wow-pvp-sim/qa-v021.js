(()=>{
  const D=window.WOW_DATA,T=window.WOW_TALENTS,E=window.WOW_ENGINE,F=window.WOW_FOREVER_TALENTS;
  const base=window.WOW_QA||{checks:[]};
  const checks=[...(base.checks||[])];
  const add=(name,pass,details)=>checks.push({name,pass:!!pass,details});
  const near=(a,b,eps=1e-8)=>Math.abs(Number(a)-Number(b))<=eps;
  try{
    const n=D?.v021?.weaponNormalization||{};
    add('Dagger normalized speed',n.status==='VERIFIED'&&n.dagger===1.7,`expected 1.7 · actual ${n.dagger}`);
    add('1H normalized speed',n.oneHand===2.4,`expected 2.4 · actual ${n.oneHand}`);
    const m=D?.v021?.rogueDaggerAbilityMath||{};
    add('Backstab R9 normalized math',m.backstab?.spellId===11281&&m.backstab?.weaponPct===150&&m.backstab?.flatDamage===210&&m.backstab?.requiresBehind===true,m.backstab?.formula||'missing');
    add('Ambush R6 normalized math',m.ambush?.spellId===11269&&m.ambush?.weaponPct===250&&m.ambush?.flatDamage===290&&m.ambush?.requiresStealth===true,m.ambush?.formula||'missing');
    add('Ambush excludes Classic Lethality',String(m.ambush?.crit||'').includes('does not affect Ambush'),m.ambush?.crit||'missing');
    add('Improved Gouge 3/3 = 5.5s',m.gouge?.improvedGouge3DurationMs===5500&&m.gouge?.breaksOnDamage===true,'5500 ms + break on damage');

    const pos=D?.v022?.positioning||{};
    add('Classic rear arc source',pos.status==='REAR_ARC_VERIFIED_RUNTIME_PARTIAL'&&pos.backArcDegrees===180,`${pos.backArcDegrees}° · ${pos.source||'missing source'}`);
    const target={x:0,y:0,o:0};
    add('Rear-arc test: attacker west is behind',E?.isInBack?.(target,{x:-3,y:0,o:0},5,Math.PI)===true,'target faces east; attacker at (-3, 0)');
    add('Rear-arc test: attacker east is front',E?.isInBack?.(target,{x:3,y:0,o:Math.PI},5,Math.PI)===false,'target faces east; attacker at (+3, 0)');
    add('Rear-arc distance gate',E?.isInBack?.(target,{x:-6,y:0,o:0},5,Math.PI)===false,'6 yd fails 5 yd positional range');
    const behindPoint=E?.pointBehind?.(target,2)||{};
    add('MOVE_BEHIND destination math',near(behindPoint.x,-2)&&near(behindPoint.y,0),`expected (-2,0) · actual (${behindPoint.x},${behindPoint.y})`);

    const canonical=T?.get?.('rogue_imp_sprint_backstab_16_12_23');
    add('Canonical dagger blockers narrowed',Array.isArray(canonical?.kernelBlockers)&&canonical.kernelBlockers.some(x=>String(x).includes('MOVE_BEHIND'))&&canonical.kernelBlockers.some(x=>String(x).includes('Initiative'))&&!canonical.kernelBlockers.some(x=>String(x).includes('behind-state model')),canonical?.kernelBlockers?.join(' · ')||'missing');
    const variant=T?.get?.('rogue_imp_sprint_backstab_17_12_22');
    add('17/12/22 has no false Initiative blocker',Array.isArray(variant?.kernelBlockers)&&!variant.kernelBlockers.some(x=>String(x).includes('Initiative')),variant?.kernelBlockers?.join(' · ')||'missing');

    const blind=D?.v027?.rogueBlind||{};
    add('Blind exact static data registered',blind.spellId===2094&&blind.cost===30&&blind.range===10&&blind.durationMs===10000&&blind.cooldownMs===300000&&blind.school==='Nature'&&blind.breaksOnDamage===true,`${blind.status||'missing'} · ${blind.blocker||''}`);
    add('Blind stays strict-locked on heartbeat uncertainty',String(blind.status||'').includes('LOCKED_HEARTBEAT'),blind.blocker||'missing blocker');
    const insignia=D?.v027?.mageInsignia18859||{};
    add('Mage Insignia 18859 action registered',insignia.itemId===18859&&insignia.cooldownMs===300000&&insignia.removes?.includes('Slowing'),`${insignia.status||'missing'} · ${insignia.relevantCurrentMatchup||''}`);

    add('Forever snapshot node total',F?.totalNodes?.()===470,`expected 470 · actual ${F?.totalNodes?.()}`);
    add('Forever Rogue tree structure',F?.classTotal?.('Rogue')===53&&F?.classInfo?.('Rogue')?.trees?.Assassination===17&&F?.classInfo?.('Rogue')?.trees?.Combat===17&&F?.classInfo?.('Rogue')?.trees?.Subtlety===19,'17 / 17 / 19 = 53');
    add('Forever Mage tree structure',F?.classTotal?.('Mage')===54&&F?.classInfo?.('Mage')?.trees?.Arcane===18&&F?.classInfo?.('Mage')?.trees?.Fire===17&&F?.classInfo?.('Mage')?.trees?.Frost===19,'18 / 17 / 19 = 54');
    add('Forever Rogue names imported',F?.tree?.('Rogue','Assassination')?.length===17&&F?.tree?.('Rogue','Combat')?.length===17&&F?.tree?.('Rogue','Subtlety')?.length===19,'53/53 Rogue nodes named in local pre-beta snapshot');
    add('Forever Mage transcript coverage explicit',F?.tree?.('Mage','Arcane')?.length===18&&F?.tree?.('Mage','Fire')?.length===17&&F?.tree?.('Mage','Frost')?.length===19&&F?.coverage?.mageIncompleteTalentNames===2,'54 Mage nodes structurally mapped; 2 Fire names intentionally incomplete');
    add('Classic builds never relabeled Forever',Object.values(T?.library||{}).every(b=>b?.dataset!=='Forever'), 'all runnable/known builds remain explicitly ClassicEra');
    const foreverGate=window.WOW_DUEL?.canRun?.({ruleset:'forever',a:{class:'Rogue',spec:'Subtlety',race:'Undead',gear:'Level 60 PvP BiS',build:'rogue_cb_hemo_21_3_27'},b:{class:'Mage',spec:'Frost',race:'Gnome',gear:'Level 60 PvP BiS',build:'mage_deep_frost_17_0_34'}});
    add('Forever strict fight gate',foreverGate?.ready===false&&foreverGate?.missing?.some(x=>String(x).includes('Forever strict gate')),foreverGate?.missing?.join(' · ')||'missing gate');
  }catch(err){add('v0.28 QA runtime',false,String(err?.stack||err));}

  const passed=checks.filter(x=>x.pass).length,failed=checks.length-passed;
  const root=document.getElementById('qaReport');
  if(root)root.innerHTML=`<div class="duel-summary"><div class="${failed?'red':'winner'}">QA ${failed?'FAIL':'PASS'} · ${passed}/${checks.length}</div><div class="result-meta">Classic combat parity + Rogue policy evidence + current Forever pre-beta talent structure + strict ruleset separation.</div></div><div class="rule-grid" style="margin-top:10px">${checks.map(c=>`<div class="rule-card"><h3 class="${c.pass?'green':'red'}">${c.pass?'✓':'✗'} ${c.name}</h3><p>${String(c.details??'')}</p></div>`).join('')}</div>`;
  window.WOW_QA={version:'0.28-qa',checks,passed,failed,pass:failed===0};
})();