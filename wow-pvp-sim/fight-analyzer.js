(()=>{
  const T=window.WOW_TALENTS;
  const pct=(v,max)=>max>0?Math.round(v/max*100):0;
  const has=(e,s)=>String(e?.text||'').includes(s);
  const count=(events,actor,kindOrText)=>events.filter(e=>e.actor===actor&&(e.kind===kindOrText||has(e,kindOrText))).length;
  const actorEvents=(events,actor)=>events.filter(e=>e.actor===actor);

  function buildFor(className,result,cfg){
    const side=className==='Rogue'?'a':'b';
    const id=result?.builds?.[side]?.id||cfg?.[side]?.build||T?.defaultBuild(cfg?.[side]?.class,cfg?.[side]?.spec);
    return {id,build:T?.get(id)||null};
  }

  function classReport(className,won,result,events,maxHp,buildInfo){
    const enemy=actorEvents(events,className==='Rogue'?'Mage':'Rogue');
    const improvements=[];
    const build=buildInfo?.build;

    if(className==='Rogue'){
      const kick=count(events,'Rogue','Kick');
      const vanish=count(events,'Rogue','Vanish');
      const sprint=count(events,'Rogue','Sprint');
      const kidney=count(events,'Rogue','Kidney Shot');
      const coldBlood=count(events,'Rogue','Cold Blood');
      const frostCasts=enemy.filter(e=>has(e,'Frostbolt cast started')).length;
      const roots=enemy.filter(e=>has(e,'Frost Nova')||has(e,'rooted')).length;
      if(frostCasts>0&&kick===0) improvements.push('Prioritize Kick against exposed Frostbolt casts; the selected build has enough control tools to deny free casts.');
      if(roots>0&&vanish===0) improvements.push('Preserve Vanish as a root-break/reopen tool when Frost Nova creates a losing distance window.');
      if(sprint===0) improvements.push('Use Sprint more deliberately after Blink/Nova to recover melee range instead of accepting free ranged pressure.');
      if(kidney===0) improvements.push('Build a cleaner Kidney Shot control window before committing the finisher when the target is not already stunned.');
      if(build?.modifiers?.coldBlood&&coldBlood===0) improvements.push(`${build.name} includes Cold Blood, but this fight logged no Cold Blood use; review finisher timing in Rogue ClassCombat.lua.`);
      if(won&&pct(result.final.rogue.hp,maxHp.rogue)<30) improvements.push('The win was expensive: reduce damage traded during control gaps so the same line is safer across more RNG seeds.');
      if(!improvements.length) improvements.push(`Current ${build?.name||'Rogue'} priority handled this seed cleanly; next tuning target is timing efficiency rather than adding more actions.`);
    }

    if(className==='Mage'){
      const blink=count(events,'Mage','Blink');
      const nova=count(events,'Mage','Frost Nova');
      const barrier=count(events,'Mage','Ice Barrier');
      const block=count(events,'Mage','Ice Block');
      const coldSnap=count(events,'Mage','Cold Snap');
      const agm=count(events,'Mage','Arena Grand Master');
      const rogueControls=enemy.filter(e=>has(e,'Cheap Shot')||has(e,'Kidney Shot')).length;
      if(rogueControls>0&&blink===0) improvements.push('Protect Blink for the Rogue control chain; control pressure occurred without a logged Blink escape.');
      if(nova===0) improvements.push('Create distance with Frost Nova before trying to stabilize; melee uptime is too valuable for Rogue.');
      if(barrier===0) improvements.push('Refresh Ice Barrier earlier when the absorb is gone instead of taking the next melee sequence directly on HP.');
      if(!won&&build?.modifiers?.iceBlock&&block===0) improvements.push(`${build.name} includes Ice Block, but it was not used before the losing sequence.`);
      if(!won&&build?.modifiers?.coldSnap&&coldSnap===0) improvements.push(`${build.name} includes Cold Snap; evaluate whether an earlier reset of Frost Nova / Barrier / Ice Block would create a second defensive cycle.`);
      if(!won&&agm===0) improvements.push('Arena Grand Master was available as an additional survival buffer and should be evaluated before lethal range.');
      if(won&&pct(result.final.mage.mana,maxHp.mageMana)<15) improvements.push('The win is mana-fragile: reduce unnecessary shield refreshes/casts so the policy survives longer fights.');
      if(!improvements.length) improvements.push(`Current ${build?.name||'Frost'} priority handled this seed cleanly; next tuning target is cooldown timing and mana efficiency.`);
    }

    return improvements.slice(0,5);
  }

  function analyze(result,cfg,maxHp){
    const events=result?.timeline||[];
    const winner=result?.winner||'Unknown';
    const loser=winner==='Rogue'?'Mage':winner==='Mage'?'Rogue':'None';
    const winnerDamage=events.filter(e=>e.actor===winner&&(e.kind==='damage'||e.kind==='crit')).length;
    const winnerControl=events.filter(e=>e.actor===winner&&e.kind==='control').length;
    const loserMisses=events.filter(e=>e.actor===loser&&e.kind==='miss').length;
    const winnerProcs=events.filter(e=>e.actor===winner&&e.kind==='proc').length;
    const winnerBuild=winner==='Rogue'||winner==='Mage'?buildFor(winner,result,cfg):null;
    const loserBuild=loser==='Rogue'||loser==='Mage'?buildFor(loser,result,cfg):null;
    const facts=[];
    const whyWinner=[];
    const whyLoser=[];

    if(winnerBuild?.build)facts.push(`${winner} build: ${winnerBuild.build.name} ${winnerBuild.build.points}.`);
    if(loserBuild?.build)facts.push(`${loser} build: ${loserBuild.build.name} ${loserBuild.build.points}.`);
    if(winner==='Rogue'){
      facts.push(`Rogue final: ${result.final.rogue.hp} HP, ${result.final.rogue.energy} Energy, ${result.final.rogue.combo} CP.`);
      facts.push(`Mage final: ${result.final.mage.hp} HP, ${result.final.mage.mana} Mana.`);
    } else if(winner==='Mage'){
      facts.push(`Mage final: ${result.final.mage.hp} HP, ${result.final.mage.mana} Mana.`);
      facts.push(`Rogue final: ${result.final.rogue.hp} HP, ${result.final.rogue.energy} Energy.`);
    }
    facts.push(`${winnerDamage} damage events, ${winnerControl} control events și ${winnerProcs} proc events de la câștigător.`);
    if(loser!=='None') facts.push(`${loserMisses} miss/dodge/resist events pentru clasa pierzătoare.`);

    if(winner!=='Timeout'&&winner!=='Draw'){
      whyWinner.push(`${winner} a terminat duelul la ${result.duration}s și a dus adversarul la 0 HP.`);
      if(winnerBuild?.build)whyWinner.push(`A câștigat folosind profilul de talente ${winnerBuild.build.name} (${winnerBuild.build.points}); analiza și recomandările sunt evaluate în limitele acestui build.`);
      if(winnerControl>0) whyWinner.push(`Controlul a creat ${winnerControl} ferestre în care adversarul nu a putut răspunde normal.`);
      if(winnerDamage>0) whyWinner.push(`Presiunea a fost convertită în ${winnerDamage} evenimente de damage/crit confirmate.`);
      if(winnerProcs>0) whyWinner.push(`${winnerProcs} proc-uri au contribuit la ritmul duelului.`);

      whyLoser.push(`${loser} a pierdut deoarece HP-ul a ajuns la 0 înainte să poată inversa presiunea.`);
      if(loserBuild?.build)whyLoser.push(`Build-ul ${loserBuild.build.name} (${loserBuild.build.points}) definește ce instrumente avea disponibile; nu recomandăm abilități pe care build-ul nu le deține.`);
      if(winnerControl>0) whyLoser.push(`A absorbit ${winnerControl} evenimente de control din partea lui ${winner}, reducând ferestrele de reacție.`);
      if(loserMisses>0) whyLoser.push(`${loserMisses} acțiuni au ratat / fost dodged / resisted, reducând eficiența acțiunilor consumate.`);
    } else {
      whyWinner.push('Duelul nu are încă un câștigător normal; analiza trebuie tratată ca diagnostic de timeout/draw.');
      whyLoser.push('Nu există o clasă pierzătoare normală pentru acest rezultat.');
    }

    const winnerImprovements=winner==='Rogue'||winner==='Mage'?classReport(winner,true,result,events,maxHp,winnerBuild):[];
    const loserImprovements=loser==='Rogue'||loser==='Mage'?classReport(loser,false,result,events,maxHp,loserBuild):[];

    return {
      winner,loser,duration:result.duration,winnerBuild,loserBuild,
      whyWinner:whyWinner.slice(0,5),
      whyLoser:whyLoser.slice(0,5),
      winnerImprovements,
      loserImprovements,
      facts,
      policyTargets:{
        winner:winner==='Rogue'?'combat/Rogue/ClassCombat.lua':winner==='Mage'?'combat/Mage/ClassCombat.lua':'—',
        loser:loser==='Rogue'?'combat/Rogue/ClassCombat.lua':loser==='Mage'?'combat/Mage/ClassCombat.lua':'—'
      }
    };
  }

  window.WOW_FIGHT_ANALYZER={analyze,version:'0.16'};
})();
