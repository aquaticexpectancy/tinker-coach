import skadistats.clarity.model.*;
import skadistats.clarity.processor.entities.*;
import skadistats.clarity.processor.gameevents.*;
import skadistats.clarity.processor.reader.*;
import skadistats.clarity.processor.runner.*;
import skadistats.clarity.source.MappedFileSource;
import java.io.*;
import java.util.*;

public class Extract {
    PrintWriter snap, ev, unitDeaths, spawns, heroes;
    Map<Integer, float[]> alive = new HashMap<>(); // index -> pos, for neutral/lane creeps
    Map<Integer, Integer> lifeOf = new HashMap<>();
    Set<Long> seen = new HashSet<>();
    float startTime = 0; int paused = 0;
    float[] tinkerPos = {0, 0};

    Extract(String prefix) throws IOException {
        snap = new PrintWriter(new FileWriter(prefix + "_snap.csv"));
        ev = new PrintWriter(new FileWriter(prefix + "_events.csv"));
        unitDeaths = new PrintWriter(new FileWriter(prefix + "_unitdeaths.csv"));
        spawns = new PrintWriter(new FileWriter(prefix + "_spawns.csv"));
        heroes = new PrintWriter(new FileWriter(prefix + "_heroes.csv"));
        snap.println("tick,start,paused,x,y,hp,mana,maxmana,level,life,lh,dn,nw,gold,campsStacked,creepsStacked,neutralGold,creepGold,earned");
        ev.println("tick,ts,type,attacker,target,inflictor,value,atkHero,tgtHero,tx,ty");
        unitDeaths.println("tick,cls,idx,x,y");
        spawns.println("tick,cls,idx,x,y");
        heroes.println("tick,cls,team,x,y,life");
    }

    static float[] pos(Entity e) {
        Integer cx = e.getProperty("CBodyComponent.m_cellX"), cy = e.getProperty("CBodyComponent.m_cellY");
        Float vx = e.getProperty("CBodyComponent.m_vecX"), vy = e.getProperty("CBodyComponent.m_vecY");
        return new float[]{cx * 128 + vx - 16384, cy * 128 + vy - 16384};
    }

    @UsesEntities
    @OnTickEnd
    public void onTick(Context ctx, boolean synthetic) {
        Entities es = ctx.getProcessor(Entities.class);
        int tick = ctx.getTick();
        Entity gr = es.getByDtName("CDOTAGamerulesProxy");
        if (gr != null) {
            startTime = gr.getProperty("m_pGameRules.m_flGameStartTime");
            paused = gr.getProperty("m_pGameRules.m_nTotalPausedTicks");
        }
        for (String cls : new String[]{"CDOTA_BaseNPC_Creep_Neutral", "CDOTA_BaseNPC_Creep_Lane"}) {
            Iterator<Entity> it = es.getAllByDtName(cls);
            while (it.hasNext()) {
                Entity e = it.next();
                int idx = e.getIndex();
                float[] p = pos(e);
                int life = e.getProperty("m_lifeState");
                long uid = e.getUid();
                if (!seen.contains(uid)) { seen.add(uid); if (cls.contains("Neutral")) spawns.printf("%d,%s,%d,%.0f,%.0f%n", tick, cls, idx, p[0], p[1]); lifeOf.put(idx, 0); }
                Integer prev = lifeOf.get(idx);
                if (prev != null && prev == 0 && life != 0) unitDeaths.printf("%d,%s,%d,%.0f,%.0f%n", tick, cls, idx, p[0], p[1]);
                lifeOf.put(idx, life);
            }
        }
        Entity t = es.getByDtName("CDOTA_Unit_Hero_Tinker");
        if (t != null) tinkerPos = pos(t);
        if (tick % 15 != 0 || t == null) return;
        int pid = t.getProperty("m_iPlayerID");
        int team = t.getProperty("m_iTeamNum");
        Entity dt = es.getByDtName(team == 2 ? "CDOTA_DataRadiant" : "CDOTA_DataDire");
        String k = String.format("m_vecDataTeam.%04d.", (pid / 2) % 5);
        float[] p = tinkerPos;
        snap.printf("%d,%.2f,%d,%.0f,%.0f,%d,%.0f,%.0f,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d%n", tick, startTime, paused, p[0], p[1],
            (int) t.getProperty("m_iHealth"), (float) t.getProperty("m_flMana"), (float) t.getProperty("m_flMaxMana"),
            (int) t.getProperty("m_iCurrentLevel"), (int) t.getProperty("m_lifeState"),
            (int) dt.getProperty(k + "m_iLastHitCount"), (int) dt.getProperty(k + "m_iDenyCount"), (int) dt.getProperty(k + "m_iNetWorth"),
            (int) dt.getProperty(k + "m_iReliableGold") + (int) dt.getProperty(k + "m_iUnreliableGold"),
            (int) dt.getProperty(k + "m_iCampsStacked"), (int) dt.getProperty(k + "m_iCreepsStacked"),
            (int) dt.getProperty(k + "m_iNeutralKillGold"), (int) dt.getProperty(k + "m_iCreepKillGold"), (int) dt.getProperty(k + "m_iTotalEarnedGold"));
        if (tick % 60 == 0) {
            Iterator<Entity> it = es.getAllByPredicate(e -> e.getDtClass().getDtName().startsWith("CDOTA_Unit_Hero_"));
            while (it.hasNext()) {
                Entity h = it.next();
                if (!h.hasProperty("m_hReplicatingOtherHeroModel")) {}
                float[] hp = pos(h);
                heroes.printf("%d,%s,%d,%.0f,%.0f,%d%n", tick, h.getDtClass().getDtName(), (int) h.getProperty("m_iTeamNum"), hp[0], hp[1], (int) h.getProperty("m_lifeState"));
            }
        }
    }

    Context lastCtx;
    @OnCombatLogEntry
    public void onCombat(Context ctx, CombatLogEntry e) {
        String a = e.hasAttackerName() ? e.getAttackerName() : "", t = e.hasTargetName() ? e.getTargetName() : "";
        String type = e.getType().name().replace("DOTA_COMBATLOG_", "");
        boolean tinker = a.contains("tinker") || t.contains("tinker") || (e.hasDamageSourceName() && String.valueOf(e.getDamageSourceName()).contains("tinker"));
        boolean keep = tinker || type.equals("DEATH") || type.equals("PURCHASE") && false;
        if (type.equals("DAMAGE") || type.equals("HEAL") || type.startsWith("MODIFIER")) keep = tinker && !type.equals("DAMAGE") && !type.equals("HEAL") && type.equals("MODIFIER_ADD") && e.hasInflictorName() && String.valueOf(e.getInflictorName()).matches(".*(tinker|travel|tpscroll|teleport).*");
        if (!keep) return;
        String inf = e.hasInflictorName() ? String.valueOf(e.getInflictorName()) : "";
        ev.printf("%d,%.2f,%s,%s,%s,%s,%d,%b,%b,%.0f,%.0f%n", ctx.getTick(), e.getTimestamp(), type, a, t, inf,
            e.hasValue() ? e.getValue() : 0, e.isAttackerHero(), e.isTargetHero(), tinkerPos[0], tinkerPos[1]);
    }

    void close() { snap.close(); ev.close(); unitDeaths.close(); spawns.close(); heroes.close(); }

    public static void main(String[] args) throws Exception {
        Extract x = new Extract(args[1]);
        new SimpleRunner(new MappedFileSource(args[0])).runWith(x);
        x.close();
    }
}
