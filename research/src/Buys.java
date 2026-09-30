import skadistats.clarity.model.*;
import skadistats.clarity.processor.gameevents.*;
import skadistats.clarity.processor.runner.*;
import skadistats.clarity.source.MappedFileSource;
import java.io.*;

public class Buys {
    PrintWriter out;
    Buys(String p) throws IOException { out = new PrintWriter(new FileWriter(p)); out.println("tick,item"); }
    @OnCombatLogEntry
    public void onCombat(Context ctx, CombatLogEntry e) {
        if (e.getType().name().endsWith("PURCHASE") && String.valueOf(e.getTargetName()).contains("tinker"))
            out.println(ctx.getTick() + "," + e.getValueName());
    }
    public static void main(String[] a) throws Exception {
        Buys b = new Buys(a[1]);
        new SimpleRunner(new MappedFileSource(a[0])).runWith(b);
        b.out.close();
    }
}
