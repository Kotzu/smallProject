(()=>{
  const $=id=>document.getElementById(id);
  const DUEL=window.WOW_DUEL,D=window.WOW_DATA,CE=window.WOW_CHARACTER_ENGINE,CD=window.WOW_CHARACTER_DATA,A=window.WOW_ARMORY;
  let result=null,index=0,timer=null,speed=2;
  const cfg=()=>({
    a:{class:$('ac').value,spec:$('as').value,race:$('ar').value,gear:$('ag').value},
    b:{class:$('bc').value,spec:$('bs').value,race:$('br').value,gear:$('bg').value}
  });
  function maxHp(){
    const P=D.profiles.rogue_subtlety_lvl60_pvp_bis_p6_baseline;
    const r=CE.rogue60Baseline(CD.level60.undeadRogue,P);
    return {rogue:r.health,mage:D.pvpProfiles.mage_frost_gnome_p6_core.stats.health};
  }
  function setBar(id,value,max){const el=$(id);if(!el)return;const pct=Math.max(0,Math.min(100,value/max*100));el.style.width=pct+'%';}
  function setText(id,v){const el=$(id);if(el)el.textContent=v;}
  function switchTab(id){document.querySelectorAll('.tabs button').forEach(x=>x.classList.toggle('active',x.dataset.tab===id));document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x.id===id));}
  function resetView(){
    stop();index=0;const m=maxHp();setBar('fightRogueHpBar',m.rogue,m.rogue);setBar('fightMageHpBar',m.mage,m.mage);
    setText('fightRogueHp',m.rogue+' / '+m.rogue);setText('fightMageHp',m.mage+' / '+m.mage);
    setText('fightRogueRes','100 Energy');setText('fightMageRes',D.pvpProfiles.mage_frost_gnome_p6_core.stats.mana+' Mana');
    setText('fightTime','0.0s');setText('fightAction','Ready');$('fightLiveLog').innerHTML='';
  }
  function parseState(e){
    const m=maxHp();
    let x=e.text.match(/→ Rogue (\d+) HP/);if(x){setBar('fightRogueHpBar',+x[1],m.rogue);setText('fightRogueHp',x[1]+' / '+m.rogue);}
    x=e.text.match(/→ Mage (\d+) HP/);if(x){setBar('fightMageHpBar',+x[1],m.mage);setText('fightMageHp',x[1]+' / '+m.mage);}
    setText('fightTime',e.t.toFixed(1)+'s');setText('fightAction',e.actor+' · '+e.text);
  }
  function appendEvent(e){
    const row=document.createElement('div');row.className='fight-log-row '+e.kind;
    row.innerHTML=`<span>${e.t.toFixed(1)}s</span><b>${e.actor}</b><em>${e.text}</em>`;
    const root=$('fightLiveLog');root.appendChild(row);root.scrollTop=root.scrollHeight;
  }
  function step(){
    if(!result||index>=result.timeline.length){stop();if(result){setText('fightAction','WINNER: '+result.winner);setText('fightRogueRes',result.final.rogue.energy+' Energy');setText('fightMageRes',result.final.mage.mana+' Mana');}return;}
    const e=result.timeline[index++];parseState(e);appendEvent(e);
  }
  function play(){stop();timer=setInterval(step,Math.max(80,420/speed));}
  function stop(){if(timer){clearInterval(timer);timer=null;}}
  function startFight(autoPlay=true){
    const c=cfg(),ga=DUEL.canRun(c),aa=A.audit(c.a),ab=A.audit(c.b);
    if(!ga.ready||!aa.pass||!ab.pass){$('fightError').textContent='Fight blocat: '+[...(ga.missing||[]),!aa.pass?'Player A stat audit':'',!ab.pass?'Player B stat audit':''].filter(Boolean).join(' · ');return;}
    $('fightError').textContent='';
    const seed=(Number($('duelCode').value)||1337)>>>0;result=DUEL.run(seed,c);resetView();switchTab('fight');
    if(result.error){$('fightError').textContent=result.error+': '+result.missing.join(', ');return;}
    setText('fightAction','Duel #'+seed+' loaded · '+result.timeline.length+' events');
    if(autoPlay)play();
  }
  $('fightRunBtn')?.addEventListener('click',()=>startFight(true));
  $('fightPlayBtn')?.addEventListener('click',play);
  $('fightPauseBtn')?.addEventListener('click',stop);
  $('fightStepBtn')?.addEventListener('click',()=>{stop();step();});
  $('fightResetBtn')?.addEventListener('click',resetView);
  $('fightSpeed')?.addEventListener('change',e=>{speed=Number(e.target.value)||2;if(timer)play();});
  $('runBtn')?.addEventListener('click',()=>setTimeout(()=>startFight(true),0));
  resetView();
  window.WOW_FIGHT_UI={startFight,version:'0.14'};
})();
