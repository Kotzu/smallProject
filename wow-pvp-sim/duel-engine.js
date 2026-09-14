window.WOW_DUEL=(function(){
  const D=window.WOW_DATA,E=window.WOW_ENGINE,CD=window.WOW_CHARACTER_DATA,CE=window.WOW_CHARACTER_ENGINE;
  const STEP=100,MAX_TIME=90000,BASE_RUN=7;
  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  const round=(v,n=1)=>Number(v.toFixed(n));
  const same=(x,y)=>x.class===y.class&&x.spec===y.spec&&x.race===y.race&&x.gear===y.gear;

  function supportedConfig(cfg){
    const k=D.pvpKernel&&D.pvpKernel.supported;
    return !!k&&same(cfg.a,k.a)&&same(cfg.b,k.b);
  }
  function canRun(cfg){
    const missing=[];
    if(!D.pvpBuilds?.rogue_cb_hemo_21_3_27)missing.push('Rogue PvP build');
    if(!D.pvpBuilds?.mage_deep_frost_17_0_34)missing.push('Mage PvP build');
    if(!D.pvpProfiles?.mage_frost_gnome_p6_core?.kernelReady)missing.push('Mage gear profile');
    if(!D.pvpProfiles?.rogue_sub_undead_p6_static?.kernelReady)missing.push('Rogue gear profile');
    if(!supportedConfig(cfg))missing.push('matchup not in exact kernel yet');
    return {ready:missing.length===0,missing};
  }

  function makeState(seed){
    const rng=new E.RNG(seed);
    const rp=D.profiles.rogue_subtlety_lvl60_pvp_bis_p6_baseline;
    const rb=CE.rogue60Baseline(CD.level60.undeadRogue,rp);
    const mp=D.pvpProfiles.mage_frost_gnome_p6_core;
    const rogueCrit=19+(rb.stats.agi/29)+5;
    const mageArmor=Math.trunc(mp.stats.armorBeforeTalents+mp.stats.intellect*0.50);
    return {
      rng,time:0,range:5,timeline:[],winner:null,
      rogue:{
        name:'Undead Rogue · Subtlety/Hemo',hp:rb.health,maxHp:rb.health,energy:100,maxEnergy:100,nextEnergy:2000,
        ap:rb.attackPower,armor:rb.armor,hit:rb.hitPct,crit:rogueCrit,dodge:14.4828+((132)/14.5),
        mh:{min:rb.mainHand.min,max:rb.mainHand.max,speed:D.items[String(rp.slots['Main Hand'])].weapon.speed},
        combo:0,gcd:0,cd:{},stun:0,root:0,slow:0,slowPct:0,stealth:true,sprint:0,coldBlood:false,
        hemoCharges:0,hemoUntil:0,casting:null
      },
      mage:{
        name:'Gnome Mage · Frost',hp:mp.stats.health,maxHp:mp.stats.health,mana:mp.stats.mana,maxMana:mp.stats.mana,
        armor:mageArmor,dodge:mp.stats.dodgePct+1,spellDamage:mp.stats.spellDamage,spellCrit:mp.stats.spellCritPct,
        frostHit:mp.stats.spellHitPct+6,fireHit:mp.stats.spellHitPct+6,gcd:0,cd:{},stun:0,root:0,slow:0,slowPct:0,
        casting:null,schoolLock:{Frost:0,Fire:0,Arcane:0},iceBlock:0,
        iceBarrier:455+mp.stats.spellDamage*0.10,manaShield:570,agmShield:0
      }
    };
  }

  function log(s,actor,text,kind='event'){
    s.timeline.push({t:round(s.time/1000,1),actor,text,kind});
    if(s.timeline.length>500)s.timeline.shift();
  }
  function ready(s,u,key){return (u.cd[key]||0)<=s.time;}
  function setCd(s,u,key,ms){u.cd[key]=s.time+ms;}
  function gcdReady(s,u){return u.gcd<=s.time;}
  function spend(u,key,value){if((u[key]||0)<value)return false;u[key]-=value;return true;}
  function rand(s,min,max){return min+(max-min)*s.rng.next();}
  function rollPct(s,pct){return s.rng.next()*100<pct;}
  function alive(s){return s.rogue.hp>0&&s.mage.hp>0;}

  function absorbMage(s,amount,school){
    let left=amount,absorbed=0;
    if(s.mage.iceBlock>s.time)return {dealt:0,absorbed:amount};
    if(s.mage.iceBarrier>0){const a=Math.min(left,s.mage.iceBarrier);s.mage.iceBarrier-=a;left-=a;absorbed+=a;}
    if(left>0&&s.mage.agmShield>0){const a=Math.min(left,s.mage.agmShield);s.mage.agmShield-=a;left-=a;absorbed+=a;}
    if(left>0&&school==='Physical'&&s.mage.manaShield>0&&s.mage.mana>0){
      const a=Math.min(left,s.mage.manaShield,s.mage.mana/2);s.mage.manaShield-=a;s.mage.mana-=a*2;left-=a;absorbed+=a;
    }
    s.mage.hp=Math.max(0,s.mage.hp-left);
    return {dealt:left,absorbed};
  }
  function damageRogue(s,amount,spell,crit){
    s.rogue.hp=Math.max(0,s.rogue.hp-amount);
    log(s,'Mage',`${spell}${crit?' CRIT':''}: ${Math.round(amount)} dmg → Rogue ${Math.round(s.rogue.hp)} HP`,crit?'crit':'damage');
  }
  function damageMage(s,amount,spell,crit){
    const r=absorbMage(s,amount,'Physical');
    log(s,'Rogue',`${spell}${crit?' CRIT':''}: ${Math.round(amount)} raw, ${Math.round(r.absorbed)} absorb, ${Math.round(r.dealt)} HP dmg → Mage ${Math.round(s.mage.hp)} HP`,crit?'crit':'damage');
  }

  function physicalSpecial(s,name,base,critMult=2,forceCrit=false){
    const m=s.mage;
    if(m.iceBlock>s.time){log(s,'Rogue',`${name}: immune (Ice Block)`,'miss');return {hit:false};}
    const miss=E.sameLevelMeleeSpecialMiss(s.rogue.hit);
    if(rollPct(s,miss)){log(s,'Rogue',`${name}: MISS`,'miss');return {hit:false};}
    const stunned=m.stun>s.time;
    if(!stunned&&rollPct(s,m.dodge)){log(s,'Rogue',`${name}: DODGE`,'miss');return {hit:false};}
    let dmg=base*1.02; // Murder 2/2 applies against players (Humanoid).
    const red=E.physicalArmorReduction(m.armor,60);dmg*=1-red;
    if(s.rogue.hemoCharges>0&&s.rogue.hemoUntil>s.time&&name!=='Hemorrhage'){dmg+=7;s.rogue.hemoCharges--;}
    const crit=forceCrit||rollPct(s,s.rogue.crit);if(crit)dmg*=critMult;
    damageMage(s,dmg,name,crit);return {hit:true,crit,dmg};
  }

  function spellHit(s,school){return !rollPct(s,E.sameLevelSpellMiss(school==='Frost'?s.mage.frostHit:s.mage.fireHit));}
  function spellDamage(s,key,{frozenBonus=true}={}){
    const sp=D.pvpSpellbooks.Mage[key],r=s.rogue;
    if(!spellHit(s,sp.school)){log(s,'Mage',`${sp.name}: RESIST/MISS`,'miss');return;}
    let dmg=rand(s,sp.damage[0],sp.damage[1])+s.mage.spellDamage*sp.spCoeff;
    if(sp.school==='Frost')dmg*=1.06;
    if(key==='coneOfCold')dmg*=1.35;
    let critChance=s.mage.spellCrit;
    if(sp.school==='Frost'&&frozenBonus&&r.root>s.time)critChance+=50;
    const crit=rollPct(s,critChance);
    if(crit)dmg*=sp.school==='Frost'?2:1.5;
    damageRogue(s,dmg,sp.name,crit);
    if(key==='frostbolt'){r.slow=s.time+12000;r.slowPct=50;}
    if(key==='coneOfCold'){r.slow=s.time+11000;r.slowPct=60;}
  }

  function rogueCheapShot(s){
    const sp=D.pvpSpellbooks.Rogue.cheapShot;if(!sp||!gcdReady(s,s.rogue)||!s.rogue.stealth||s.range>5)return false;
    if(!spend(s.rogue,'energy',40))return false;
    s.rogue.gcd=s.time+1000;s.rogue.stealth=false;s.rogue.combo=Math.min(5,s.rogue.combo+2);s.mage.stun=s.time+4000;
    log(s,'Rogue','Cheap Shot → 4.0s stun, 2 CP','control');return true;
  }
  function rogueHemo(s){
    if(!gcdReady(s,s.rogue)||s.range>5||s.rogue.energy<35)return false;
    s.rogue.energy-=35;s.rogue.gcd=s.time+1000;
    const base=rand(s,s.rogue.mh.min,s.rogue.mh.max);
    const hit=physicalSpecial(s,'Hemorrhage',base,2.3,false);
    if(hit.hit){s.rogue.combo=Math.min(5,s.rogue.combo+1);s.rogue.hemoCharges=30;s.rogue.hemoUntil=s.time+15000;if(hit.crit)s.rogue.energy=Math.min(100,s.rogue.energy+5);}
    return true;
  }
  function rogueKidney(s){
    if(!gcdReady(s,s.rogue)||s.range>5||s.rogue.combo<2||s.rogue.energy<25||!ready(s,s.rogue,'kidney'))return false;
    const cp=s.rogue.combo;s.rogue.energy-=25;s.rogue.combo=0;s.rogue.gcd=s.time+1000;setCd(s,s.rogue,'kidney',20000);
    if(E.sameLevelMeleeSpecialMiss(s.rogue.hit)>0&&rollPct(s,E.sameLevelMeleeSpecialMiss(s.rogue.hit))){log(s,'Rogue','Kidney Shot: MISS','miss');return true;}
    if(rollPct(s,s.mage.dodge)){log(s,'Rogue','Kidney Shot: DODGE','miss');return true;}
    s.mage.stun=s.time+(cp+1)*1000;
    if(rollPct(s,cp*20))s.rogue.energy=Math.min(100,s.rogue.energy+25);
    log(s,'Rogue',`Kidney Shot ${cp} CP → ${cp+1}.0s stun`,'control');return true;
  }
  function rogueEvis(s){
    if(!gcdReady(s,s.rogue)||s.range>5||s.rogue.combo<1||s.rogue.energy<35)return false;
    const cp=s.rogue.combo,sp=D.pvpSpellbooks.Rogue.eviscerate,range=sp.baseByCombo[cp];
    s.rogue.energy-=35;s.rogue.combo=0;s.rogue.gcd=s.time+1000;
    const base=(rand(s,range[0],range[1])+s.rogue.ap*0.03*cp)*1.15;
    const force=s.rogue.coldBlood;s.rogue.coldBlood=false;
    physicalSpecial(s,'Eviscerate',base,2,force);
    if(rollPct(s,cp*20))s.rogue.energy=Math.min(100,s.rogue.energy+25);
    return true;
  }
  function rogueColdBlood(s){
    if(!ready(s,s.rogue,'coldBlood')||s.rogue.coldBlood)return false;
    s.rogue.coldBlood=true;setCd(s,s.rogue,'coldBlood',180000);log(s,'Rogue','Cold Blood → next eligible attack guaranteed crit','buff');return true;
  }
  function rogueKick(s){
    const r=s.rogue,m=s.mage;if(s.range>5||!m.casting||r.energy<25||!ready(s,r,'kick')||!gcdReady(s,r))return false;
    r.energy-=25;r.gcd=s.time+1000;setCd(s,r,'kick',10000);
    const school=m.casting.school;m.casting=null;m.schoolLock[school]=s.time+5000;
    physicalSpecial(s,'Kick',80,2,false);log(s,'Rogue',`Kick → ${school} locked 5.0s`,'control');return true;
  }
  function rogueVanish(s){
    const r=s.rogue;if(!ready(s,r,'vanish'))return false;setCd(s,r,'vanish',300000);r.root=0;r.slow=0;r.slowPct=0;r.stealth=true;log(s,'Rogue','Vanish → root/slow removed, Stealth','control');return true;
  }
  function rogueSprint(s){
    const r=s.rogue;if(!ready(s,r,'sprint'))return false;setCd(s,r,'sprint',300000);r.sprint=s.time+15000;log(s,'Rogue','Sprint → 170% run speed for 15s','movement');return true;
  }

  function mageBlink(s){
    const m=s.mage,sp=D.pvpSpellbooks.Mage.blink;if(!ready(s,m,'blink')||m.mana<446||m.schoolLock.Arcane>s.time)return false;
    m.mana-=446;setCd(s,m,'blink',15000);m.gcd=s.time+1500;m.stun=0;m.root=0;s.range=clamp(s.range+20,0,40);log(s,'Mage',`Blink → range ${round(s.range)} yd`,'movement');return true;
  }
  function mageNova(s){
    const m=s.mage,sp=D.pvpSpellbooks.Mage.frostNova;if(!gcdReady(s,m)||!ready(s,m,'nova')||m.schoolLock.Frost>s.time||m.mana<sp.cost||s.range>10)return false;
    m.mana-=sp.cost;m.gcd=s.time+1500;setCd(s,m,'nova',21000);
    spellDamage(s,'frostNova',{frozenBonus:false});
    if(spellHit(s,'Frost')){s.rogue.root=s.time+8000;s.rogue.slow=s.time+11000;s.rogue.slowPct=60;log(s,'Mage','Frost Nova → Rogue rooted 8.0s','control');}
    return true;
  }
  function mageCone(s){
    const m=s.mage,sp=D.pvpSpellbooks.Mage.coneOfCold;if(!gcdReady(s,m)||!ready(s,m,'cone')||m.schoolLock.Frost>s.time||m.mana<sp.cost||s.range>10)return false;
    m.mana-=sp.cost;m.gcd=s.time+1500;setCd(s,m,'cone',10000);spellDamage(s,'coneOfCold');return true;
  }
  function mageFireBlast(s){
    const m=s.mage,sp=D.pvpSpellbooks.Mage.fireBlast;if(!gcdReady(s,m)||!ready(s,m,'fireBlast')||m.schoolLock.Fire>s.time||m.mana<sp.cost||s.range>20)return false;
    m.mana-=sp.cost;m.gcd=s.time+1500;setCd(s,m,'fireBlast',8000);spellDamage(s,'fireBlast',{frozenBonus:false});return true;
  }
  function startFrostbolt(s){
    const m=s.mage,sp=D.pvpSpellbooks.Mage.frostbolt;if(!gcdReady(s,m)||m.casting||m.schoolLock.Frost>s.time||m.mana<sp.cost||s.range>30)return false;
    m.mana-=sp.cost;m.gcd=s.time+1500;m.casting={key:'frostbolt',school:'Frost',end:s.time+2500,range:30};log(s,'Mage','Frostbolt cast started (2.5s)','cast');return true;
  }
  function completeMageCast(s){
    const c=s.mage.casting;if(!c||c.end>s.time)return;
    s.mage.casting=null;if(s.range>c.range){log(s,'Mage','Frostbolt failed: out of range','miss');return;}spellDamage(s,c.key);
  }
  function mageBarrier(s){
    const m=s.mage,sp=D.pvpSpellbooks.Mage.iceBarrier;if(!gcdReady(s,m)||!ready(s,m,'barrier')||m.schoolLock.Frost>s.time||m.mana<sp.cost)return false;
    m.mana-=sp.cost;m.gcd=s.time+1500;setCd(s,m,'barrier',30000);m.iceBarrier=455+m.spellDamage*0.10;log(s,'Mage',`Ice Barrier → ${Math.round(m.iceBarrier)} absorb`,'buff');return true;
  }
  function mageAGM(s){
    const m=s.mage;if(!ready(s,m,'agm'))return false;setCd(s,m,'agm',1800000);m.agmShield=rand(s,750,1250);log(s,'Mage',`Arena Grand Master → ${Math.round(m.agmShield)} absorb`,'buff');return true;
  }
  function mageIceBlock(s){
    const m=s.mage;if(!gcdReady(s,m)||!ready(s,m,'iceBlock')||m.schoolLock.Frost>s.time||m.mana<15)return false;
    m.mana-=15;m.gcd=s.time+1500;setCd(s,m,'iceBlock',300000);m.iceBlock=s.time+2500;m.stun=0;m.root=0;log(s,'Mage','Ice Block → immune; policy cancels after 2.5s','control');return true;
  }
  function mageColdSnap(s){
    const m=s.mage;if(!ready(s,m,'coldSnap'))return false;setCd(s,m,'coldSnap',600000);['nova','cone','barrier','iceBlock'].forEach(k=>m.cd[k]=s.time);log(s,'Mage','Cold Snap → Frost cooldowns reset','control');return true;
  }

  function chooseRogue(s){
    const r=s.rogue,m=s.mage;if(r.stun>s.time)return;
    if(r.root>s.time){if(ready(s,r,'vanish'))rogueVanish(s);return;}
    if(r.stealth){if(s.range<=5)rogueCheapShot(s);return;}
    if(s.range>5){if(ready(s,r,'sprint')&&r.sprint<=s.time)rogueSprint(s);return;}
    if(m.iceBlock>s.time)return;
    if(m.casting&&rogueKick(s))return;
    if(r.combo>=5&&m.stun<=s.time&&rogueKidney(s))return;
    if(r.combo>=5&&r.energy>=35){if(ready(s,r,'coldBlood'))rogueColdBlood(s);rogueEvis(s);return;}
    rogueHemo(s);
  }
  function chooseMage(s){
    const m=s.mage,r=s.rogue;
    if(m.iceBlock>s.time)return;
    if(m.casting)return;
    // Blink is deliberately allowed while stunned; that is one of the spell's defining PvP mechanics.
    if(m.stun>s.time){if(s.range<=5)mageBlink(s);return;}
    if(m.hp/m.maxHp<0.28&&ready(s,m,'iceBlock')){mageIceBlock(s);return;}
    if(m.hp/m.maxHp<0.65&&ready(s,m,'agm')){mageAGM(s);return;}
    if(s.range<=6&&ready(s,m,'blink')&&mageBlink(s))return;
    if(m.iceBarrier<=0&&ready(s,m,'barrier')&&mageBarrier(s))return;
    if(s.range<=10&&r.root<=s.time&&ready(s,m,'nova')&&mageNova(s))return;
    if(s.range<=10&&ready(s,m,'cone')&&mageCone(s))return;
    if(s.range<=20&&ready(s,m,'fireBlast')&&mageFireBlast(s))return;
    if(s.range<=12&&(!ready(s,m,'nova')||!ready(s,m,'barrier'))&&ready(s,m,'coldSnap')){mageColdSnap(s);return;}
    if(s.range<=30)startFrostbolt(s);
  }

  function rogueSpeed(s){
    const r=s.rogue;if(r.stun>s.time||r.root>s.time)return 0;
    let pct=r.sprint>s.time?1.70:1.08;if(r.stealth)pct*=0.70;if(r.slow>s.time)pct*=Math.max(0,1-r.slowPct/100);return BASE_RUN*pct;
  }
  function mageSpeed(s){
    const m=s.mage;if(m.stun>s.time||m.root>s.time||m.casting||m.iceBlock>s.time)return 0;return BASE_RUN;
  }
  function move(s){
    if(s.rogue.stealth&&s.time===0)return;
    const dt=STEP/1000;
    s.range=clamp(s.range+(mageSpeed(s)-rogueSpeed(s))*dt,0,40);
  }
  function resources(s){
    while(s.time>=s.rogue.nextEnergy){s.rogue.energy=Math.min(100,s.rogue.energy+20);s.rogue.nextEnergy+=2000;}
  }
  function finish(s){
    if(s.rogue.hp<=0&&s.mage.hp<=0)s.winner='Draw';else if(s.mage.hp<=0)s.winner='Rogue';else if(s.rogue.hp<=0)s.winner='Mage';else s.winner='Timeout';
    log(s,'System',`WINNER: ${s.winner}`,'winner');
    return {seed:s.rng.state,winner:s.winner,duration:round(s.time/1000,1),timeline:s.timeline,final:{rogue:{hp:Math.round(s.rogue.hp),energy:Math.round(s.rogue.energy),combo:s.rogue.combo},mage:{hp:Math.round(s.mage.hp),mana:Math.round(s.mage.mana)},range:round(s.range,1)}};
  }
  function run(seed,cfg){
    const gate=canRun(cfg);if(!gate.ready)return {error:'STRICT_DATA_GATE',missing:gate.missing};
    const s=makeState(seed);
    log(s,'System','Duel starts at 5 yd. Rogue stealthed; Mage pre-buffed with Ice Barrier + Mana Shield.','start');
    for(;s.time<=MAX_TIME&&alive(s);s.time+=STEP){
      resources(s);completeMageCast(s);if(!alive(s))break;
      chooseRogue(s);if(!alive(s))break;
      chooseMage(s);if(!alive(s))break;
      move(s);
    }
    return finish(s);
  }
  function batch(seed,count,cfg){
    const gate=canRun(cfg);if(!gate.ready)return {error:'STRICT_DATA_GATE',missing:gate.missing};
    const n=clamp(Number(count)||1000,1,100000),wins={Rogue:0,Mage:0,Draw:0,Timeout:0};let duration=0;
    const base=(Number(seed)||1)>>>0;
    for(let i=0;i<n;i++){
      const r=run((base+Math.imul(i+1,2654435761))>>>0,cfg);wins[r.winner]=(wins[r.winner]||0)+1;duration+=r.duration;
    }
    return {count:n,wins,rates:Object.fromEntries(Object.entries(wins).map(([k,v])=>[k,round(v*100/n,2)])),avgDuration:round(duration/n,2)};
  }
  function selfTest(cfg){
    const a=run(1337,cfg),b=run(1337,cfg);return {deterministic:JSON.stringify(a)===JSON.stringify(b),winner:a.winner,duration:a.duration};
  }
  return {version:'0.9.0',canRun,run,batch,selfTest,constants:{baseRunYdPerSec:BASE_RUN,stepMs:STEP,maxTimeMs:MAX_TIME}};
})();
