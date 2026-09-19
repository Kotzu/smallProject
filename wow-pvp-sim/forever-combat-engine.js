(function(){
  const DATA=()=>window.WOW_FOREVER_COMBAT_DATA;
  const POL=()=>window.WOW_FOREVER_COMBAT_POLICIES;
  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  const round=v=>Math.round(v);
  const pct=(v,max)=>max>0?v/max*100:0;

  function rng(seed){
    let a=(seed>>>0)||0x6d2b79f5;
    return function(){a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return ((t^t>>>14)>>>0)/4294967296;};
  }
  function rankMap(build){
    const out={};
    for(const t of build?.selectedTalents||[])out[t.name]=Number(t.rank||0);
    return out;
  }
  function supported(config){
    const a=config?.a,b=config?.b,issues=[];
    if(a?.class!=='Rogue'||a?.spec!=='Subtlety'||a?.race!=='Undead')issues.push('Player A must be Undead Rogue Subtlety for the current reference matchup');
    if(b?.class!=='Mage'||b?.spec!=='Frost'||b?.race!=='Gnome')issues.push('Player B must be Gnome Mage Frost for the current reference matchup');
    if(Number(a?.build?.points)!==51)issues.push('Player A requires a valid 51-point Forever build');
    if(Number(b?.build?.points)!==51)issues.push('Player B requires a valid 51-point Forever build');
    const AD=window.WOW_FOREVER_ARMORY_DATA;
    if(!AD?.audit?.(a)?.gearIdentityPass)issues.push('Player A Forever gear profile is not verified');
    if(!AD?.audit?.(b)?.gearIdentityPass)issues.push('Player B Forever gear profile is not verified');
    return{ready:issues.length===0,issues,status:'REFERENCE_MODEL',certifiedParity:false};
  }

  function initState(seed,config,opts={}){
    const d=DATA(),s=d.scenario,ra=d.referenceProfiles.Rogue,ma=d.referenceProfiles.Mage;
    const R=rankMap(config.a.build),M=rankMap(config.b.build);
    const rand=rng(seed);
    return{
      seed:seed>>>0,nowMs:0,range:s.startRange,maxMs:s.maxDurationMs,tickMs:s.tickMs,rand,compact:opts.compact===true,
      timeline:[],decisionTrace:[],events:[],
      memory:{Rogue:{fakeCastRestarts:0,lastCastSpell:null,lastCancelMs:0},Mage:{fakeCasts:0,blinkObserved:false}},
      rogue:{
        name:'Rogue',hp:ra.health,maxHp:ra.health,energy:ra.maxEnergy,maxEnergy:ra.maxEnergy,energyRegenPerSec:ra.energyRegenPerSec,
        ap:ra.attackPower,critPct:ra.critPct,hitPct:ra.hitPct,armor:ra.armor,
        mh:{...ra.mh},oh:{...ra.oh},talents:R,
        comboPoints:0,premedCp:0,premedExpire:0,stealthed:s.rogueStartsStealthed,
        gcdUntil:0,cooldowns:{},stunUntil:0,rootUntil:0,disorientUntil:0,incapUntil:0,slowUntil:0,slowPct:0,
        sprintUntil:0,coldBloodActive:false,nextMhSwing:0,nextOhSwing:0,dead:false
      },
      mage:{
        name:'Mage',hp:ma.health,maxHp:ma.health,mana:ma.mana,maxMana:ma.mana,baseMana:ma.baseMana,
        spellPower:ma.spellPower,frostSpellPower:ma.frostSpellPower,critPct:ma.spellCritPct,hitPct:ma.spellHitPct,spirit:ma.spirit||0,
        armor:ma.armor+(s.mageStartsIceArmor?560:0),dodgePct:ma.dodgePct,talents:M,
        gcdUntil:0,cooldowns:{},stunUntil:0,rootUntil:0,disorientUntil:0,incapUntil:0,slowUntil:0,slowPct:0,
        iceBarrierAbsorb:s.mageStartsIceBarrier?DATA().abilities.Mage['Ice Barrier'].absorb:0,manaShieldAbsorb:0,iceBlockUntil:0,
        cast:null,schoolLockUntil:{Frost:0,Fire:0,Arcane:0},fingersOfFrostCharges:0,fingersOfFrostUntil:0,clearcasting:false,lastManaSpendMs:-999999,nextManaRegenTickMs:2000,
        dead:false
      },
      metrics:{
        rogue:{damage:0,absorbed:0,kicks:0,kidneys:0,holds:0,resets:0,energyStarveAvoided:0},
        mage:{damage:0,absorbed:0,blinks:0,novas:0,fakeCasts:0,iceBlocks:0},
        provisionalRulesUsed:new Set()
      },
      config
    };
  }

  function log(st,actor,kind,text,trace){
    const entry={t:st.nowMs/1000,tMs:st.nowMs,actor,kind,text,
      state:{rogueHp:round(st.rogue.hp),rogueEnergy:round(st.rogue.energy),rogueCp:st.rogue.comboPoints,mageHp:round(st.mage.hp),mageMana:round(st.mage.mana),range:+st.range.toFixed(1)}};
    if(trace)entry.trace=trace;
    if(!st.compact)st.timeline.push(entry);return entry;
  }
  function cdRemain(st,a,name){return Math.max(0,(a.cooldowns[name]||0)-st.nowMs);}
  function isReady(st,a,name){return cdRemain(st,a,name)<=0;}
  function setCd(st,a,name,ms){if(ms>0)a.cooldowns[name]=st.nowMs+ms;}
  function controlled(st,a){return st.nowMs<a.stunUntil||st.nowMs<a.disorientUntil||st.nowMs<a.incapUntil;}
  function rooted(st,a){return st.nowMs<a.rootUntil;}
  function slowed(st,a){return st.nowMs<a.slowUntil;}
  function roll(st,min,max){return min+(max-min)*st.rand();}
  function chance(st,p){return st.rand()*100<p;}
  function physicalReduction(armor,level=60){
    const x=.1*Math.max(0,armor)/(8.5*level+40);
    return clamp(x/(1+x),0,.75);
  }
  function meleeRange(){return Number(DATA().inherited.effectiveMeleeRangeYards?.value||5);}
  function armorAgainstRogue(st){
    const ignore=(st.rogue.talents['Serrated Blades']||0)*3/100;
    return st.mage.armor*(1-ignore);
  }
  function weaponDamage(st,hand){
    const w=st.rogue[hand];return roll(st,w.min,w.max)+(st.rogue.ap/14)*w.speed;
  }
  function rogueDamageMods(st,{builder=false,kidneyBonus=true}={}){
    let m=1;
    m*=1+(st.rogue.talents.Murder||0)*.02;
    if(kidneyBonus&&st.nowMs<st.mage.stunUntil)m*=1+(st.rogue.talents['Improved Kidney Shot']||0)*.05;
    return m;
  }
  function damage(st,target,amount,{actor,school='Physical',physical=false,kind='damage',breakControl=true}={}){
    if(amount<=0)return{dealt:0,absorbed:0};
    if(target===st.mage&&st.nowMs<st.mage.iceBlockUntil)return{dealt:0,absorbed:amount,immune:true};
    let remaining=amount,absorbed=0;
    if(target===st.mage&&st.mage.iceBarrierAbsorb>0){
      const x=Math.min(remaining,st.mage.iceBarrierAbsorb);st.mage.iceBarrierAbsorb-=x;remaining-=x;absorbed+=x;
      if(st.mage.iceBarrierAbsorb<=.01)log(st,'Mage','aura','Ice Barrier breaks');
    }
    if(target===st.mage&&physical&&remaining>0&&st.mage.manaShieldAbsorb>0&&st.mage.mana>0){
      const maxByMana=st.mage.mana/2,x=Math.min(remaining,st.mage.manaShieldAbsorb,maxByMana);
      st.mage.manaShieldAbsorb-=x;st.mage.mana-=x*2;remaining-=x;absorbed+=x;
      if(st.mage.manaShieldAbsorb<=.01)log(st,'Mage','aura','Mana Shield breaks');
    }
    if(remaining>0){
      target.hp=Math.max(0,target.hp-remaining);
      if(breakControl){
        if(st.nowMs<target.disorientUntil){target.disorientUntil=0;log(st,target.name,'control','Disorient broken by damage');}
        if(st.nowMs<target.incapUntil){target.incapUntil=0;log(st,target.name,'control','Incapacitate broken by damage');}
      }
      if(actor==='Rogue')st.metrics.rogue.damage+=remaining;else st.metrics.mage.damage+=remaining;
    }
    if(actor==='Rogue')st.metrics.mage.absorbed+=absorbed;else st.metrics.rogue.absorbed+=absorbed;
    if(target.hp<=0)target.dead=true;
    return{dealt:remaining,absorbed};
  }
  function specialLands(st){
    st.metrics.provisionalRulesUsed.add('melee special hit/dodge table');
    const miss=Math.max(0,5-st.rogue.hitPct),dodge=st.mage.dodgePct||0;
    const r=st.rand()*100;
    if(r<miss)return'miss';if(r<miss+dodge)return'dodge';return'hit';
  }
  function whiteLands(st){
    st.metrics.provisionalRulesUsed.add('dual-wield white hit table');
    const miss=Math.max(0,24-st.rogue.hitPct),dodge=st.mage.dodgePct||0,r=st.rand()*100;
    if(r<miss)return'miss';if(r<miss+dodge)return'dodge';return'hit';
  }
  function spellLands(st){
    st.metrics.provisionalRulesUsed.add('same-level spell miss floor');
    const miss=Math.max(1,4-st.mage.hitPct);return chance(st,100-miss);
  }
  function procPoison(st,hand){
    const poison=hand==='mh'?'Crippling Poison':'Mind-numbing Poison',p=DATA().abilities.Rogue[poison];
    if(!chance(st,p.procPct))return;
    if(poison==='Crippling Poison'){
      st.mage.slowUntil=st.nowMs+p.durationMs;st.mage.slowPct=p.slowPct;
      log(st,'Rogue','proc','Crippling Poison applied · Mage slowed '+p.slowPct+'% for 12s');
    }else{
      st.mage.mindNumbingUntil=st.nowMs+p.durationMs;
      log(st,'Rogue','proc','Mind-numbing Poison applied · cast time +'+p.castTimeIncreasePct+'% for '+(p.durationMs/1000)+'s');
    }
  }
  function rogueCritMultiplier(st,name){
    const builder=['Hemorrhage','Backstab','Gouge'].includes(name);
    return builder?2+(st.rogue.talents.Lethality||0)*.04:2;
  }
  function castCost(st,actor,name){
    const data=DATA().abilities[actor.name]?.[name];if(!data)return Infinity;
    if(actor===st.rogue){
      let c=data.cost||0;if(name==='Cheap Shot')c=Math.max(0,c-(st.rogue.talents['Dirty Deeds']||0)*10);return c;
    }
    if(data.costPctBaseMana)return st.mage.baseMana*data.costPctBaseMana/100;
    if(st.mage.clearcasting&&['Frostbolt','Ice Lance','Cone of Cold','Fire Blast'].includes(name))return 0;
    return data.cost||0;
  }
  function spendMana(st,amount){
    const n=Math.max(0,Number(amount||0));
    if(n<=0)return 0;
    const spent=Math.min(st.mage.mana,n);
    st.mage.mana-=spent;
    st.mage.lastManaSpendMs=st.nowMs;
    return spent;
  }
  function regenMageMana(st){
    const rule=DATA().inherited.mageManaRegen;if(!rule)return;
    while(st.nowMs>=st.mage.nextManaRegenTickMs){
      if(st.mage.nextManaRegenTickMs-st.mage.lastManaSpendMs>=rule.fiveSecondRuleMs){
        const gain=13+(st.mage.spirit||0)/4;
        st.mage.mana=Math.min(st.mage.maxMana,st.mage.mana+gain);
      }
      st.mage.nextManaRegenTickMs+=rule.tickMs;
    }
    st.metrics.provisionalRulesUsed.add('Classic Mage spirit mana regeneration / five-second rule');
  }
  function talentRank(st,actor,name){return Number(actor.talents[name]||0);}
  function actorCtx(st,who){
    const self=who==='Rogue'?st.rogue:st.mage,enemy=who==='Rogue'?st.mage:st.rogue,memory=st.memory[who];
    const ctx={
      nowMs:st.nowMs,self:{
        ...self,
        healthPct:pct(self.hp,self.maxHp),
        stunned:st.nowMs<self.stunUntil,rooted:st.nowMs<self.rootUntil,slowed:slowed(st,self),
        disoriented:st.nowMs<self.disorientUntil,incapacitated:st.nowMs<self.incapUntil,
        iceBlockActive:self===st.mage&&st.nowMs<st.mage.iceBlockUntil,
        sprintActive:self===st.rogue&&st.nowMs<st.rogue.sprintUntil
      },
      enemy:{
        ...enemy,healthPct:pct(enemy.hp,enemy.maxHp),stunned:st.nowMs<enemy.stunUntil,rooted:rooted(st,enemy),
        frozen:st.nowMs<enemy.rootUntil,stealthed:enemy===st.rogue&&enemy.stealthed,
        iceBlockActive:enemy===st.mage&&st.nowMs<st.mage.iceBlockUntil,
        majorDefensiveActive:enemy===st.mage&&(st.nowMs<st.mage.iceBlockUntil||st.mage.iceBarrierAbsorb>0),
        casting:enemy===st.mage&&!!st.mage.cast,
        castSpell:enemy===st.mage&&st.mage.cast?.spell,
        castDurationMs:enemy===st.mage&&st.mage.cast?.durationMs,
        castElapsedMs:enemy===st.mage&&st.mage.cast?st.nowMs-st.mage.cast.startMs:0,
        castRemainingMs:enemy===st.mage&&st.mage.cast?Math.max(0,st.mage.cast.endMs-st.nowMs):0,
        castHighValue:enemy===st.mage&&!!st.mage.cast&&(st.mage.cast.spell==='Polymorph'||st.mage.cast.spell==='Frostbolt'&&(pct(st.rogue.hp,st.rogue.maxHp)<65||rooted(st,st.rogue))),
        castThreatSoonMs:enemy===st.mage&&!st.mage.cast&&st.range<=30?1200:0,
        stunDRMultiplier:1,incapDRMultiplier:1,disorientDRMultiplier:1,facingRogue:true,
        blinkUsedRecently:enemy===st.mage&&cdRemain(st,st.mage,'Blink')>0,
        blinkUnavailable:enemy===st.mage&&(!isReady(st,st.mage,'Blink')||st.mage.mana<castCost(st,st.mage,'Blink')),
        kickReady:enemy===st.rogue&&isReady(st,st.rogue,'Kick')
      },
      range:st.range,meleeRange:meleeRange(),memory,
      talentRank:name=>talentRank(st,self,name),
      ready:name=>isReady(st,self,name),
      cooldownRemaining:name=>cdRemain(st,self,name),
      cost:name=>castCost(st,self,name),
      canKillEvis:false
    };
    return ctx;
  }

  function startMageCast(st,spell,decision){
    const d=DATA().abilities.Mage[spell];
    let castMs=d.castMs||0;
    if(spell==='Frostbolt')castMs-=100*(st.mage.talents['Improved Frostbolt']||0);
    if(st.nowMs<(st.mage.mindNumbingUntil||0))castMs*=1.6;
    if(castMs<=0)return false;
    spendMana(st,castCost(st,st.mage,spell));
    st.mage.cast={spell,startMs:st.nowMs,durationMs:castMs,endMs:st.nowMs+castMs,fakeAtMs:decision.fakeAtMs?st.nowMs+decision.fakeAtMs:null,decision};
    st.mage.gcdUntil=Math.max(st.mage.gcdUntil,st.nowMs+(d.gcdMs||1500));
    log(st,'Mage','cast',spell+' cast started · '+(castMs/1000).toFixed(2)+'s',decision);return true;
  }
  function applyChillProcs(st){
    if((st.mage.talents.Frostbite||0)>=3&&chance(st,15)){
      st.rogue.rootUntil=Math.max(st.rogue.rootUntil,st.nowMs+5000);
      log(st,'Mage','proc','Frostbite proc · Rogue frozen 5s');
    }
    const fofRank=Number(st.mage.talents['Fingers of Frost']||0),fof=DATA().talents.Mage['Fingers of Frost'];
    const fofChance=Number(fof?.procChanceByRankPct?.[fofRank]||0);
    if(fofChance>0&&chance(st,fofChance)){
      st.mage.fingersOfFrostCharges=Number(fof.charges||1);st.mage.fingersOfFrostUntil=st.nowMs+Number(fof.durationMs||15000);
      log(st,'Mage','proc','Fingers of Frost proc · '+st.mage.fingersOfFrostCharges+' charge');
    }
  }
  function resolveMageSpell(st,spell,decision){
    const d=DATA().abilities.Mage[spell],m=st.mage,r=st.rogue;
    if(!d)return;
    const frozen=rooted(st,r)||m.fingersOfFrostCharges>0;
    const spendClear=m.clearcasting&&['Frostbolt','Ice Lance','Cone of Cold','Fire Blast'].includes(spell);
    if(['Frostbolt','Ice Lance','Cone of Cold','Fire Blast','Frost Nova'].includes(spell)){
      if(!spellLands(st)){log(st,'Mage','miss',spell+' missed');if(spendClear)m.clearcasting=false;return;}
      let raw=roll(st,d.min,d.max),school=d.school||'Frost';
      if(spell==='Frostbolt')raw+=m.frostSpellPower*d.spCoeff;
      if(spell==='Ice Lance')raw+=m.frostSpellPower*d.spCoeff;
      if(spell==='Cone of Cold')raw+=m.frostSpellPower*d.spCoeff;
      if(spell==='Fire Blast')raw+=m.spellPower*d.spCoeff;
      if(school==='Frost')raw*=1+(m.talents['Piercing Ice']||0)*.02;
      if(spell==='Ice Lance'&&frozen)raw*=d.frozenMultiplier;
      let critChance=m.critPct+(frozen?(m.talents.Shatter||0)>=3?50:0:0);
      const crit=chance(st,critChance);
      if(crit)raw*=school==='Frost'&&(m.talents['Ice Shards']||0)>=5?2:1.5;
      const out=damage(st,r,raw,{actor:'Mage',school,physical:false});
      log(st,'Mage',crit?'crit':'damage',spell+' '+(crit?'CRIT ':'')+round(out.dealt)+' damage → Rogue '+round(r.hp)+' HP',decision);
      if(spell==='Frostbolt'){
        const dur=Math.round(d.slowMs*(1+((m.talents.Permafrost||0)>=3?.33:0)));r.slowUntil=st.nowMs+dur;r.slowPct=d.slowPct+((m.talents.Permafrost||0)>=3?10:0);applyChillProcs(st);
      }
      if(spell==='Cone of Cold'){r.slowUntil=st.nowMs+d.slowMs;r.slowPct=d.slowPct+((m.talents.Permafrost||0)>=3?10:0);applyChillProcs(st);}
      if(spell==='Frost Nova'){r.rootUntil=st.nowMs+d.rootMs;st.metrics.mage.novas++;log(st,'Mage','control','Frost Nova roots Rogue for up to 8s');}
      if(m.fingersOfFrostCharges>0&&['Frostbolt','Ice Lance','Cone of Cold','Fire Blast'].includes(spell)){m.fingersOfFrostCharges--;if(m.fingersOfFrostCharges<=0)m.fingersOfFrostUntil=0;}
      if((m.talents['Arcane Concentration']||0)>=5&&chance(st,10)){m.clearcasting=true;log(st,'Mage','proc','Clearcasting proc');}
    }
    if(spendClear)m.clearcasting=false;
  }
  function finishMageCast(st){
    const cast=st.mage.cast;if(!cast)return;
    st.mage.cast=null;
    if(st.nowMs<(st.mage.schoolLockUntil.Frost||0)&&DATA().abilities.Mage[cast.spell]?.school==='Frost'){log(st,'Mage','interrupt',cast.spell+' fails: Frost school locked');return;}
    resolveMageSpell(st,cast.spell,cast.decision);
  }

  function executeRogue(st,d){
    const r=st.rogue,m=st.mage,a=DATA().abilities.Rogue[d.action];if(!a&&d.action!=='MOVE_TO'&&d.action!=='HOLD')return;
    if(d.action==='HOLD'){st.metrics.rogue.holds++;if(d.reserveResource>0)st.metrics.rogue.energyStarveAvoided++;return;}
    if(d.action==='MOVE_TO'){r.moveTarget=d.targetRange||5;return;}
    const cost=castCost(st,r,d.action);if(r.energy+1e-6<cost)return;r.energy-=cost;
    setCd(st,r,d.action,a.cooldownMs||0);r.gcdUntil=Math.max(r.gcdUntil,st.nowMs+(a.gcdMs||0));
    if(d.action==='Premeditation'){const gain=Math.min(5-r.comboPoints,2);r.comboPoints+=gain;r.premedCp+=gain;r.premedExpire=st.nowMs+a.comboExpiryMs;log(st,'Rogue','control','Premeditation +'+gain+' CP → '+r.comboPoints+' CP',d);return;}
    if(d.action==='Cheap Shot'){
      r.stealthed=false;let gain=2;if((r.talents.Initiative||0)>=3)gain++;r.comboPoints=Math.min(5,r.comboPoints+gain);m.stunUntil=st.nowMs+a.stunMs;
      log(st,'Rogue','control','Cheap Shot · Mage stunned 4s · +'+gain+' CP → '+r.comboPoints+' CP',d);return;
    }
    if(d.action==='Kick'){
      let dealt=0;if(specialLands(st)==='hit'){const out=damage(st,m,a.damage*rogueDamageMods(st),{actor:'Rogue',physical:true});dealt=out.dealt;}
      if(m.cast){const school=DATA().abilities.Mage[m.cast.spell]?.school||'Arcane';log(st,'Rogue','interrupt','Kick interrupts '+m.cast.spell+' · '+school+' locked 5s',d);m.cast=null;m.schoolLockUntil[school]=st.nowMs+a.lockMs;st.metrics.rogue.kicks++;}
      else log(st,'Rogue','damage','Kick '+round(dealt)+' damage',d);return;
    }
    if(d.action==='Kidney Shot'){
      const cp=r.comboPoints,dur=a.durationsMs[cp]||0;r.comboPoints=0;r.premedCp=0;m.stunUntil=st.nowMs+dur;st.metrics.rogue.kidneys++;
      log(st,'Rogue','control','Kidney Shot '+cp+' CP · Mage stunned '+(dur/1000)+'s',d);return;
    }
    if(d.action==='Cold Blood'){r.coldBloodActive=true;log(st,'Rogue','buff','Cold Blood armed',d);return;}
    if(d.action==='Eviscerate'){
      const cp=clamp(r.comboPoints,1,5),pair=a.baseByCp[cp],land=specialLands(st);r.comboPoints=0;r.premedCp=0;
      if(land!=='hit'){log(st,'Rogue','miss','Eviscerate '+land,d);r.coldBloodActive=false;return;}
      st.metrics.provisionalRulesUsed.add('Eviscerate AP coefficient');
      let raw=roll(st,pair[0],pair[1])+r.ap*a.apCoeffPerCp*cp;
      const ie=Number(r.talents['Improved Eviscerate']||0),iePct=Number(DATA().talents.Rogue['Improved Eviscerate']?.evisDamageByRankPct?.[ie]||0);raw*=1+iePct/100;
      raw*=rogueDamageMods(st,{builder:false});
      const crit=r.coldBloodActive||chance(st,r.critPct);r.coldBloodActive=false;if(crit)raw*=2;
      raw*=1-physicalReduction(armorAgainstRogue(st));
      const out=damage(st,m,raw,{actor:'Rogue',physical:true});
      log(st,'Rogue',crit?'crit':'damage','Eviscerate '+cp+' CP '+(crit?'CRIT ':'')+round(out.dealt)+' damage → Mage '+round(m.hp)+' HP',d);return;
    }
    if(d.action==='Hemorrhage'){
      const land=specialLands(st);if(land!=='hit'){log(st,'Rogue','miss','Hemorrhage '+land,d);return;}
      let raw=weaponDamage(st,'mh')*(r.mh.type==='Dagger'?a.daggerPct:a.weaponPct)*rogueDamageMods(st,{builder:true});
      const crit=chance(st,r.critPct);if(crit)raw*=rogueCritMultiplier(st,'Hemorrhage');
      raw*=1-physicalReduction(armorAgainstRogue(st));const out=damage(st,m,raw,{actor:'Rogue',physical:true});
      r.comboPoints=Math.min(5,r.comboPoints+1);procPoison(st,'mh');
      log(st,'Rogue',crit?'crit':'damage','Hemorrhage '+(crit?'CRIT ':'')+round(out.dealt)+' damage · '+r.comboPoints+' CP → Mage '+round(m.hp)+' HP',d);return;
    }
    if(d.action==='Gouge'){
      const land=specialLands(st);if(land!=='hit'){log(st,'Rogue','miss','Gouge '+land,d);return;}
      const dur=a.incapMs+(r.talents['Improved Gouge']||0)*500;m.incapUntil=st.nowMs+dur;r.comboPoints=Math.min(5,r.comboPoints+1);
      log(st,'Rogue','control','Gouge incapacitates Mage '+(dur/1000).toFixed(1)+'s',d);return;
    }
    if(d.action==='Blind'){m.disorientUntil=st.nowMs+a.disorientMs;st.metrics.rogue.resets++;log(st,'Rogue','control','Blind disorients Mage up to 10s',d);return;}
    if(d.action==='Vanish'){r.stealthed=true;r.rootUntil=0;r.slowUntil=0;r.slowPct=0;st.metrics.rogue.resets++;log(st,'Rogue','reset','Vanish · movement effects cleared · Stealth',d);return;}
    if(d.action==='Sprint'){r.sprintUntil=st.nowMs+a.durationMs;log(st,'Rogue','mobility','Sprint +70% movement for 15s',d);return;}
    if(d.action==='Evasion'){r.evasionUntil=st.nowMs+a.durationMs;log(st,'Rogue','defensive','Evasion +50% dodge for 15s',d);return;}
    if(d.action==='Preparation'){
      for(const name of Object.keys(r.cooldowns))if(name!=='Preparation')r.cooldowns[name]=0;
      log(st,'Rogue','reset','Preparation resets other Rogue cooldowns',d);return;
    }
  }

  function executeMage(st,d){
    const m=st.mage,r=st.rogue,a=DATA().abilities.Mage[d.action];if(!a&&d.action!=='MOVE_TO'&&d.action!=='HOLD')return;
    if(d.action==='HOLD')return;
    if(d.action==='MOVE_TO'){m.moveTarget=d.targetRange||30;return;}
    const cost=castCost(st,m,d.action);if(m.mana+1e-6<cost)return;
    if(a.castMs){startMageCast(st,d.action,d);return;}
    spendMana(st,cost);if(m.clearcasting&&['Ice Lance','Cone of Cold','Fire Blast'].includes(d.action))m.clearcasting=false;
    setCd(st,m,d.action,a.cooldownMs||0);m.gcdUntil=Math.max(m.gcdUntil,st.nowMs+(a.gcdMs||0));
    if(d.action==='Blink'){
      m.stunUntil=0;m.rootUntil=0;st.range=clamp(st.range+a.distance,0,40);st.metrics.mage.blinks++;st.memory.Mage.blinkObserved=true;
      log(st,'Mage','mobility','Blink breaks control and opens 20 yd → range '+st.range.toFixed(1),d);return;
    }
    if(d.action==='Ice Barrier'){m.iceBarrierAbsorb=a.absorb;log(st,'Mage','defensive','Ice Barrier '+a.absorb+' absorb',d);return;}
    if(d.action==='Mana Shield'){m.manaShieldAbsorb=a.absorb+285;log(st,'Mage','defensive','Mana Shield '+m.manaShieldAbsorb+' physical absorb (includes glove bonus)',d);return;}
    if(d.action==='Ice Block'){m.iceBlockUntil=st.nowMs+a.durationMs;m.cast=null;st.metrics.mage.iceBlocks++;log(st,'Mage','defensive','Ice Block · immune 10s',d);return;}
    if(d.action==='Cold Snap'){
      for(const name of ['Frost Nova','Cone of Cold','Ice Barrier','Ice Block'])m.cooldowns[name]=0;
      log(st,'Mage','reset','Cold Snap resets other Frost cooldowns',d);return;
    }
    resolveMageSpell(st,d.action,d);setCd(st,m,d.action,a.cooldownMs||0);
  }

  function processMageCast(st){
    const c=st.mage.cast;if(!c)return;
    if(c.fakeAtMs&&st.nowMs>=c.fakeAtMs&&st.nowMs<c.endMs){
      st.mage.cast=null;st.memory.Mage.fakeCasts++;st.memory.Rogue.fakeCastRestarts++;
      st.metrics.mage.fakeCasts++;log(st,'Mage','fakecast',c.spell+' fake-cast cancelled · bait #'+st.memory.Mage.fakeCasts,c.decision);return;
    }
    if(st.nowMs>=c.endMs)finishMageCast(st);
  }
  function expire(st){
    const r=st.rogue,m=st.mage;
    if(r.premedExpire&&st.nowMs>=r.premedExpire&&r.premedCp>0){
      const lost=Math.min(r.comboPoints,r.premedCp);r.comboPoints-=lost;r.premedCp=0;r.premedExpire=0;if(lost)log(st,'Rogue','resource','Premeditation expires · -'+lost+' CP');
    }
    if(m.fingersOfFrostUntil&&st.nowMs>=m.fingersOfFrostUntil){m.fingersOfFrostCharges=0;m.fingersOfFrostUntil=0;}
    if(r.slowUntil&&st.nowMs>=r.slowUntil){r.slowUntil=0;r.slowPct=0;}
    if(m.slowUntil&&st.nowMs>=m.slowUntil){m.slowUntil=0;m.slowPct=0;}
  }
  function movement(st,dt){
    const r=st.rogue,m=st.mage,d=DATA(),base=d.inherited.movementSpeedYps.value;st.metrics.provisionalRulesUsed.add('movement speed');st.metrics.provisionalRulesUsed.add('combat reach tolerance');
    if(r.stealthed){
      if(!controlled(st,r)&&!rooted(st,r)&&st.range>meleeRange()){
        const stealthPenalty=(r.talents.Camouflage||0)>=5?.15:.30,sprint=st.nowMs<r.sprintUntil?1.7:1;
        st.range=Math.max(meleeRange(),st.range-base*(1-stealthPenalty)*sprint*dt);
      }
      return;
    }
    let rSpeed=base*(1-(slowed(st,r)?r.slowPct/100:0))*(st.nowMs<r.sprintUntil?1.7:1);
    let mSpeed=base*(1-(slowed(st,m)?m.slowPct/100:0));
    const rCan=!controlled(st,r)&&!rooted(st,r),mCan=!controlled(st,m)&&!rooted(st,m)&&!m.cast&&st.nowMs>=m.iceBlockUntil;
    if(rCan&&st.range>meleeRange())st.range-=rSpeed*dt;
    if(mCan&&st.range<28)st.range+=mSpeed*dt;
    st.range=clamp(st.range,0,40);
  }
  function whiteSwing(st,hand){
    const r=st.rogue,m=st.mage,w=r[hand];
    if(r.stealthed||controlled(st,r)||rooted(st,r)||st.range>meleeRange()||st.nowMs<m.iceBlockUntil)return;
    const land=whiteLands(st);if(land!=='hit'){log(st,'Rogue','swing',hand.toUpperCase()+' swing '+land);return;}
    let raw=weaponDamage(st,hand)*(hand==='oh'?.5:1)*rogueDamageMods(st,{builder:false});
    const crit=chance(st,r.critPct);if(crit)raw*=2;raw*=1-physicalReduction(armorAgainstRogue(st));
    const out=damage(st,m,raw,{actor:'Rogue',physical:true,kind:'swing'});procPoison(st,hand);
    log(st,'Rogue',crit?'crit':'swing',hand.toUpperCase()+' '+(crit?'CRIT ':'')+round(out.dealt)+' → Mage '+round(m.hp)+' HP');
  }
  function processSwings(st){
    const r=st.rogue;
    if(r.nextMhSwing<=st.nowMs){whiteSwing(st,'mh');r.nextMhSwing=st.nowMs+r.mh.speed*1000;}
    if(r.nextOhSwing<=st.nowMs){whiteSwing(st,'oh');r.nextOhSwing=st.nowMs+r.oh.speed*1000;}
  }
  function decide(st,who){
    const a=who==='Rogue'?st.rogue:st.mage;
    if(a.dead)return;
    if(who==='Mage'&&a.cast)return;
    if(st.nowMs<a.gcdUntil)return;
    const ctx=actorCtx(st,who),d=POL().choose(who,ctx);
    if(!d)return;
    if(!st.compact)st.decisionTrace.push(d);
    if(who==='Rogue')executeRogue(st,d);else executeMage(st,d);
  }
  function regen(st,dt){st.rogue.energy=Math.min(st.rogue.maxEnergy,st.rogue.energy+st.rogue.energyRegenPerSec*dt);st.metrics.provisionalRulesUsed.add('Rogue continuous energy regeneration');}
  function tick(st){
    const dt=st.tickMs/1000;st.nowMs+=st.tickMs;expire(st);regen(st,dt);regenMageMana(st);processMageCast(st);movement(st,dt);processSwings(st);
    decide(st,'Mage');decide(st,'Rogue');
  }
  function result(st){
    const winner=st.rogue.dead?'Mage':st.mage.dead?'Rogue':'Timeout';
    const duration=st.nowMs/1000;
    return{
      seed:st.seed,winner,duration,timeline:st.timeline,decisionTrace:st.decisionTrace,
      final:{rogue:{hp:round(st.rogue.hp),maxHp:st.rogue.maxHp,energy:round(st.rogue.energy),comboPoints:st.rogue.comboPoints},mage:{hp:round(st.mage.hp),maxHp:st.mage.maxHp,mana:round(st.mage.mana)}},
      metrics:{rogue:st.metrics.rogue,mage:st.metrics.mage,provisionalRulesUsed:[...st.metrics.provisionalRulesUsed]},
      status:'FOREVER_REFERENCE_MODEL',clientBuild:DATA().clientBuild,certifiedParity:false,
      scenario:DATA().scenario.id
    };
  }
  function run(seed,config,opts={}){
    const gate=supported(config);if(!gate.ready)return{error:'MATCHUP_LOCKED',missing:gate.issues,status:'LOCKED'};
    const st=initState(seed,config,opts);log(st,'System','start','Forever reference duel starts · range '+st.range+' yd · Rogue Stealthed · Mage Ice Barrier + Ice Armor');
    while(st.nowMs<st.maxMs&&!st.rogue.dead&&!st.mage.dead)tick(st);
    log(st,'System','end',(st.rogue.dead?'Mage':st.mage.dead?'Rogue':'Timeout')+' · duel complete');
    return result(st);
  }
  function summarize(results){
    const s={fights:results.length,Rogue:0,Mage:0,Timeout:0,totalDuration:0};
    for(const r of results){s[r.winner]=(s[r.winner]||0)+1;s.totalDuration+=r.duration||0;}
    s.roguePct=results.length?s.Rogue/results.length*100:0;s.magePct=results.length?s.Mage/results.length*100:0;s.timeoutPct=results.length?s.Timeout/results.length*100:0;s.avgDuration=results.length?s.totalDuration/results.length:0;
    return s;
  }
  async function batch(count,seed,config,onProgress){
    const gate=supported(config);if(!gate.ready)return{error:'MATCHUP_LOCKED',missing:gate.issues};
    const s={fights:0,Rogue:0,Mage:0,Timeout:0,totalDuration:0},chunk=count>=100000?250:count>=10000?100:50;
    for(let i=0;i<count;i++){
      const r=run(((seed>>>0)+Math.imul(i,2654435761))>>>0,config,{compact:true});
      s.fights++;s[r.winner]=(s[r.winner]||0)+1;s.totalDuration+=r.duration||0;
      if((i+1)%chunk===0){onProgress?.(i+1,count);await new Promise(resolve=>setTimeout(resolve,0));}
    }
    s.roguePct=s.Rogue/s.fights*100;s.magePct=s.Mage/s.fights*100;s.timeoutPct=s.Timeout/s.fights*100;s.avgDuration=s.totalDuration/s.fights;
    return{...s,seed,count,status:'FOREVER_REFERENCE_MODEL'};
  }

  window.WOW_FOREVER_COMBAT_ENGINE={version:'0.51-beta-69913-reference-engine',status:'REFERENCE_MODEL',supported,run,batch,physicalReduction};
})();