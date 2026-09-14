(()=>{
  const T=window.WOW_TALENTS;
  const $=id=>document.getElementById(id);
  if(!T)return;

  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  function playerState(p){
    return {
      class:$(p+'c')?.value,
      spec:$(p+'s')?.value,
      race:$(p+'r')?.value,
      gear:$(p+'g')?.value,
      build:$(p+'build')?.value||null
    };
  }

  function refreshSelect(p){
    const el=$(p+'build');if(!el)return;
    const s=playerState(p),ids=T.idsFor(s.class,s.spec),previous=el.value;
    if(!ids.length){
      el.innerHTML='<option value="">LOCKED — no verified build</option>';
      el.disabled=true;
    } else {
      el.disabled=false;
      el.innerHTML=ids.map(id=>{const b=T.get(id);return `<option value="${esc(id)}">${esc(b.name)} · ${esc(b.points)}</option>`;}).join('');
      el.value=ids.includes(previous)?previous:ids[0];
    }
    renderPlayer(p);
  }

  function modifierText(b){
    if(!b)return '';
    const m=b.modifiers||{};
    const bits=[];
    if(m.meleeCritPct!=null)bits.push(`+${m.meleeCritPct}% melee crit`);
    if(m.eviscerateDamagePct!=null)bits.push(`Eviscerate +${m.eviscerateDamagePct}%`);
    if(m.frostFireHitPct!=null)bits.push(`Frost/Fire hit +${m.frostFireHitPct}%`);
    if(m.frostDamagePct!=null)bits.push(`Frost damage +${m.frostDamagePct}%`);
    if(m.frostboltCastMs!=null)bits.push(`Frostbolt ${(m.frostboltCastMs/1000).toFixed(1)}s`);
    return bits.join(' · ');
  }

  function renderPlayer(p){
    const root=$(p+'TalentPanel');if(!root)return;
    const s=playerState(p),audit=T.auditSelection(s);
    if(!audit.pass){
      root.innerHTML=`<div class="talent-locked"><b>TALENT BUILD: ${esc(audit.status)}</b><span>${esc(audit.reason)}</span></div>`;
      return;
    }
    const b=audit.build;
    root.innerHTML=`
      <div class="talent-head"><div><h3>${esc(b.name)}</h3><span>${esc(b.class)} ${esc(b.spec)} · ${esc(b.points)} · ${T.pointTotal(b.points)} points</span></div><div class="audit-badge pass">BUILD AUDIT: PASS</div></div>
      <div class="talent-role">${esc(b.role||'PvP build')}</div>
      <div class="talent-effects">${(b.combatTalents||[]).map(t=>`<div><b>${esc(t.name)} <span>${esc(t.rank)}</span></b><p>${esc(t.effect)}</p></div>`).join('')}</div>
      <div class="talent-summary"><b>Active kernel modifiers:</b> ${esc(modifierText(b)||'verified by build registry')}</div>
      <div class="talent-links"><a href="${esc(b.calculatorUrl)}" target="_blank" rel="noreferrer">Open talent calculator</a><code>${esc(b.calculator||'')}</code></div>`;

    const fightLabel=p==='a'?$('fightRogueBuild'):$('fightMageBuild');
    if(fightLabel)fightLabel.textContent=`${b.name} · ${b.points}`;
  }

  function refreshAll(){refreshSelect('a');refreshSelect('b');}

  ['ac','as','ar','ag'].forEach(id=>$(id)?.addEventListener('change',()=>setTimeout(()=>refreshSelect('a'),0)));
  ['bc','bs','br','bg'].forEach(id=>$(id)?.addEventListener('change',()=>setTimeout(()=>refreshSelect('b'),0)));
  $('abuild')?.addEventListener('change',()=>renderPlayer('a'));
  $('bbuild')?.addEventListener('change',()=>renderPlayer('b'));

  setTimeout(refreshAll,0);
  window.WOW_TALENT_UI={refreshAll,renderPlayer,version:'0.16'};
})();
