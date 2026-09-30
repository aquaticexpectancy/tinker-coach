import skadistats.clarity.model.*;
import skadistats.clarity.processor.entities.*;
import skadistats.clarity.processor.gameevents.*;
import skadistats.clarity.processor.runner.*;
import skadistats.clarity.source.MappedFileSource;
import java.io.*;
import java.util.*;

@UsesEntities
public class MarchDirs {
    PrintWriter out;
    List<long[]> marches = new ArrayList<>();          // tick, x, y, yaw*100, neutralKills, laneKills
    MarchDirs(String path) throws IOException { out = new PrintWriter(new FileWriter(path)); out.println("tick,x,y,yaw,neutral_kills,lane_kills"); }
    static float[] pos(Entity e) {
        Integer cx = e.getProperty("CBodyComponent.m_cellX"), cy = e.getProperty("CBodyComponent.m_cellY");
        Float vx = e.getProperty("CBodyComponent.m_vecX"), vy = e.getProperty("CBodyComponent.m_vecY");
        return new float[]{cx * 128 + vx - 16384, cy * 128 + vy - 16384};
    }
    @OnCombatLogEntry
    public void onCombat(Context ctx, CombatLogEntry e) {
        String type = e.getType().name(), inf = String.valueOf(e.getInflictorName()), atk = String.valueOf(e.getAttackerName());
        if (type.endsWith("ABILITY") && inf.equals("tinker_march_of_the_machines") && atk.contains("tinker")) {
            Entity t = ctx.getProcessor(Entities.class).getByDtName("CDOTA_Unit_Hero_Tinker");
            if (t == null) return;
            float[] p = pos(t);
            Object a = t.getProperty("CBodyComponent.m_angRotation");
            float yaw = 0;
            String s = String.valueOf(a).replace("[", "").replace("]", "").replace("(", "").replace(")", ""); yaw = Float.parseFloat(s.split(",")[1].trim());
            marches.add(new long[]{ctx.getTick(), (long) p[0], (long) p[1], (long) (yaw * 100), 0, 0});
        } else if (type.endsWith("DEATH") && inf.equals("tinker_march_of_the_machines") && atk.contains("tinker") && !marches.isEmpty()) {
            long[] m = marches.get(marches.size() - 1);
            if (ctx.getTick() - m[0] < 300) {
                String tgt = String.valueOf(e.getTargetName());
                if (tgt.startsWith("npc_dota_neutral")) m[4]++; else if (tgt.contains("creep")) m[5]++;
            }
        }
    }
    void close() { for (long[] m : marches) out.println(m[0] + "," + m[1] + "," + m[2] + "," + (m[3] / 100.0) + "," + m[4] + "," + m[5]); out.close(); }
    public static void main(String[] a) throws Exception {
        MarchDirs x = new MarchDirs(a[1]);
        new SimpleRunner(new MappedFileSource(a[0])).runWith(x);
        x.close();
    }
}
