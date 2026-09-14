(()=>{
  const D=window.WOW_DATA,T=window.WOW_TALENTS;
  const base=window.WOW_QA||{checks:[]};
  const checks=[...(base.checks||[])];
  const add=(name,pass,details)=>checks.push({name,pass:!!pass,details});
  try{
    const n=D?.v021?.weaponNormalization||{};
    add('Dagger normalized speed',n.status==='VERIFIED'&&n.dagger===1.7,`expected 1.7 · actual ${n.dagger}`);
    add('1H normalized speed',n.oneHand===2.4,`expected 2.4 · actual ${n.oneHand}`);
    const m=D?.v021?.rogueDaggerAbilityMath||{};
    add('Backstab R9 normalized math',m.backstab?.spellId===11281&&m.backstab?.weaponPct===150&&m.backstab?.flatDamage===210&&m.backstab?.requiresBehind===true,m.backstab?.formula||'missing');
    add('Ambush R6 normalized math',m.ambush?.spellId===11269&&m.ambush?.weaponPct===250&&m.ambush?.flatDamage===290&&m.ambush?.requiresStealth===true,m.ambush?.formula||'missing');
    add('Ambush excludes Classic Lethality',String(m.ambush?.crit||'').includes('does not affect Ambush'),m.ambush?.crit||'missing');
    add('Improved Gouge 3/3 = 5.5s',m.gouge?.improvedGouge3DurationMs===5500&&m.gouge?.breaksOnDamage===true,'5500 ms + break on damage');
    const b=T?.get?.('rogue_imp_sprint_backstab_16_12_23');
    add('Dagger build blockers now policy/position only',Array.isArray(b?.kernelBlockers)&&b.kernelBlockers.some(x=>String(x).includes('behind-state'))&&b.kernelBlockers.some(x=>String(x).includes('policy parity')),b?.kernelBlockers?.join(' · ')||'missing');
  }catch(err){add('v0.21 QA runtime',false,String(err?.stack||err));}
  const passed=checks.filter(x=>x.pass).length,failed=checks.length-passed;
  const root=document.getElementById('qaReport');
  if(root)root.innerHTML=`<div class="duel-summary"><div class="${failed?'red':'winner'}">QA ${failed?'FAIL':'PASS'} · ${passed}/${checks.length}</div><div class="result-meta">Active talent runtime + Rogue dagger formulas + strict build/kernel gates.</div></div><div class="rule-grid" style="margin-top:10px">${checks.map(c=>`<div class="rule-card"><h3 class="${c.pass?'green':'red'}">${c.pass?'✓':'✗'} ${c.name}</h3><p>${String(c.details??'')}</p></div>`).join('')}</div>`;
  window.WOW_QA={version:'0.21-qa',checks,passed,failed,pass:failed===0};
})();