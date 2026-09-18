(function(){
  const D=()=>window.WOW_FOREVER_COMBAT_DATA;
  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  const rank=(ctx,name)=>Number(ctx.talentRank?.(name)||0);
  const has=(ctx,name)=>rank(ctx,name)>0;
  const ready=(ctx,name)=>ctx.ready?.(name)===true;
  const cd=(ctx,name)=>Number(ctx.cooldownRemaining?.(name)||0);

  function trace(actor,layer,action,reason,plan,ctx,extra={}){
    return {
      actor,layer,action,reason,plan,
      priority:extra.priority||0,
      reserveResource:extra.reserveResource||0,
      target:extra.target||'enemy',
      evidence:extra.evidence||[],
      rejected:extra.rejected||[],
      atMs:ctx.nowMs,
      ...extra
    };
  }
  function hold(actor,ctx,reason,plan,reserve=0,evidence=[]){
    return trace(actor,'HOLD','HOLD',reason,plan,ctx,{priority:100,reserveResource:reserve,evidence});
  }

  function rogueCost(ctx,name){
    let base=D().abilities.Rogue[name]?.cost;
    if(name==='Cheap Shot'&&has(ctx,'Dirty Deeds'))base=Math.max(0,base-10*rank(ctx,'Dirty Deeds'));
    if(name==='Gouge'&&has(ctx,'Improved Gouge'))base=base;
    return Number(base||0);
  }
  function rogueReserve(ctx,plan){
    const me=ctx.self,enemy=ctx.enemy;
    let reserve=0;const evidence=[];
    if(ready(ctx,'Kick')&&enemy.casting&&enemy.castHighValue&&ctx.range<=5){
      reserve=Math.max(reserve,rogueCost(ctx,'Kick'));evidence.push('reserve Kick for active cast');
    }else if(ready(ctx,'Kick')&&enemy.castThreatSoonMs>0&&enemy.castThreatSoonMs<=1800&&ctx.range<=7){
      reserve=Math.max(reserve,rogueCost(ctx,'Kick'));evidence.push('reserve Kick for predicted cast');
    }
    if((me.comboPoints||0)>=5&&ready(ctx,'Kidney Shot')&&enemy.stunDRMultiplier>0){
      const follow=35;reserve=Math.max(reserve,rogueCost(ctx,'Kidney Shot')+follow);evidence.push('reserve Kidney + finisher Energy');
    }
    if(plan==='RESET'&&ready(ctx,'Gouge')){reserve=Math.max(reserve,rogueCost(ctx,'Gouge'));evidence.push('reserve Gouge reset');}
    return{reserve,evidence};
  }
  function roguePlan(ctx){
    const me=ctx.self,e=ctx.enemy;
    if(e.iceBlockActive)return'WAIT_IMMUNITY';
    if((e.healthPct||100)<=30)return'KILL';
    if((me.healthPct||100)<=35||e.majorDefensiveActive)return'RESET';
    if((me.comboPoints||0)>=5)return'CONTROL';
    return'PRESSURE';
  }
  function interruptDecision(ctx,memory,reserve){
    const e=ctx.enemy;
    if(!e.casting||!e.castHighValue||!ready(ctx,'Kick')||ctx.range>5)return null;
    const remain=e.castRemainingMs,elapsed=e.castElapsedMs,dur=e.castDurationMs;
    if(remain==null)return hold('Rogue',ctx,'cast deadline unknown; preserve Kick','INTERRUPT',reserve,['high-value cast']);
    if(remain<=250)return trace('Rogue','DEADLINE_INTERRUPT','Kick','emergency interrupt window','DENY_CAST',ctx,{priority:900,reserveResource:reserve,evidence:[e.castSpell,remain+'ms remaining']});
    if(elapsed<300)return hold('Rogue',ctx,'anti-fake floor','DENY_CAST',Math.max(reserve,25),[e.castSpell,elapsed+'ms elapsed']);
    let target=.72;if((memory.fakeCastRestarts||0)>=2)target=.80;
    const progress=dur>0?elapsed/dur:0;
    if(progress>=target)return trace('Rogue','DEADLINE_INTERRUPT','Kick','anti-fake timing reached','DENY_CAST',ctx,{priority:890,reserveResource:reserve,evidence:[e.castSpell,Math.round(progress*100)+'% cast',(memory.fakeCastRestarts||0)+' observed fake restarts']});
    if(remain<=900)return hold('Rogue',ctx,'hold GCD/Energy for interrupt deadline','DENY_CAST',Math.max(reserve,25),[remain+'ms remaining']);
    return null;
  }
  function chooseRogue(ctx){
    const me=ctx.self,e=ctx.enemy,m=ctx.memory||{};
    const rejected=[];
    if(me.dead)return hold('Rogue',ctx,'dead','NONE');
    if(me.stunned||me.disoriented||me.incapacitated)return hold('Rogue',ctx,'hard crowd control active','RECOVER_CONTROL');
    if(me.rooted){
      if(ready(ctx,'Vanish'))return trace('Rogue','MOVEMENT_EMERGENCY','Vanish','break root and create reopen','RESET_REOPEN',ctx,{priority:930});
      if(has(ctx,'Preparation')&&!ready(ctx,'Vanish')&&ready(ctx,'Preparation'))return trace('Rogue','MOVEMENT_EMERGENCY','Preparation','Vanish unavailable while rooted; reset Rogue cooldowns','RESET_COOLDOWNS',ctx,{priority:920});
      return hold('Rogue',ctx,'rooted; no verified escape ready','RECOVER_CONTROL');
    }

    const plan=roguePlan(ctx),rr=rogueReserve(ctx,plan),reserve=rr.reserve;
    const kick=interruptDecision(ctx,m,reserve);if(kick)return kick;

    if(e.iceBlockActive)return hold('Rogue',ctx,'Ice Block active; do not spend Energy','WAIT_IMMUNITY',reserve,['target immune']);

    if(me.stealthed){
      if(has(ctx,'Premeditation')&&ready(ctx,'Premeditation')&&(me.comboPoints||0)<=3&&ctx.range<=20)
        return trace('Rogue','CONTROL','Premeditation','bank 2 combo points before opener','OPEN_CONTROL',ctx,{priority:720,evidence:['stealthed','Premeditation selected']});
      if(ctx.range>5)return trace('Rogue','MOBILITY','MOVE_TO','close from Stealth without consuming cooldown','OPEN',ctx,{priority:700,targetRange:5});
      const cs=rogueCost(ctx,'Cheap Shot');
      if(me.energy>=cs)return trace('Rogue','CONTROL','Cheap Shot','verified stealth stun opener','OPEN_CONTROL',ctx,{priority:680,evidence:['cost '+cs,'Initiative '+rank(ctx,'Initiative')+'/3']});
      return hold('Rogue',ctx,'pool Energy for Cheap Shot','OPEN',cs);
    }

    if((me.healthPct||100)<=22&&ready(ctx,'Vanish'))return trace('Rogue','DEFENSIVE','Vanish','emergency defensive reset','RESET_REOPEN',ctx,{priority:850});
    if((me.healthPct||100)<=22&&has(ctx,'Preparation')&&ready(ctx,'Preparation')&&!ready(ctx,'Vanish'))
      return trace('Rogue','DEFENSIVE','Preparation','recover Vanish for emergency reset','RESET_COOLDOWNS',ctx,{priority:840});

    if(plan==='RESET'){
      if(ctx.range<=5&&e.facingRogue&&ready(ctx,'Gouge')&&e.incapDRMultiplier>0&&me.energy>=rogueCost(ctx,'Gouge'))
        return trace('Rogue','RESET','Gouge','create break-on-damage reset window','RESET_REOPEN',ctx,{priority:800,reserveResource:reserve});
      if(ctx.range<=10&&ready(ctx,'Blind')&&e.disorientDRMultiplier>0&&me.energy>=rogueCost(ctx,'Blind'))
        return trace('Rogue','RESET','Blind','create long reset window','RESET_REOPEN',ctx,{priority:790,reserveResource:reserve});
      if(ready(ctx,'Vanish'))return trace('Rogue','RESET','Vanish','direct reset/reopen','RESET_REOPEN',ctx,{priority:780});
    }

    if(ctx.range>5){
      if(ctx.range>=7&&ready(ctx,'Sprint')&&!me.sprintActive)return trace('Rogue','MOBILITY','Sprint','reconnect after Mage separation','RECONNECT',ctx,{priority:700});
      return trace('Rogue','MOBILITY','MOVE_TO','recover melee range','RECONNECT',ctx,{priority:690,targetRange:5});
    }

    const cp=me.comboPoints||0;
    const blinkUnavailable=cd(ctx,'Blink')>0||e.blinkUsedRecently===true;
    if(cp>=5&&!e.stunned&&e.stunDRMultiplier>0&&ready(ctx,'Kidney Shot')){
      const need=rogueCost(ctx,'Kidney Shot')+35;
      if((me.energy||0)>=need&&blinkUnavailable)
        return trace('Rogue','CONTROL','Kidney Shot','convert 5 CP after Blink is unavailable','KILL_CONTROL',ctx,{priority:650,reserveResource:reserve,evidence:['Blink unavailable',me.energy+' Energy']});
      if(!blinkUnavailable)rejected.push({action:'Kidney Shot',reason:'preserve Kidney until Blink is committed'});
      else if((me.energy||0)<need)return hold('Rogue',ctx,'pool for Kidney + follow-up instead of wasting control','CONTROL',need,['5 CP']);
    }

    const hp=e.healthPct||100;
    const kill=hp<=30||(ctx.canKillEvis===true);
    if(cp>=4&&kill){
      if(has(ctx,'Cold Blood')&&cp>=5&&ready(ctx,'Cold Blood')&&!me.coldBloodActive)
        return trace('Rogue','KILL','Cold Blood','prepare guaranteed Eviscerate crit','KILL_EVIS',ctx,{priority:610,reserveResource:reserve,evidence:[cp+' CP',hp.toFixed(1)+'% target HP']});
      if((me.energy||0)>=rogueCost(ctx,'Eviscerate'))
        return trace('Rogue','KILL','Eviscerate','convert combo points in kill window','KILL',ctx,{priority:600,reserveResource:reserve,evidence:[cp+' CP']});
    }

    if(cp>=5&&e.stunned&&me.energy>=rogueCost(ctx,'Eviscerate')+reserve)
      return trace('Rogue','DAMAGE','Eviscerate','convert CP during protected stun pressure','PRESSURE',ctx,{priority:550,reserveResource:reserve,rejected});

    if(has(ctx,'Hemorrhage')){
      const cost=rogueCost(ctx,'Hemorrhage');
      if((me.energy||0)>=cost+reserve)
        return trace('Rogue','DAMAGE','Hemorrhage','builder without starving higher-priority Energy','BUILD_COMBO',ctx,{priority:500,reserveResource:reserve,evidence:[reserve+' reserved Energy'],rejected});
      return hold('Rogue',ctx,'intentional Energy hold for higher-priority future action','PRESSURE',reserve,rr.evidence);
    }
    return hold('Rogue',ctx,'no verified action beats waiting','PRESSURE',reserve,rr.evidence);
  }

  function magePlan(ctx){
    const me=ctx.self,e=ctx.enemy;
    if((me.healthPct||100)<=22)return'SURVIVE';
    if(e.stealthed)return'DETECT_WAIT';
    if(ctx.range<=8)return'ESCAPE_MELEE';
    if(e.rooted||e.frozen)return'SHATTER';
    return'CONTROL_PRESSURE';
  }
  function chooseMage(ctx){
    const me=ctx.self,e=ctx.enemy,m=ctx.memory||{},plan=magePlan(ctx);
    if(me.dead)return hold('Mage',ctx,'dead','NONE');
    if(me.iceBlockActive)return hold('Mage',ctx,'Ice Block active','SURVIVE');
    if(me.stunned){
      if(ready(ctx,'Blink')&&me.mana>=ctx.cost('Blink'))return trace('Mage','EMERGENCY','Blink','break stun and create 20 yd separation','ESCAPE_MELEE',ctx,{priority:950});
      if((me.healthPct||100)<=20&&has(ctx,'Ice Block')&&ready(ctx,'Ice Block'))return trace('Mage','EMERGENCY','Ice Block','lethal stun with Blink unavailable','SURVIVE',ctx,{priority:940});
      return hold('Mage',ctx,'stunned; no verified escape ready','SURVIVE');
    }
    if(me.rooted){
      if(ready(ctx,'Blink')&&me.mana>=ctx.cost('Blink'))return trace('Mage','EMERGENCY','Blink','break immobilize and create separation','ESCAPE_MELEE',ctx,{priority:930});
      return hold('Mage',ctx,'rooted; Escape Artist cooldown is not verified for this reference model','RECOVER_CONTROL');
    }
    if(me.disoriented||me.incapacitated)return hold('Mage',ctx,'crowd control active','RECOVER_CONTROL');
    if(e.stealthed)return hold('Mage',ctx,'Rogue not targetable while stealthed','DETECT_WAIT');

    if((me.healthPct||100)<=20&&has(ctx,'Ice Block')&&ready(ctx,'Ice Block')&&me.mana>=ctx.cost('Ice Block'))
      return trace('Mage','DEFENSIVE','Ice Block','emergency immunity at lethal HP','SURVIVE',ctx,{priority:850});

    if(me.iceBarrierAbsorb<=0&&has(ctx,'Ice Barrier')&&ready(ctx,'Ice Barrier')&&me.mana>=ctx.cost('Ice Barrier'))
      return trace('Mage','DEFENSIVE','Ice Barrier','restore verified absorb before more pressure','SURVIVE',ctx,{priority:830});

    if(ctx.range<=10&&!e.rooted&&ready(ctx,'Frost Nova')&&me.mana>=ctx.cost('Frost Nova'))
      return trace('Mage','CONTROL','Frost Nova','root melee Rogue before kiting','ESCAPE_MELEE',ctx,{priority:760});

    if(e.rooted&&ctx.range<18&&ready(ctx,'Blink')&&me.mana>=ctx.cost('Blink'))
      return trace('Mage','MOBILITY','Blink','convert Frost Nova into separation','SHATTER',ctx,{priority:735});

    if(ctx.range<=7&&me.manaShieldAbsorb<=0&&ready(ctx,'Mana Shield')&&me.mana>=ctx.cost('Mana Shield'))
      return trace('Mage','DEFENSIVE','Mana Shield','extra absorb under melee pressure','SURVIVE',ctx,{priority:720});

    if(has(ctx,'Cold Snap')&&ready(ctx,'Cold Snap')&&cd(ctx,'Frost Nova')>8000&&cd(ctx,'Ice Barrier')>10000&&(me.healthPct||100)<55)
      return trace('Mage','DEFENSIVE','Cold Snap','recover Frost control/defense under sustained pressure','SURVIVE',ctx,{priority:710});

    const frozen=e.frozen||e.rooted||me.fingersOfFrostCharges>0;
    if(frozen&&has(ctx,'Ice Lance')&&ctx.range<=30&&me.mana>=ctx.cost('Ice Lance'))
      return trace('Mage','DAMAGE','Ice Lance','shatter pressure on Frozen-equivalent target','SHATTER',ctx,{priority:620,evidence:[frozen?'Frozen/FoF':'']});

    if(ctx.range<=10&&ready(ctx,'Cone of Cold')&&me.mana>=ctx.cost('Cone of Cold'))
      return trace('Mage','DAMAGE','Cone of Cold','instant close-range Frost pressure and slow','PRESSURE',ctx,{priority:590});

    if(ctx.range<=20&&ready(ctx,'Fire Blast')&&me.mana>=ctx.cost('Fire Blast')&&(ctx.range<12||e.healthPct<25))
      return trace('Mage','DAMAGE','Fire Blast','instant pressure while kiting','PRESSURE',ctx,{priority:560});

    if(ctx.range<=30&&me.mana>=ctx.cost('Frostbolt')){
      const canFake=e.kickReady===true&&ctx.range<=5&&(m.fakeCasts||0)<2;
      return trace('Mage','DAMAGE','Frostbolt',canFake?'start Frostbolt with deliberate fake-cast plan':'primary ranged pressure','CONTROL_PRESSURE',ctx,{
        priority:520,
        fakeAtMs:canFake?450+150*(m.fakeCasts||0):null,
        evidence:canFake?['Rogue Kick ready','anti-interrupt bait']:['cast pressure']
      });
    }
    if(ctx.range>30)return trace('Mage','MOBILITY','MOVE_TO','enter spell range','CONTROL_PRESSURE',ctx,{priority:400,targetRange:30});
    return hold('Mage',ctx,'no verified action currently improves position','CONTROL_PRESSURE');
  }

  window.WOW_FOREVER_COMBAT_POLICIES={
    version:'0.50-expert-policies',
    chooseRogue,chooseMage,
    choose(className,ctx){return className==='Rogue'?chooseRogue(ctx):className==='Mage'?chooseMage(ctx):hold(className,ctx,'class policy unavailable','LOCKED');}
  };
})();