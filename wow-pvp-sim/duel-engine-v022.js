window.WOW_DUEL=(function(){
  const D=window.WOW_DATA,E=window.WOW_ENGINE,CD=window.WOW_CHARACTER_DATA,CE=window.WOW_CHARACTER_ENGINE,T=window.WOW_TALENTS;
  const STEP=100,MAX_TIME=90000,BASE_RUN=7;
  const M=D.pvpMechanics?.v010;
  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  const round=(v,n=1)=>Number(v.toFixed(n));
  const same=(x,y)=>x.class===y.class&&x.spec===y.spec&&x.race===y.race&&x.gear===y.gear;

  const DEFAULT_ROGUE_POLICY=Object.freeze({
    id:'rogue_cb_hemo_champion_g0',version:1,
    vanishOnRoot:true,prepWhenRootedAndVanishDown:true,
    kickEnabled:true,kickMinRemainingMs:0,
    sprintMinRange:5.1,
    kidneyMinCp:5,kidneyEnergyReserve:0,
    evisMinCp:5,executeEvisHpPct:0,executeEvisMinCp:4,
    coldBloodMinCp:5,hemoMinEnergy:35
  });

  function normalizePolicy(p){
    const x={...DEFAULT_ROGUE_POLICY,...(p||{})};
    x.kickMinRemainingMs=clamp(Number(x.kickMinRemainingMs)||0,0,2500);
    x.sprintMinRange=clamp(Number(x.sprintMinRange)||5.1,5.1,40);
    x.kidneyMinCp=clamp(Math.round(Number(x.kidneyMinCp)||5),2,5);
    x.kidneyEnergyReserve=clamp(Math.round(Number(x.kidneyEnergyReserve)||0),0,75);
    x.evisMinCp=clamp(Math.round(Number(x.evisMinCp)||5),1,5);
    x.executeEvisHpPct=clamp(Number(x.executeEvisHpPct)||0,0,100);
    x.executeEvisMinCp=clamp(Math.round(Number(x.executeEvisMinCp)||4),1,5);
    x.coldBloodMinCp=clamp(Math.round(Number(x.coldBloodMinCp)||5),1,5);
    x.hemoMinEnergy=clamp(Math.round(Number(x.hemoMinEnergy)||35),35,100);
    return x;
  }
  function runtimePolicy(cfg){return normalizePolicy(cfg?.roguePolicy||window.WOW_ROGUE_LEARNER?.getChampionPolicy?.()||D.roguePolicyChampion||DEFAULT_ROGUE_POLICY);}
  function buildFor(side){return T?.get?.(side?.build)||D.pvpBuilds?.[side?.build]||null;}
  function supportedConfig(cfg){const k=D.pvpKernel&&D.pvpKernel.supported;return !!k&&same(cfg.a,k.a)&&same(cfg.b,k.b);}
  function canRun(cfg){
    const missing=[];
    if(!M)missing.push('v0.10 mechanics');
    if(!M?.crusader?.ppm)missing.push('Crusader PPM');
    if(!M?.bonescythe2p?.ppm)missing.push('Bonescythe 2p PPM');
    if(!D.pvpProfiles?.mage_frost_gnome_p6_core?.kernelReady)missing.push('Mage gear profile');
    if(!D.pvpProfiles?.rogue_sub_undead_p6_static?.kernelReady)missing.push('Rogue gear profile');
    if(!supportedConfig(cfg))missing.push('matchup not in exact kernel yet');
    return {ready:missing.length===0,missing};
  }

  function makeState(seed,cfg,policy){
    const rng=new E.RNG(seed),rp=D.profiles.rogue_subtlety_lvl60_pvp_bis_p6_baseline,rb=CE.rogue60Baseline(CD.level60.undeadRogue,rp),mp=D.pvpProfiles.mage_frost_gnome_p6_core;
    const rogueBuild=buildFor(cfg?.a)||D.pvpBuilds?.rogue_cb_hemo_21_3_27||{},mageBuild=buildFor(cfg?.b)||D.pvpBuilds?.mage_deep_frost_17_0_34||{};
    const rm=rogueBuild.modifiers||{},mm=mageBuild.modifiers||{};
    const mhItem=D.items[String(rp.slots['Main Hand'])].weapon,ohItem=D.items[String(rp.slots['Off Hand'])].weapon;
    const rogueCrit=19+(rb.stats.agi/29)+(rm.meleeCritPct||0),rogueDodge=(rb.stats.agi/14.5)+2;
    const mageArmor=Math.trunc(mp.stats.armorBeforeTalents+mp.stats.intellect*((mm.armorFromIntellectPct||50)/100));
    const barrier=D.pvpSpellbooks.Mage.iceBarrier,manaShield=D.pvpSpellbooks.Mage.manaShield;
    return {rng,time:0,range:5,timeline:[],winner:null,cfg,policy,
      rogue:{name:'Undead Rogue · Subtlety/Hemo',hp:rb.health,maxHp:rb.health,energy:100,maxEnergy:100,nextEnergy:2000,ap:rb.attackPower,armor:rb.armor,hit:rb.hitPct,crit:rogueCrit,dodge:rogueDodge,talents:rm,spellRangedHitPenaltyPct:rm.attackerSpellRangedHitPenaltyPct||0,
        mh:{min:rb.mainHand.min,max:rb.mainHand.max,speed:mhItem.speed,next:0},oh:{min:rb.offHandBeforeOffhandPenalty.min,max:rb.offHandBeforeOffhandPenalty.max,speed:ohItem.speed,next:200},combo:0,gcd:0,cd:{},stun:0,root:0,slow:0,slowPct:0,stealth:true,sprint:0,coldBlood:false,hemoCharges:0,hemoUntil:0,casting:null,hojReady:0,crusaderUntil:0,crusaderProcs:0,bonescytheHeals:0,initiativeProcs:0,ruthlessnessProcs:0,relentlessProcs:0,preparationUses:0,decisions:{}},
      mage:{name:'Gnome Mage · Frost',hp:mp.stats.health,maxHp:mp.stats.health,mana:mp.stats.mana,maxMana:mp.stats.mana,armor:mageArmor,dodge:mp.stats.dodgePct+(mp.utility?.arenaGrandMaster?.dodgePct||1),spellDamage:mp.stats.spellDamage,spellCrit:mp.stats.spellCritPct,talents:mm,frostHit:mp.stats.spellHitPct+(mm.frostFireHitPct||6),fireHit:mp.stats.spellHitPct+(mm.frostFireHitPct||6),gcd:0,cd:{},stun:0,root:0,slow:0,slowPct:0,casting:null,schoolLock:{Frost:0,Fire:0,Arcane:0},iceBlock:0,iceBarrier:barrier.absorbBase+mp.stats.spellDamage*barrier.spCoeff,manaShield:manaShield.absorbBase+(mp.gearEffects?.manaShieldBonusAbsorb||0),agmShield:0,mindNumbingUntil:0,elementalVulnerabilityUntil:0,mageArmor:true,resist:{...mp.stats.resist,arcane:(mp.stats.resist.arcane||0)+15,fire:(mp.stats.resist.fire||0)+15,frost:(mp.stats.resist.frost||0)+15,nature:(mp.stats.resist.nature||0)+15,shadow:(mp.stats.resist.shadow||0)+15}}
    };
  }

  function log(s,actor,text,kind='event'){s.timeline.push({t:round(s.time/1000,1),actor,text,kind});if(s.timeline.length>900)s.timeline.shift();}
  function decision(s,action,reason){s.rogue.decisions[action]=(s.rogue.decisions[action]||0)+1;log(s,'RoguePolicy',`${action} · ${reason}`,'decision');}
  function ready(s,u,key){return (u.cd[key]||0)<=s.time;}
  function setCd(s,u,key,ms){u.cd[key]=s.time+ms;}
  function gcdReady(s,u){return u.gcd<=s.time;}
  function spend(u,key,value){if((u[key]||0)<value)return false;u[key]-=value;return true;}
  function rand(s,min,max){return min+(max-min)*s.rng.next();}
  function rollPct(s,pct){return s.rng.next()*100<pct;}
  function alive(s){return s.rogue.hp>0&&s.mage.hp>0;}
  function mageCost(base,school){return (school==='Frost'||school==='Fire')?Math.trunc(base*(1-M.elementalPrecision.manaCostReductionPct/100)):base;}
  function mageCastTime(s,baseMs){return Math.round(baseMs*(s.mage.mindNumbingUntil>s.time?1.6:1));}
  function ppmPct(ppm,speed){return ppm*speed/60*100;}
  function currentRogueAP(s){return s.rogue.ap+(s.rogue.crusaderUntil>s.time?M.crusader.strength:0);}
  function weaponRoll(s,hand){const w=s.rogue[hand],delta=currentRogueAP(s)-s.rogue.ap;return rand(s,w.min,w.max)+(delta/14*w.speed);}
  function healRogue(s,min,max,label){const amount=rand(s,min,max),before=s.rogue.hp;s.rogue.hp=Math.min(s.rogue.maxHp,s.rogue.hp+amount);const healed=s.rogue.hp-before;if(healed>0)log(s,'Rogue',`${label} → +${Math.round(healed)} HP`,'heal');return healed;}
  function tryCrusader(s,hand){if(hand!=='mh')return;if(rollPct(s,ppmPct(M.crusader.ppm,s.rogue.mh.speed))){s.rogue.crusaderUntil=s.time+M.crusader.durationMs;s.rogue.crusaderProcs++;healRogue(s,M.crusader.healMin,M.crusader.healMax,'Crusader');log(s,'Rogue',`Crusader → +${M.crusader.strength} STR for ${M.crusader.durationMs/1000}s (1 PPM)`,'proc');}}
  function tryBonescythe2p(s,hand){const w=s.rogue[hand];if(rollPct(s,ppmPct(M.bonescythe2p.ppm,w.speed))){const h=healRogue(s,M.bonescythe2p.healMin,M.bonescythe2p.healMax,'Bonescythe 2p Invigorate');if(h>0)s.rogue.bonescytheHeals++;}}
  function tryFinisherTalents(s,cp){const r=s.rogue,t=r.talents||{};const relentlessPct=(t.relentlessChancePerComboPct||20)*cp;if(relentlessPct>0&&rollPct(s,relentlessPct)){r.energy=Math.min(r.maxEnergy,r.energy+(t.relentlessEnergy||25));r.relentlessProcs++;log(s,'Rogue',`Relentless Strikes → +${t.relentlessEnergy||25} Energy`,'proc');}if((t.ruthlessnessProcPct||0)>0&&rollPct(s,t.ruthlessnessProcPct)){r.combo=Math.min(5,r.combo+1);r.ruthlessnessProcs++;log(s,'Rogue','Ruthlessness → +1 combo point','proc');}}

  function absorbMage(s,amount,school){let left=amount,absorbed=0;if(s.mage.iceBlock>s.time)return {dealt:0,absorbed:amount};if(s.mage.iceBarrier>0){const a=Math.min(left,s.mage.iceBarrier);s.mage.iceBarrier-=a;left-=a;absorbed+=a;}if(left>0&&s.mage.agmShield>0){const a=Math.min(left,s.mage.agmShield);s.mage.agmShield-=a;left-=a;absorbed+=a;}if(left>0&&school==='Physical'&&s.mage.manaShield>0&&s.mage.mana>0){const a=Math.min(left,s.mage.manaShield,s.mage.mana/2);s.mage.manaShield-=a;s.mage.mana-=a*2;left-=a;absorbed+=a;}s.mage.hp=Math.max(0,s.mage.hp-left);return {dealt:left,absorbed};}
  function damageRogue(s,amount,spell,crit){s.rogue.hp=Math.max(0,s.rogue.hp-amount);log(s,'Mage',`${spell}${crit?' CRIT':''}: ${Math.round(amount)} dmg → Rogue ${Math.round(s.rogue.hp)} HP`,crit?'crit':'damage');}
  function damageMage(s,amount,spell,crit){const r=absorbMage(s,amount,'Physical');log(s,'Rogue',`${spell}${crit?' CRIT':''}: ${Math.round(amount)} raw, ${Math.round(r.absorbed)} absorb, ${Math.round(r.dealt)} HP dmg → Mage ${Math.round(s.mage.hp)} HP`,crit?'crit':'damage');return r;}
  function consumeHemoBonus(s,name,dmg){if(s.rogue.hemoCharges>0&&s.rogue.hemoUntil>s.time&&name!=='Hemorrhage'){s.rogue.hemoCharges--;return dmg+7;}return dmg;}
  function physicalSpecial(s,name,base,critMult=2,forceCrit=false,opts={}){const m=s.mage,r=s.rogue;if(m.iceBlock>s.time){log(s,'Rogue',`${name}: immune (Ice Block)`,'miss');return {hit:false};}const miss=E.sameLevelMeleeSpecialMiss(r.hit);if(rollPct(s,miss)){log(s,'Rogue',`${name}: MISS`,'miss');return {hit:false};}const stunned=m.stun>s.time;if(!stunned&&rollPct(s,m.dodge)){log(s,'Rogue',`${name}: DODGE`,'miss');return {hit:false};}let dmg=base*(1+(r.talents.murderDamagePct||2)/100);dmg*=1-E.physicalArmorReduction(m.armor,60);dmg=consumeHemoBonus(s,name,dmg);const crit=forceCrit||rollPct(s,r.crit);if(crit)dmg*=critMult;const dealt=damageMage(s,dmg,name,crit);if(opts.weaponHand&&dealt.dealt+dealt.absorbed>0)procWeaponEffects(s,opts.weaponHand,opts.allowHoJ!==false);return {hit:true,crit,dmg};}

  function applyCrippling(s){const p=M.poisons.cripplingII;s.mage.slow=s.time+p.durationMs;s.mage.slowPct=p.slowPct;log(s,'Rogue',`Crippling Poison II → Mage -${p.slowPct}% movement for ${p.durationMs/1000}s`,'control');}
  function applyMindNumbing(s){const p=M.poisons.mindNumbingIII;s.mage.mindNumbingUntil=s.time+p.durationMs;log(s,'Rogue',`Mind-numbing Poison III → Mage cast time +${p.castTimeIncreasePct}% for ${p.durationMs/1000}s`,'control');}
  function procWeaponEffects(s,hand,allowHoJ=true){if(hand==='mh'&&rollPct(s,M.poisons.cripplingII.procPct))applyCrippling(s);if(hand==='oh'&&rollPct(s,M.poisons.mindNumbingIII.procPct))applyMindNumbing(s);tryCrusader(s,hand);if(allowHoJ&&s.time>=s.rogue.hojReady&&rollPct(s,M.handOfJustice.procPct)){s.rogue.hojReady=s.time+M.handOfJustice.internalCooldownMs;log(s,'Rogue','Hand of Justice proc → extra main-hand attack','proc');rogueWhiteSwing(s,'mh',true);}}
  function rogueWhiteSwing(s,hand,isExtra=false){const r=s.rogue,m=s.mage,w=r[hand];if(r.stealth||r.stun>s.time||r.root>s.time||s.range>5||m.iceBlock>s.time)return false;const whiteMiss=Math.max(0,M.dualWield.baseSameLevelMissPct+M.dualWield.whitePenaltyPct-r.hit);if(rollPct(s,whiteMiss)){log(s,'Rogue',`${hand==='mh'?'MH':'OH'} auto: MISS`,'miss');return true;}if(m.stun<=s.time&&rollPct(s,m.dodge)){log(s,'Rogue',`${hand==='mh'?'MH':'OH'} auto: DODGE`,'miss');return true;}let dmg=weaponRoll(s,hand)*(hand==='oh'?M.dualWield.offhandDamageMultiplier:1)*(1+(r.talents.murderDamagePct||2)/100);dmg*=1-E.physicalArmorReduction(m.armor,60);dmg=consumeHemoBonus(s,`${hand==='mh'?'MH':'OH'} auto`,dmg);const crit=rollPct(s,r.crit);if(crit)dmg*=2;const dealt=damageMage(s,dmg,`${hand==='mh'?'MH':'OH'} auto${isExtra?' (extra)':''}`,crit);if(dealt.dealt+dealt.absorbed>0){procWeaponEffects(s,hand,!isExtra);tryBonescythe2p(s,hand);}return true;}
  function processAutos(s){const r=s.rogue;if(r.stealth||r.stun>s.time||r.root>s.time||s.range>5)return;if(r.mh.next<=s.time){rogueWhiteSwing(s,'mh');r.mh.next=s.time+Math.round(r.mh.speed*1000);}if(r.oh.next<=s.time){rogueWhiteSwing(s,'oh');r.oh.next=s.time+Math.round(r.oh.speed*1000);}}

  function spellHit(s,school){const hit=school==='Frost'?s.mage.frostHit:s.mage.fireHit;const effectiveHit=hit-(s.rogue.spellRangedHitPenaltyPct||0);return !rollPct(s,E.sameLevelSpellMiss(effectiveHit));}
  function spellDamage(s,key,{frozenBonus=true}={}){const sp=D.pvpSpellbooks.Mage[key],r=s.rogue,m=s.mage;if(!spellHit(s,sp.school)){log(s,'Mage',`${sp.name}: RESIST/MISS`,'miss');return {hit:false};}let bonusSP=0;if(m.elementalVulnerabilityUntil>s.time){bonusSP=M.frostfire6p.bonusSpellPowerForNextHit;m.elementalVulnerabilityUntil=0;log(s,'Mage',`Elemental Vulnerability consumed → +${bonusSP} effective spell power`,'proc');}let dmg=rand(s,sp.damage[0],sp.damage[1])+(m.spellDamage+bonusSP)*sp.spCoeff;if(sp.school==='Frost')dmg*=1+(m.talents.frostDamagePct||6)/100;if(key==='coneOfCold')dmg*=1+(m.talents.coneOfColdDamagePct||35)/100;let critChance=m.spellCrit;if(sp.school==='Frost'&&frozenBonus&&r.root>s.time)critChance+=(m.talents.frozenCritBonusPct||50);const crit=rollPct(s,critChance);if(crit)dmg*=sp.school==='Frost'?(m.talents.frostCritMultiplier||2):1.5;damageRogue(s,dmg,sp.name,crit);if(key==='frostbolt'){r.slow=s.time+(9000+(m.talents.chillDurationBonusMs||3000));r.slowPct=40+(m.talents.chillSlowBonusPct||10);}if(key==='coneOfCold'){r.slow=s.time+(8000+(m.talents.chillDurationBonusMs||3000));r.slowPct=50+(m.talents.chillSlowBonusPct||10);}if(rollPct(s,M.frostfire6p.procPct)){m.elementalVulnerabilityUntil=s.time+M.frostfire6p.debuffMs;log(s,'Mage','Frostfire 6p → Elemental Vulnerability primed for next damaging spell','proc');}return {hit:true,crit,dmg};}

  function rogueCheapShot(s){const r=s.rogue,sp=D.pvpSpellbooks.Rogue.cheapShot,cost=r.talents.cheapShotEnergy||40;if(!sp||!gcdReady(s,r)||!r.stealth||s.range>5)return false;if(!spend(r,'energy',cost))return false;r.gcd=s.time+1000;r.stealth=false;let cp=2;if((r.talents.initiativeProcPct||0)>0&&rollPct(s,r.talents.initiativeProcPct)){cp++;r.initiativeProcs++;log(s,'Rogue','Initiative → Cheap Shot gains +1 combo point','proc');}r.combo=Math.min(5,r.combo+cp);s.mage.stun=s.time+4000;log(s,'Rogue',`Cheap Shot → 4.0s stun, ${cp} CP (${cost} Energy)`,'control');return true;}
  function rogueHemo(s){const r=s.rogue;if(!gcdReady(s,r)||s.range>5||r.energy<35)return false;r.energy-=35;r.gcd=s.time+1000;const base=weaponRoll(s,'mh');const hit=physicalSpecial(s,'Hemorrhage',base,r.talents.hemorrhageCritMultiplier||r.talents.builderCritMultiplier||2.3,false,{weaponHand:'mh'});if(hit.hit){r.combo=Math.min(5,r.combo+1);r.hemoCharges=30;r.hemoUntil=s.time+15000;if(hit.crit)r.energy=Math.min(100,r.energy+M.bonescythe4p.energyOnBuilderCrit);}return true;}
  function rogueKidney(s){const r=s.rogue,m=s.mage;if(!gcdReady(s,r)||s.range>5||r.combo<2||r.energy<25||!ready(s,r,'kidney'))return false;const cp=r.combo;r.energy-=25;r.combo=0;r.gcd=s.time+1000;setCd(s,r,'kidney',20000);tryFinisherTalents(s,cp);if(rollPct(s,E.sameLevelMeleeSpecialMiss(r.hit))){log(s,'Rogue','Kidney Shot: MISS','miss');return true;}if(m.stun<=s.time&&rollPct(s,m.dodge)){log(s,'Rogue','Kidney Shot: DODGE','miss');return true;}m.stun=s.time+(cp+1)*1000;log(s,'Rogue',`Kidney Shot ${cp} CP → ${cp+1}.0s stun (separate DR from Cheap Shot)`,'control');return true;}
  function rogueEvis(s){const r=s.rogue;if(!gcdReady(s,r)||s.range>5||r.combo<1||r.energy<35)return false;const cp=r.combo,sp=D.pvpSpellbooks.Rogue.eviscerate,range=sp.baseByCombo[cp];r.energy-=35;r.combo=0;r.gcd=s.time+1000;const base=(rand(s,range[0],range[1])+currentRogueAP(s)*0.03*cp)*(1+(r.talents.eviscerateDamagePct||15)/100);const force=r.coldBlood;r.coldBlood=false;physicalSpecial(s,'Eviscerate',base,2,force);tryFinisherTalents(s,cp);return true;}
  function rogueColdBlood(s){const r=s.rogue;if(!ready(s,r,'coldBlood')||r.coldBlood||!r.talents.coldBlood)return false;r.coldBlood=true;setCd(s,r,'coldBlood',180000);log(s,'Rogue','Cold Blood → next eligible attack guaranteed crit','buff');return true;}
  function rogueKick(s){const r=s.rogue,m=s.mage;if(s.range>5||!m.casting||r.energy<25||!ready(s,r,'kick')||!gcdReady(s,r))return false;r.energy-=25;r.gcd=s.time+1000;setCd(s,r,'kick',10000);const school=m.casting.school;m.casting=null;if(m.schoolLock[school]!==undefined)m.schoolLock[school]=s.time+5000;physicalSpecial(s,'Kick',80,2,false);log(s,'Rogue',school==='Physical'?'Kick → cast interrupted':`Kick → ${school} locked 5.0s`,'control');return true;}
  function rogueVanish(s){const r=s.rogue;if(!ready(s,r,'vanish'))return false;const cd=Math.max(0,300000-(r.talents.elusivenessCooldownReductionMs||0));setCd(s,r,'vanish',cd);r.root=0;r.slow=0;r.slowPct=0;r.stealth=true;log(s,'Rogue',`Vanish → root/slow removed, Stealth · CD ${cd/1000}s`,'control');return true;}
  function rogueSprint(s){const r=s.rogue;if(!ready(s,r,'sprint'))return false;setCd(s,r,'sprint',300000);r.sprint=s.time+15000;log(s,'Rogue','Sprint → +70% movement for 15s','movement');return true;}
  function roguePreparation(s){const r=s.rogue,sp=D.pvpSpellbooks.Rogue.preparation;if(!r.talents.preparation||!sp||!ready(s,r,'preparation')||!gcdReady(s,r))return false;setCd(s,r,'preparation',sp.cooldownMs||600000);r.gcd=s.time+(sp.gcdMs||1000);['vanish','sprint','kick','kidney','coldBlood'].forEach(k=>r.cd[k]=s.time);r.preparationUses++;log(s,'Rogue','Preparation → Rogue-family cooldowns reset (Preparation excluded)','control');return true;}

  function mageBlink(s){const m=s.mage;if(!ready(s,m,'blink')||m.mana<446||m.schoolLock.Arcane>s.time)return false;m.mana-=446;setCd(s,m,'blink',13500);m.gcd=s.time+1500;m.stun=0;m.root=0;s.range=clamp(s.range+20,0,40);log(s,'Mage',`Blink (PvP 3p: 13.5s CD) → range ${round(s.range)} yd`,'movement');return true;}
  function mageNova(s){const m=s.mage,sp=D.pvpSpellbooks.Mage.frostNova,cost=mageCost(sp.cost,'Frost');if(!gcdReady(s,m)||!ready(s,m,'nova')||m.schoolLock.Frost>s.time||m.mana<cost||s.range>10)return false;m.mana-=cost;m.gcd=s.time+1500;setCd(s,m,'nova',m.talents.frostNovaCooldownMs||21000);const result=spellDamage(s,'frostNova',{frozenBonus:false});if(result.hit){s.rogue.root=s.time+8000;log(s,'Mage','Frost Nova → Rogue rooted 8.0s','control');}return true;}
  function mageCone(s){const m=s.mage,sp=D.pvpSpellbooks.Mage.coneOfCold,cost=mageCost(sp.cost,'Frost');if(!gcdReady(s,m)||!ready(s,m,'cone')||m.schoolLock.Frost>s.time||m.mana<cost||s.range>10)return false;m.mana-=cost;m.gcd=s.time+1500;setCd(s,m,'cone',10000);spellDamage(s,'coneOfCold');return true;}
  function mageFireBlast(s){const m=s.mage,sp=D.pvpSpellbooks.Mage.fireBlast,cost=mageCost(sp.cost,'Fire');if(!gcdReady(s,m)||!ready(s,m,'fireBlast')||m.schoolLock.Fire>s.time||m.mana<cost||s.range>20)return false;m.mana-=cost;m.gcd=s.time+1500;setCd(s,m,'fireBlast',8000);spellDamage(s,'fireBlast',{frozenBonus:false});return true;}
  function startFrostbolt(s){const m=s.mage,sp=D.pvpSpellbooks.Mage.frostbolt,cost=mageCost(sp.cost,'Frost');if(!gcdReady(s,m)||m.casting||m.schoolLock.Frost>s.time||m.mana<cost||s.range>30)return false;m.mana-=cost;m.gcd=s.time+1500;const castMs=mageCastTime(s,m.talents.frostboltCastMs||2500);m.casting={key:'frostbolt',school:'Frost',end:s.time+castMs,range:30};log(s,'Mage',`Frostbolt cast started (${(castMs/1000).toFixed(1)}s${castMs>(m.talents.frostboltCastMs||2500)?' · Mind-numbing':''})`,'cast');return true;}
  function startEscapeArtist(s){const m=s.mage,sp=D.pvpSpellbooks.Mage.escapeArtist;if(!gcdReady(s,m)||m.casting||!ready(s,m,'escapeArtist')||(m.root<=s.time&&m.slow<=s.time))return false;setCd(s,m,'escapeArtist',sp.cooldownMs);m.gcd=s.time+sp.gcdMs;const castMs=mageCastTime(s,sp.castMs);m.casting={key:'escapeArtist',school:'Physical',end:s.time+castMs,range:0};log(s,'Mage',`Escape Artist cast started (${(castMs/1000).toFixed(1)}s)`,'cast');return true;}
  function completeMageCast(s){const c=s.mage.casting;if(!c||c.end>s.time)return;s.mage.casting=null;if(c.key==='escapeArtist'){s.mage.root=0;s.mage.slow=0;s.mage.slowPct=0;log(s,'Mage','Escape Artist → roots/snares removed','control');return;}if(s.range>c.range){log(s,'Mage','Frostbolt failed: out of range','miss');return;}spellDamage(s,c.key);}
  function mageBarrier(s){const m=s.mage,sp=D.pvpSpellbooks.Mage.iceBarrier,cost=mageCost(sp.cost,'Frost');if(!gcdReady(s,m)||!ready(s,m,'barrier')||m.schoolLock.Frost>s.time||m.mana<cost)return false;m.mana-=cost;m.gcd=s.time+1500;setCd(s,m,'barrier',sp.cooldownMs);m.iceBarrier=sp.absorbBase+m.spellDamage*sp.spCoeff;log(s,'Mage',`Ice Barrier R4 → ${Math.round(m.iceBarrier)} absorb`,'buff');return true;}
  function mageManaShield(s){const m=s.mage,sp=D.pvpSpellbooks.Mage.manaShield;if(!gcdReady(s,m)||m.schoolLock.Arcane>s.time||m.mana<sp.cost)return false;m.mana-=sp.cost;m.gcd=s.time+1500;m.manaShield=sp.absorbBase+(D.pvpProfiles.mage_frost_gnome_p6_core.gearEffects?.manaShieldBonusAbsorb||0);log(s,'Mage',`Mana Shield R6 + PvP gloves → ${Math.round(m.manaShield)} physical absorb`,'buff');return true;}
  function mageAGM(s){const m=s.mage;if(!ready(s,m,'agm'))return false;setCd(s,m,'agm',1800000);m.agmShield=rand(s,750,1250);log(s,'Mage',`Arena Grand Master → ${Math.round(m.agmShield)} absorb`,'buff');return true;}
  function mageIceBlock(s){const m=s.mage;if(!gcdReady(s,m)||!ready(s,m,'iceBlock')||m.schoolLock.Frost>s.time||m.mana<15||!m.talents.iceBlock)return false;m.mana-=15;m.gcd=s.time+1500;setCd(s,m,'iceBlock',300000);m.iceBlock=s.time+2500;m.stun=0;m.root=0;log(s,'Mage','Ice Block → immune; policy cancels after 2.5s (max duration 10s)','control');return true;}
  function mageColdSnap(s){const m=s.mage;if(!ready(s,m,'coldSnap')||!m.talents.coldSnap)return false;setCd(s,m,'coldSnap',600000);['nova','cone','barrier','iceBlock'].forEach(k=>m.cd[k]=s.time);log(s,'Mage','Cold Snap → Frost cooldowns reset','control');return true;}

  function chooseRogue(s){
    const r=s.rogue,m=s.mage,p=s.policy;if(r.stun>s.time)return;
    if(r.root>s.time){if(p.vanishOnRoot&&ready(s,r,'vanish')){decision(s,'Vanish','break root / reopen');rogueVanish(s);return;}if(p.prepWhenRootedAndVanishDown&&ready(s,r,'preparation')&&r.talents.preparation){decision(s,'Preparation','Vanish unavailable while rooted');roguePreparation(s);return;}return;}
    if(r.stealth){if(s.range<=5){decision(s,'Cheap Shot','stealth opener');rogueCheapShot(s);}return;}
    if(s.range>5){if(ready(s,r,'sprint')&&r.sprint<=s.time&&s.range>=p.sprintMinRange){decision(s,'Sprint',`recover range at ${round(s.range,1)} yd`);rogueSprint(s);}return;}
    if(m.iceBlock>s.time)return;
    if(m.casting&&p.kickEnabled){const remaining=m.casting.end-s.time;if(remaining>=p.kickMinRemainingMs&&rogueKick(s)){decision(s,'Kick',`interrupt with ${remaining}ms remaining`);return;}}
    if(r.combo>=p.kidneyMinCp&&m.stun<=s.time&&r.energy>=25+p.kidneyEnergyReserve&&ready(s,r,'kidney')){decision(s,'Kidney Shot',`${r.combo} CP control`);rogueKidney(s);return;}
    const execute=m.hp/m.maxHp*100<=p.executeEvisHpPct&&r.combo>=p.executeEvisMinCp;
    if((r.combo>=p.evisMinCp||execute)&&r.energy>=35){if(r.combo>=p.coldBloodMinCp&&ready(s,r,'coldBlood')&&r.talents.coldBlood){decision(s,'Cold Blood',`${r.combo} CP finisher setup`);rogueColdBlood(s);}decision(s,'Eviscerate',`${r.combo} CP${execute?' execute':''}`);rogueEvis(s);return;}
    if(r.energy>=p.hemoMinEnergy){decision(s,'Hemorrhage',`builder at ${Math.round(r.energy)} Energy`);rogueHemo(s);}
  }
  function chooseMage(s){const m=s.mage,r=s.rogue;if(m.iceBlock>s.time)return;if(m.casting)return;if(m.stun>s.time){if(s.range<=5)mageBlink(s);return;}if((m.root>s.time||m.slow>s.time)&&ready(s,m,'escapeArtist')&&startEscapeArtist(s))return;if(m.hp/m.maxHp<0.28&&ready(s,m,'iceBlock')){mageIceBlock(s);return;}if(m.hp/m.maxHp<0.65&&ready(s,m,'agm')){mageAGM(s);return;}if(s.range<=6&&ready(s,m,'blink')&&mageBlink(s))return;if(m.iceBarrier<=0&&ready(s,m,'barrier')&&mageBarrier(s))return;if(m.manaShield<=0&&s.range<=8&&mageManaShield(s))return;if(s.range<=10&&r.root<=s.time&&ready(s,m,'nova')&&mageNova(s))return;if(s.range<=10&&ready(s,m,'cone')&&mageCone(s))return;if(s.range<=20&&ready(s,m,'fireBlast')&&mageFireBlast(s))return;if(s.range<=12&&(!ready(s,m,'nova')||!ready(s,m,'barrier'))&&ready(s,m,'coldSnap')){mageColdSnap(s);return;}if(s.range<=30)startFrostbolt(s);}
  function rogueSpeed(s){const r=s.rogue;if(r.stun>s.time||r.root>s.time)return 0;let pct=r.sprint>s.time?1.70:1.08;if(r.stealth)pct*=0.70;if(r.slow>s.time)pct*=Math.max(0,1-r.slowPct/100);return BASE_RUN*pct;}
  function mageSpeed(s){const m=s.mage;if(m.stun>s.time||m.root>s.time||m.casting||m.iceBlock>s.time)return 0;let pct=1;if(m.slow>s.time)pct*=Math.max(0,1-m.slowPct/100);return BASE_RUN*pct;}
  function move(s){if(s.rogue.stealth&&s.time===0)return;const dt=STEP/1000;s.range=clamp(s.range+(mageSpeed(s)-rogueSpeed(s))*dt,0,40);}
  function resources(s){while(s.time>=s.rogue.nextEnergy){s.rogue.energy=Math.min(100,s.rogue.energy+20);s.rogue.nextEnergy+=2000;}}
  function finish(s){if(s.rogue.hp<=0&&s.mage.hp<=0)s.winner='Draw';else if(s.mage.hp<=0)s.winner='Rogue';else if(s.rogue.hp<=0)s.winner='Mage';else s.winner='Timeout';log(s,'System',`WINNER: ${s.winner}`,'winner');return {seed:s.rng.state,winner:s.winner,duration:round(s.time/1000,1),timeline:s.timeline,policy:{...s.policy},decisions:{...s.rogue.decisions},final:{rogue:{hp:Math.round(s.rogue.hp),maxHp:s.rogue.maxHp,energy:Math.round(s.rogue.energy),combo:s.rogue.combo,crusaderProcs:s.rogue.crusaderProcs,bonescytheHeals:s.rogue.bonescytheHeals,initiativeProcs:s.rogue.initiativeProcs,ruthlessnessProcs:s.rogue.ruthlessnessProcs,relentlessProcs:s.rogue.relentlessProcs,preparationUses:s.rogue.preparationUses},mage:{hp:Math.round(s.mage.hp),maxHp:s.mage.maxHp,mana:Math.round(s.mage.mana),maxMana:s.mage.maxMana},range:round(s.range,1)},talentRuntime:{initiativePct:s.rogue.talents.initiativeProcPct||0,ruthlessnessPct:s.rogue.talents.ruthlessnessProcPct||0,preparation:!!s.rogue.talents.preparation,elusivenessMs:s.rogue.talents.elusivenessCooldownReductionMs||0,heightenedSensesHitPenaltyPct:s.rogue.spellRangedHitPenaltyPct},calibrationRequired:[]};}
  function runWithPolicy(seed,cfg,policy){const gate=canRun(cfg);if(!gate.ready)return {error:'STRICT_DATA_GATE',missing:gate.missing};const p=normalizePolicy(policy),s=makeState(seed,cfg,p);log(s,'System',`v0.22 policy-driven precise duel · ${p.id}`,'start');for(;s.time<=MAX_TIME&&alive(s);s.time+=STEP){resources(s);completeMageCast(s);if(!alive(s))break;chooseRogue(s);if(!alive(s))break;processAutos(s);if(!alive(s))break;chooseMage(s);if(!alive(s))break;move(s);}return finish(s);}
  function run(seed,cfg){return runWithPolicy(seed,cfg,runtimePolicy(cfg));}
  function batchWithPolicy(seed,count,cfg,policy){const gate=canRun(cfg);if(!gate.ready)return {error:'STRICT_DATA_GATE',missing:gate.missing};const n=clamp(Number(count)||1000,1,100000),wins={Rogue:0,Mage:0,Draw:0,Timeout:0};let duration=0,rogueHp=0,mageHp=0;const base=(Number(seed)||1)>>>0,p=normalizePolicy(policy);for(let i=0;i<n;i++){const r=runWithPolicy((base+Math.imul(i+1,2654435761))>>>0,cfg,p);wins[r.winner]=(wins[r.winner]||0)+1;duration+=r.duration;rogueHp+=r.final.rogue.hp/r.final.rogue.maxHp;mageHp+=r.final.mage.hp/r.final.mage.maxHp;}const rates=Object.fromEntries(Object.entries(wins).map(([k,v])=>[k,round(v*100/n,3)]));const avgRogueHpPct=round(rogueHp*100/n,3),avgMageHpPct=round(mageHp*100/n,3);const score=round(rates.Rogue*100+(avgRogueHpPct-avgMageHpPct)-rates.Timeout*2,4);return {count:n,wins,rates,avgDuration:round(duration/n,3),avgRogueHpPct,avgMageHpPct,score,policy:p};}
  function batch(seed,count,cfg){return batchWithPolicy(seed,count,cfg,runtimePolicy(cfg));}
  function comparePolicies(seed,count,cfg,champion,challenger){const a=batchWithPolicy(seed,count,cfg,champion),b=batchWithPolicy(seed,count,cfg,challenger);if(a.error||b.error)return {error:'STRICT_DATA_GATE',champion:a,challenger:b};return {count:a.count,champion:a,challenger:b,deltaScore:round(b.score-a.score,4),deltaWinRate:round(b.rates.Rogue-a.rates.Rogue,3),promote:b.score>a.score&&b.rates.Rogue>=a.rates.Rogue};}
  function selfTest(cfg){const p=runtimePolicy(cfg),a=runWithPolicy(1337,cfg,p),b=runWithPolicy(1337,cfg,p);return {deterministic:JSON.stringify(a)===JSON.stringify(b),winner:a.winner,duration:a.duration,version:'0.22.0',policy:p.id};}
  return {version:'0.22.0',canRun,run,runWithPolicy,batch,batchWithPolicy,comparePolicies,selfTest,defaultRoguePolicy:{...DEFAULT_ROGUE_POLICY},normalizeRoguePolicy:normalizePolicy,constants:{baseRunYdPerSec:BASE_RUN,stepMs:STEP,maxTimeMs:MAX_TIME}};
})();
