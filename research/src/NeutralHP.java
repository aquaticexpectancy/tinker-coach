import skadistats.clarity.model.*;
import skadistats.clarity.processor.entities.*;
import skadistats.clarity.processor.gameevents.*;
import skadistats.clarity.processor.reader.*;
import skadistats.clarity.processor.runner.*;
import skadistats.clarity.processor.stringtables.*;
import skadistats.clarity.source.MappedFileSource;
import java.io.*;
import java.util.*;

/** Neutral creep HP around Tinker (every 6 ticks), Tinker casts with position/facing, neutral spawns and deaths.
 *  Output prefix_{neu,cast,spawn,death}.csv; clock = game time since the horn (from the game rules entity). */
@UsesEntities
@UsesStringTable("EntityNames")
public class NeutralHP {
    PrintWriter neu, cast, spawn, death, lane, heroes;
    int lastLane = -100;
    Entity tinker, rules;
    int lastSample = -100;
    NeutralHP(String p) throws IOException {
        neu = new PrintWriter(new FileWriter(p + "_neu.csv")); neu.println("clock,idx,name,hp,maxhp,x,y,tx,ty");
        cast = new PrintWriter(new FileWriter(p + "_cast.csv")); cast.println("clock,ability,x,y,yaw,mana,level");
        spawn = new PrintWriter(new FileWriter(p + "_spawn.csv")); spawn.println("clock,idx,name,x,y,maxhp");
        death = new PrintWriter(new FileWriter(p + "_death.csv")); death.println("clock,target,attacker,inflictor,value");
        lane = new PrintWriter(new FileWriter(p + "_lane.csv")); lane.println("clock,team,hp,maxhp,x,y");
        heroes = new PrintWriter(new FileWriter(p + "_heroes.csv")); heroes.println("clock,hero,team,hp,maxhp,mana,x,y");
    }
    static float[] pos(Entity e) {
        Integer cx = e.getProperty("CBodyComponent.m_cellX"), cy = e.getProperty("CBodyComponent.m_cellY");
        Float vx = e.getProperty("CBodyComponent.m_vecX"), vy = e.getProperty("CBodyComponent.m_vecY");
        return new float[]{cx * 128 + vx - 16384, cy * 128 + vy - 16384};
    }
    Float off = null; int curTick = 0;
    float clock() {                      // game time since the horn: combat-log time offset + start time from the game rules
        if (rules == null || off == null) return -999;
        Float st = rules.getProperty("m_pGameRules.m_flGameStartTime");
        return (st == null || st == 0) ? -999 : curTick / 30f + off - st;
    }
    String name(Context ctx, Entity e) {                 // unit type index (mapped to a name from the death log later)
        try { return "u" + e.getProperty("m_iUnitNameIndex"); } catch (Exception ex) { return "?"; }
    }
    boolean isNeutral(Entity e) { return e.getDtClass().getDtName().contains("Creep_Neutral"); }
    @OnEntityCreated
    public void onCreated(Context ctx, Entity e) {
        curTick = ctx.getTick();
        String dt = e.getDtClass().getDtName();
        if (dt.equals("CDOTA_Unit_Hero_Tinker")) tinker = e;
        else if (dt.equals("CDOTAGamerulesProxy")) rules = e;
        else if (isNeutral(e)) {
            float c = clock();
            if (c > 0 && c < 1300) { float[] p = pos(e); spawn.println(String.format(java.util.Locale.US, "%.2f,%d,%s,%.0f,%.0f,%s", c, e.getIndex(), name(ctx, e), p[0], p[1], e.getProperty("m_iMaxHealth"))); }
        }
    }
    @OnEntityDeleted
    public void onDeleted(Context ctx, Entity e) {
        if (!isNeutral(e)) return;
        curTick = ctx.getTick();
        float c = clock();
        if (c > 0 && c < 1300) { float[] p = pos(e); spawn.println(String.format(java.util.Locale.US, "%.2f,%d,gone,%.0f,%.0f,%s", c, e.getIndex(), p[0], p[1], e.getProperty("m_iHealth"))); }
    }

