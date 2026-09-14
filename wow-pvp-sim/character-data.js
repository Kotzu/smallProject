window.WOW_CHARACTER_DATA={
  source:{
    primaryStats:"WoWSims Classic sim/core/base_stats.go (live Classic calibrated naked-character stats + race offsets).",
    classBase:"WoWSims Classic ClassBaseStats; cross-checked against Classic theorycraft values. CMaNGOS remains a combat-formula reference, not the authority for live Classic base-stat constants where the datasets differ.",
    formulas:"WoWSims Classic base_stats.go + CMaNGOS StatSystem.cpp + Wowhead Classic stat guide.",
    note:"Important correction in v0.11: older CMaNGOS archived level-stat rows differ from live Classic values for some classes/races. The simulator now uses live-Classic-calibrated base stats for character math."
  },
  level60:{
    undeadRogue:{
      race:"Undead",class:"Rogue",raceId:5,classId:4,level:60,
      createStats:{str:79,agi:128,sta:76,int:33,spi:55},
      classBase:{health:1523,mana:0,attackPowerLevelComponent:100},
      racialCombat:{shadowResistance:10,willOfTheForsaken:true},
      verified:true,
      provenance:"WoWSims Classic: Rogue base STR80/AGI130/STA75/INT35/SPI50 plus Undead offsets STR-1/AGI-2/STA+1/INT-2/SPI+5."
    },
    gnomeMage:{
      race:"Gnome",class:"Mage",raceId:7,classId:8,level:60,
      createStats:{str:25,agi:38,sta:44,int:128,spi:120},
      classBase:{health:1370,mana:1213,attackPowerLevelComponent:-10},
      racialCombat:{expansiveMindIntPct:5,escapeArtist:true,arcaneResistance:10},
      verified:true,
      note:"Raw INT is pre-Expansive-Mind. The +5% Gnome INT modifier is applied after additive INT from gear, matching the stat-modifier model.",
      provenance:"WoWSims Classic: Mage base STR30/AGI35/STA45/INT125/SPI120 plus Gnome offsets STR-5/AGI+3/STA-1/INT+3."
    }
  }
};
