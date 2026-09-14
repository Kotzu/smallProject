(()=>{
  const D=window.WOW_DATA,T=window.WOW_TALENTS,E=window.WOW_ENGINE;
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
  }catch(err){add('v0.22 QA runtime',false,String(err?.stack||err));}

  const passed=checks.filter(x=>x.pass).length,failed=checks.length-passed;
  const root=document.getElementById('qaReport');
  if(root)root.innerHTML=`<div class="duel-summary"><div class="${failed?'red':'winner'}">QA ${failed?'FAIL':'PASS'} · ${passed}/${checks.length}</div><div class="result-meta">Talent runtime + Rogue dagger formulas + verified CMaNGOS rear arc + strict kernel gates.</div></div><div class="rule-grid" style="margin-top:10px">${checks.map(c=>`<div class="rule-card"><h3 class="${c.pass?'green':'red'}">${c.pass?'✓':'✗'} ${c.name}</h3><p>${String(c.details??'')}</p></div>`).join('')}</div>`;
  window.WOW_QA={version:'0.22-qa',checks,passed,failed,pass:failed===0};

  const hero=document.querySelector('.hero p');
  if(hero)hero.textContent='v0.22 · talent runtime active · verified Rogue rear arc · MOVE_BEHIND policy · post-fight coaching';
  const combatNote=document.querySelector('#combat .note');
  if(combatNote)combatNote.textContent='CB/Hemo rămâne kernelul calibrat. Pentru dagger Rogue, rear-arc-ul de 180° este verificat din CMaNGOS, iar ClassCombat.lua emite acum MOVE_BEHIND. Mai lipsesc execuția web a MOVE_BEHIND/Backstab/Ambush/Gouge, combat-reach radius parity și Lua↔web policy parity înainte să deblocăm build-ul.';
})();