    @OnTickEnd
    public void onTick(Context ctx, boolean synthetic) {
        curTick = ctx.getTick();
        float cl = clock();
        if (cl >= 0 && cl <= 1260 && ctx.getTick() - lastLane >= 30) {           // once a second: mid-lane creeps + every hero
            lastLane = ctx.getTick();
            Iterator<Entity> li = ctx.getProcessor(Entities.class).getAllByPredicate(
                    e -> e.getDtClass().getDtName().startsWith("CDOTA_BaseNPC_Creep_Lane") || e.getDtClass().getDtName().equals("CDOTA_BaseNPC_Creep_Siege"));
            while (li.hasNext()) {
                Entity e = li.next(); float[] p = pos(e);
                Integer hp = e.getProperty("m_iHealth");
                if (hp == null || hp <= 0 || Math.abs(p[0] - p[1]) > 2500) continue;
                lane.println(String.format(java.util.Locale.US, "%.1f,%s,%d,%s,%.0f,%.0f", cl, e.getProperty("m_iTeamNum"), hp, e.getProperty("m_iMaxHealth"), p[0], p[1]));
            }
            Iterator<Entity> hi = ctx.getProcessor(Entities.class).getAllByPredicate(e -> e.getDtClass().getDtName().startsWith("CDOTA_Unit_Hero_"));
            while (hi.hasNext()) {
                Entity e = hi.next(); float[] p = pos(e);
                heroes.println(String.format(java.util.Locale.US, "%.1f,%s,%s,%s,%s,%s,%.0f,%.0f", cl, e.getDtClass().getDtName().substring(16),
                        e.getProperty("m_iTeamNum"), e.getProperty("m_iHealth"), e.getProperty("m_iMaxHealth"), e.getProperty("m_flMana"), p[0], p[1]));
            }
        }
        if (tinker == null || ctx.getTick() - lastSample < 6) return;
        float c = clock();
        if (c < 240 || c > 1260) return;
        lastSample = ctx.getTick();
        float[] tp = pos(tinker);
        Iterator<Entity> it = ctx.getProcessor(Entities.class).getAllByPredicate(this::isNeutral);
        while (it.hasNext()) {
            Entity e = it.next();
            float[] p = pos(e);
            Integer hp0 = e.getProperty("m_iHealth"), mx0 = e.getProperty("m_iMaxHealth");
            boolean hurt = hp0 != null && mx0 != null && hp0 < mx0;       // damaged creeps are followed anywhere
            if (!hurt && Math.hypot(p[0] - tp[0], p[1] - tp[1]) > 2000) continue;
            neu.println(String.format(java.util.Locale.US, "%.2f,%d,%s,%s,%s,%.0f,%.0f,%.0f,%.0f", c, e.getIndex(), name(ctx, e), e.getProperty("m_iHealth"),
                    e.getProperty("m_iMaxHealth"), p[0], p[1], tp[0], tp[1]));
        }
    }
    @OnCombatLogEntry
    public void onCombat(Context ctx, CombatLogEntry e) {
        curTick = ctx.getTick();
        if (off == null && e.hasTimestamp()) off = e.getTimestamp() - ctx.getTick() / 30f;
        float c = clock();
        if (c < 240 || c > 1260) return;
        String type = e.getType().name(), atk = String.valueOf(e.getAttackerName()), tgt = String.valueOf(e.getTargetName());
        if (type.endsWith("DEATH") && tgt.startsWith("npc_dota_neutral"))
            death.println(String.format(java.util.Locale.US, "%.2f,%s,%s,%s,%d", c, tgt, atk, e.getInflictorName(), e.getValue()));
        if ((type.endsWith("ABILITY") || type.endsWith("ITEM")) && atk.contains("tinker") && tinker != null) {
            float[] p = pos(tinker);
            Object a = tinker.getProperty("CBodyComponent.m_angRotation");
            String s = String.valueOf(a).replace("[", "").replace("]", "").replace("(", "").replace(")", "");
            float yaw = 0; try { yaw = Float.parseFloat(s.split(",")[1].trim()); } catch (Exception ex) {}
            cast.println(String.format(java.util.Locale.US, "%.2f,%s,%.0f,%.0f,%.1f,%s,%s", c, e.getInflictorName(), p[0], p[1], yaw,
                    tinker.getProperty("m_flMana"), tinker.getProperty("m_iCurrentLevel")));
        }
    }
    void close() { neu.close(); cast.close(); spawn.close(); death.close(); lane.close(); heroes.close(); }
    public static void main(String[] a) throws Exception {
        NeutralHP x = new NeutralHP(a[1]);
        new SimpleRunner(new MappedFileSource(a[0])).runWith(x);
        x.close();
    }
}
