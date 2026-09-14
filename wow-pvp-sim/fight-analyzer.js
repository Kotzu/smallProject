(()=>{
  const pct=(v,max)=>max>0?Math.round(v/max*100):0;
  const has=(e,s)=>String(e?.text||'').includes(s);
  const count=(events,actor,kindOrText)=>events.filter(e=>e.actor===actor&&(e.kind===kindOrText||has(e,kindOrText))).length;
  const actorEvents=(events,actor)=>events.filter(e=>e.actor===actor);

  function classReport(className,won,result,events,maxHp){
    const mine=actorEvents(events,className);
    const enemy=actorEvents(events,className==='Rogue'?'Mage':'Rogue');
    const improvements=[];

    if(className==='Rogue'){
      const kick=count(events,'Rogue','Kick');
      const vanish=count(events,'Rogue','Vanish');
      const sprint=count(events,'Rogue','Sprint');
      const kidney=count(events,'Rogue','Kidney Shot');
      const frostCasts=enemy.filter(e=>has(e,'Frostbolt cast started')).length;
      const roots=enemy.filter(e=>has(e,'Frost Nova')||has(e,'rooted')).length;
      if(frostCasts>0&&kick===0) improvements.push('Prioritize Kick against exposed Frostbolt casts; this fight had cast windows but no logged Kick.');
      if(roots>0&&vanish===0) improvements.push('Preserve Vanish as a root-break/reopen tool when Frost Nova creates a losing distance window.');
      if(sprint===0) improvements.push('Use Sprint more deliberately after Blink/Nova to recover melee range instead of accepting free ranged pressure.');
      if(kidney===0) improvements.push('Build a cleaner Kidney Shot control window before committing the finisher when the target is not already stunned.');
      if(won&&pct(result.final.rogue.hp,maxHp.rogue)<30) improvements.push('The win was expensive: reduce damage traded during control gaps so the same line is safer across more RNG seeds.');
      if(!improvements.length) improvements.push('Current Subtlety priority handled this seed cleanly; next tuning target is timing efficiency rather than adding more actions.');
    }

    if(className==='Mage'){
      const blink=count(events,'Mage','Blink');
      const nova=count(events,'Mage','Frost Nova');
      const barrier=count(events,'Mage','Ice Barrier');
      const block=count(events,'Mage','Ice Block');
      const agm=count(events,'Mage','Arena Grand Master');
      const rogueControls=enemy.filter(e=>has(e,'Cheap Shot')||has(e,'Kidney Shot')).length;
      if(rogueControls>0&&blink===0) improvements.push('Protect Blink for the Rogue control chain; Cheap Shot/Kidney pressure occurred without a logged Blink escape.');
      if(nova===0) improvements.push('Create distance with Frost Nova before trying to stabilize; melee uptime is too valuable for Rogue.');
      if(barrier===0) improvements.push('Refresh Ice Barrier earlier when the absorb is gone instead of taking the next melee sequence directly on HP.');
      if(!won&&block===0) improvements.push('Use Ice Block before lethal burst when the next Rogue control/finisher sequence is otherwise unavoidable.');
      if(!won&&agm===0) improvements.push('Arena Grand Master was available as an additional survival buffer and should be evaluated before lethal range.');
      if(won&&pct(result.final.mage.mana,maxHp.mageMana)<15) improvements.push('The win is mana-fragile: reduce unnecessary shield refreshes/casts so the policy survives longer fights.');
      if(!improvements.length) improvements.push('Current Frost priority handled this seed cleanly; next tuning target is cooldown timing and mana efficiency.');
    }

    return improvements.slice(0,4);
  }

  function analyze(result,cfg,maxHp){
    const events=result?.timeline||[];
    const winner=result?.winner||'Unknown';
    const loser=winner==='Rogue'?'Mage':winner==='Mage'?'Rogue':'None';
    const winnerDamage=events.filter(e=>e.actor===winner&&(e.kind==='damage'||e.kind==='crit')).length;
    const winnerControl=events.filter(e=>e.actor===winner&&e.kind==='control').length;
    const loserMisses=events.filter(e=>e.actor===loser&&e.kind==='miss').length;
    const winnerProcs=events.filter(e=>e.actor===winner&&e.kind==='proc').length;
    const facts=[];
    const whyWinner=[];
    const whyLoser=[];

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
      if(winnerControl>0) whyWinner.push(`Controlul a creat ${winnerControl} ferestre în care adversarul nu a putut răspunde normal.`);
      if(winnerDamage>0) whyWinner.push(`Presiunea a fost convertită în ${winnerDamage} evenimente de damage/crit confirmate.`);
      if(winnerProcs>0) whyWinner.push(`${winnerProcs} proc-uri au contribuit la ritmul duelului.`);

      whyLoser.push(`${loser} a pierdut deoarece HP-ul a ajuns la 0 înainte să poată inversa presiunea.`);
      if(winnerControl>0) whyLoser.push(`A absorbit ${winnerControl} evenimente de control din partea lui ${winner}, reducând ferestrele de reacție.`);
      if(loserMisses>0) whyLoser.push(`${loserMisses} acțiuni au ratat / fost dodged / resisted, reducând eficiența acțiunilor consumate.`);

      if(loser==='Mage'){
        const rogueOpeners=events.filter(e=>e.actor==='Rogue'&&(has(e,'Cheap Shot')||has(e,'Kidney Shot'))).length;
        const blink=events.filter(e=>e.actor==='Mage'&&has(e,'Blink')).length;
        if(rogueOpeners>0) whyLoser.push(`Rogue a obținut ${rogueOpeners} ferestre Cheap Shot/Kidney; Mage a avut ${blink} Blink-uri logate pentru a rupe presiunea.`);
      }
      if(loser==='Rogue'){
        const mageKite=events.filter(e=>e.actor==='Mage'&&(has(e,'Blink')||has(e,'Frost Nova')||has(e,'Cone of Cold'))).length;
        if(mageKite>0) whyLoser.push(`Mage a generat ${mageKite} acțiuni de kite/control (Blink/Nova/Cone), ceea ce a redus melee uptime-ul Rogue-ului.`);
      }
    } else {
      whyWinner.push('Duelul nu are încă un câștigător normal; analiza trebuie tratată ca diagnostic de timeout/draw.');
      whyLoser.push('Nu există o clasă pierzătoare normală pentru acest rezultat.');
    }

    const winnerImprovements=winner==='Rogue'||winner==='Mage'?classReport(winner,true,result,events,maxHp):[];
    const loserImprovements=loser==='Rogue'||loser==='Mage'?classReport(loser,false,result,events,maxHp):[];

    return {
      winner,loser,duration:result.duration,
      whyWinner:whyWinner.slice(0,4),
      whyLoser:whyLoser.slice(0,4),
      winnerImprovements,
      loserImprovements,
      facts,
      policyTargets:{
        winner:winner==='Rogue'?'combat/Rogue/ClassCombat.lua':winner==='Mage'?'combat/Mage/ClassCombat.lua':'—',
        loser:loser==='Rogue'?'combat/Rogue/ClassCombat.lua':loser==='Mage'?'combat/Mage/ClassCombat.lua':'—'
      }
    };
  }

  window.WOW_FIGHT_ANALYZER={analyze,version:'0.15'};
})();
