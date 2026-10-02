"""Offline simulator of the Tinker 5:00-10:00 farm loop (pure Python, no Dota).

All numbers come from sim/params.json (written by sim/measure.py). A Policy decides where to go, how many Marches, when to
leave the fountain and whether to chain; BotPolicy is a port of the bot's lab plan + gold-per-second router.

    python sim/sim.py            # run the baseline bot policy a few times
"""
import json, math, os, random, heapq, bisect, copy

HERE = os.path.dirname(os.path.abspath(__file__))
STATIONS = "ACDE"


def load_params(path=None):
    return json.load(open(path or os.path.join(HERE, "params.json"), encoding="utf-8"))


class Payoffs:
    """Sampler over the measured per-trip records (station, Marches, March level, :00 marks since the last visit)."""

    def __init__(self, P):
        self.P = P
        self.recs = {}
        self.by_sN = {}
        # records from older / different bot versions pay less per trip than the current lab plan at the same cell:
        # scale them by the per-station ratio measured on the cells both families cover
        fam = lambda r: r["setup"] in ("lab_10x", "lab", "a3_10x", "brute4_10x", "awake_10x")
        cells = {}
        for r in P["payoff_records"]:
            cells.setdefault((r["S"], r["N"], r["ml"], fam(r)), []).append(r["lh"])
        self.factor = {}
        for S in "ABCDE":
            num = den = 0.0
            for (s, N, ml, f), v in cells.items():
                if s == S and f and len(v) >= 15 and len(cells.get((S, N, ml, False), [])) >= 15:
                    o = cells[(S, N, ml, False)]
                    w = len(o)
                    num += w * (sum(v) / len(v))
                    den += w * (sum(o) / len(o))
            self.factor[S] = num / den if den else 1.0
        for r in P["payoff_records"]:
            if not fam(r) and self.factor[r["S"]] != 1.0:
                r = dict(r)
                r["lh"] = r["lh"] * self.factor[r["S"]]
                r["gold"] = r["gold"] * self.factor[r["S"]]
                r["scaled"] = True
            self.by_sN.setdefault((r["S"], r["N"]), []).append(r)
            self.recs.setdefault((r["S"], r["N"], r["ml"]), []).append(r)
        # relative payoff by M bucket per station (N>=2): used when a bucket is thin
        self.fM = {}
        for S in "ACDE":
            allr = [r for r in P["payoff_records"] if r["S"] == S and r["N"] >= 2 and r["lh"] is not None]
            if not allr:
                continue
            m_all = sum(r["lh"] for r in allr) / len(allr)
            d = {}
            for key in ("first", 0, 1, 2):
                v = [r["lh"] for r in allr if (r["first"] if key == "first" else (not r["first"] and r["M"] == key))]
                if len(v) >= 8:
                    d[key] = sum(v) / len(v) / m_all
            self.fM[S] = d
        for S in "ACDE":                                   # stations with no revisits in the data borrow A and D's shape
            if len(self.fM.get(S, {})) < 4:
                have = [self.fM[x] for x in "AD" if x in self.fM and len(self.fM[x]) == 4]
                self.fM[S] = {k: sum(h[k] for h in have) / len(have) for k in ("first", 0, 1, 2)}
        self.fM["B"] = {"first": 1.0, 0: 1.0, 1: 1.0, 2: 1.0}
        b = [r for r in P["payoff_records"] if r["S"] == "B" and r["setup"] == "lab_10x"]
        self.b_N = {n: sum(1 for r in b if r["N"] == n) / len(b) for n in (1, 2, 3)}
        self.note = set()

    def bucket(self, M, first):
        return "first" if first else M

    def sample(self, rng, S, N, ml, M, first):
        key = self.bucket(M, first)
        ratio_note = None
        pool = self.recs.get((S, N, ml), [])
        scale = 1.0
        if len(pool) < 6:
            pool = [r for r in self.by_sN.get((S, N), [])]
        if len(pool) < 6:                                   # no data for this Marches count: reference N, lab shape
            ref = 3 if (S, 3) in self.by_sN and len(self.by_sN[(S, 3)]) >= 6 else 2
            if S == "B":
                ref = 2 if N <= 2 else 3
            pool = self.recs.get((S, ref, ml)) or self.by_sN.get((S, ref), [])
            nr = self.P["n_ratio"].get(S, {}).get(str(ml), {}) if S != "B" else {}
            if nr:
                scale = nr.get(str(min(N, 4)), 1.0) / max(nr.get(str(ref), 1.0), 1e-6)
                scale = min(scale, 1.8)
            elif S == "B":
                scale = {1: 0.5, 2: 1.0, 3: 1.55}.get(min(N, 3), 1.0) / {1: 0.5, 2: 1.0, 3: 1.55}[ref]
            self.note.add((S, N, ml))
        same = [r for r in pool if (r["first"] if key == "first" else (not r["first"] and r["M"] == key))]
        if S != "B" and len(same) >= 12:
            r = rng.choice(same)
            lh, g = r["lh"], r["gold"]
        else:
            r = rng.choice(pool)
            lh, g = r["lh"], r["gold"]
            if S != "B":
                fm = self.fM[S]
                pool_f = sum(fm["first"] if p["first"] else fm[p["M"]] for p in pool[:200]) / min(len(pool), 200)
                scale *= fm[key] / pool_f
        lh = lh * scale
        g = g * scale
        k = int(lh)
        lh = k + (1 if rng.random() < lh - k else 0)
        return {"lh": lh, "gold": g, "L": r["L"], "tail": r["tail"] if r["tail"] is not None else 2.0, "walk": r["walk"],
                "src": r}


class Camp:
    __slots__ = ("S", "i", "n", "full_mean", "tracked")


class Sim:
    def __init__(self, P, policy, seed=0, params_override=None):
        self.P = P
        self.rng = random.Random(seed)
        self.policy = policy
        self.pay = P.get("_payoffs") or Payoffs(P)
        P["_payoffs"] = self.pay
        M = P["mana"]
        self.M = M
        self.t = P["start"]["clock"] + 0.3
        self.mana = float(P["start"]["mana"])
        self.lvl = P["start"]["level"]
        self.lh = 0
        self.gain = 0.0                       # bounty gold credited so far (passive is added at the end / on demand)
        self.gold = float(P["start"]["gold"])
        self.kaya = False
        self.charges = 3
        self.bottle_until = 0.0
        self.in_f = True
        self.fount_until = 1e9
        self.keen_ready = 0.0
        self.march_ready = 0.0
        self.credits = []                     # heap of (time, lh, gold)
        self.station = "F"
        self.last_land = {}                   # station -> landing clock
        self.trips = []
        self.log_home = []                    # mana at each Keen-home order
        self.log_out = []                     # mana at each Keen-out order
        self.stops = []                       # fountain dwell until the Keen-out order
        self.home_secs = 0.0
        self.timeline = []                    # (clock, nw gain) after each credit
        # level thresholds in cumulative last hits (measured spread)
        pr = P["progression"]["level_up_at_lh"]
        self.th = {}
        cur = 0.0
        for L in (7, 8, 9, 10):
            d = pr[str(L)]
            v = max(cur + 3, self.rng.gauss(d["lh_mean"], d["lh_sd"]))
            self.th[L] = v
            cur = v
        kb = P["progression"]["kaya_buy_clock"]
        self.kaya_cost = kb["cost"]
        # camps: truth
        self.camps = {}
        for S in STATIONS:
            self.camps[S] = [self.sample_full(S, i) for i in range(len(P["camps"]["full"][S]))]
        self.camp_minute = int(self.t // 60)
        # waves
        self.waves = {}
        self.max_end = P["start"]["end_clock"]
        self.pending_note = None
        self.wave_seen = None

    # ------------------------------------------------------------------ helpers
    def sample_full(self, S, i):
        m = self.P["camps"]["full"][S][i]
        k = int(m)
        return k + (1 if self.rng.random() < m - k else 0)

    def maxm(self):
        return self.M["max_mana"][str(self.lvl)]

    def kmult(self):
        return self.M["kaya_regen_mult"] if self.kaya else 1.0

    def base(self):
        return self.M["base_regen_prekaya"][str(self.lvl)] * self.kmult()

    def march_lvl(self):
        return 4 if self.lvl >= 7 else 3

    def laser_lvl(self):
        return 4 if self.lvl >= 9 else 3 if self.lvl >= 8 else 2

    def mult(self):
        return self.M["talent_cost_mult"] if self.lvl >= self.M["talent_level"] else 1.0

    def price(self, ab):
        """list price (what the bot reads with GetManaCost): no talent."""
        c = self.M["costs"]
        if ab == "march":
            return c["march"][str(self.march_lvl())]
        if ab == "laser":
            return c["laser"][str(self.laser_lvl())]
        return c[ab]

    def spend(self, ab):
        self.mana -= self.price(ab) * self.mult()
        if self.mana < 0:
            self.mana = 0.0

    def rate(self, t):
        r = self.base()
        if self.in_f or t < self.fount_until:
            r += self.M["fountain_pct_of_max_per_s"] * self.maxm()
        if t < self.bottle_until:
            r += self.M["bottle_mana"] / self.M["bottle_s"] * self.kmult()
        return r

    def advance(self, t_new):
        """Move the clock, integrating mana regen (piecewise constant) and crediting kills."""
        while self.t < t_new - 1e-9:
            nxt = t_new
            for b in (self.bottle_until, self.fount_until if not self.in_f else 1e9):
                if self.t < b < nxt:
                    nxt = b
            if self.credits and self.t < self.credits[0][0] < nxt and self.credits[0][0] <= self.max_end:
                nxt = self.credits[0][0]
            dt = nxt - self.t
            self.mana = min(self.maxm(), self.mana + self.rate(self.t + 1e-9) * dt)
            self.gold += self.P["passive_gold_per_s"] * dt
            self.t = nxt
            while self.credits and self.credits[0][0] <= min(self.t, self.max_end) + 1e-9:
                _, lh, g = heapq.heappop(self.credits)
                self.lh += lh
                self.gain += g
                self.gold += g
                self.timeline.append((self.t, self.gain))
                while self.lvl < 10 and self.lh >= self.th[self.lvl + 1]:
                    self.lvl += 1
            if nxt >= t_new:
                break

    def credit(self, t, lh, gold):
        heapq.heappush(self.credits, (t, lh, gold))

    def use_bottle(self, in_fountain=None):
        """The bot's UseBottle: charge left, not already drinking, and (in fountain, or 60+ mana missing)."""
        inf = self.in_f if in_fountain is None else in_fountain
        if self.in_f:
            self.charges = 3
        if self.charges <= 0 or self.t < self.bottle_until:
            return False
        if not inf and self.maxm() - self.mana < 60:
            return False
        self.charges -= 1
        self.bottle_until = self.t + self.M["bottle_s"]
        return True

    def to_clock(self, t):
        return t

    def ensure_mana(self, need):
        if self.mana + 1e-9 >= need:
            return
        # wait for regen
        r = max(self.rate(self.t), 0.1)
        self.advance(self.t + (need - self.mana) / r + 0.05)

    def maybe_buy_kaya(self):
        if not self.kaya and self.gold >= self.kaya_cost and self.in_f:
            self.gold -= self.kaya_cost
            self.kaya = True

    # ------------------------------------------------------------------ camps (truth)
    def update_camps(self):
        m = int(self.t // 60)
        while self.camp_minute < m:
            self.camp_minute += 1
            for S in STATIONS:
                leak = self.P["camps"]["leak_per_minute_by_station"].get(S, self.P["camps"]["leak_per_minute"])
                for i, n in enumerate(self.camps[S]):
                    if n == 0:
                        self.camps[S][i] = self.sample_full(S, i)
                    elif self.rng.random() < leak:
                        self.camps[S][i] = n + self.sample_full(S, i)

    def kill(self, S, k):
        el = self.P["camps"].get("left_after_trip_override", {}).get(S)
        if el:                                              # E: frogs split when they die; the camp keeps 4-7 after a trip
            self.camps[S] = [self.rng.choice(el)]
            return
        left = list(self.camps[S])
        k = min(k, sum(left))
        for _ in range(k):
            tot = sum(left)
            x = self.rng.random() * tot
            for i, n in enumerate(left):
                if x < n:
                    left[i] -= 1
                    break
                x -= n
        self.camps[S] = left

    # ------------------------------------------------------------------ waves
    def wave_at(self, t):
        j = int((t - 14) // 30)
        tau = t - (30 * j + 14)
        if tau >= 26 or j < 0:
            return None
        w = self.waves.get(j)
        if w is None:
            q = self.P.get("wave_visible_p", 0.75)
            w = self.waves[j] = {"vis": self.rng.random() < q, "n0": self.rng.choice([6, 7, 7, 8]), "used": False,
                                 "noise": self.rng.gauss(0, 0.6)}
        if not w["vis"] or w["used"]:
            return None
        n = max(3, round(w["n0"] - 0.27 * tau + w["noise"]))
        return {"n": n, "j": j}

    # ------------------------------------------------------------------ movement and trips
    def rearm(self):
        """Rearm channel: refreshes Keen and March."""
        self.ensure_mana(self.price("rearm") * self.mult())
        self.spend("rearm")
        self.advance(self.t + self.P["time"]["rearm_total"])
        self.keen_ready = self.t
        self.march_ready = self.t

    def keen(self, dest):
        """Keen order now to dest ('F' or a station); lands after the channel. Returns landing time."""
        if self.t < self.keen_ready:
            self.rearm()
        self.ensure_mana(self.price("keen") * self.mult())
        t0 = self.t
        self.spend("keen")
        self.keen_ready = t0 + self.M["cooldowns"]["keen"]
        T = self.P["time"]
        ch = T["keen_home"]["mean"] if dest == "F" else T["keen_out"][dest]
        self.advance(t0 + ch)
        self.in_f = dest == "F"
        self.fount_until = 1e9 if dest == "F" else self.t + self.M["fountain_linger_s"]
        if dest == "F":
            self.charges = 3
        self.station = dest
        return t0

    def do_trip(self, S, plan, wave_info=None):
        """Land at S (Keen already done) and work the camp: plan = {'N': Marches, 'laser': bool}."""
        P = self.P
        T = P["time"]
        rng = self.rng
        t_land = self.t
        self.update_camps()
        M = None
        first = S not in self.last_land
        if not first:
            M = min(int(t_land // 60) - int(self.last_land[S] // 60), 2)
        self.last_land[S] = t_land
        policy = self.policy
        policy.on_arrival(self, S)
        N_plan = plan["N"]
        mc = self.price("march")
        rc = self.price("rearm")
        kc = self.price("keen")
        wave = None
        if S == "B":
            wave = self.wave_at(t_land) or self.wave_seen     # the bot saw it 3.5 s ago; 99.5% of its B trips find creeps
        # work out the Marches that mana allows, in order
        walk = T["walk"][S]
        self.advance(t_land + walk)
        marches = 0
        t_first = self.t
        t_last = self.t
        for i in range(1, N_plan + 1):
            if i > 1:
                # b: Bottle while the robots work, then R: the gate before Rearm + March
                self.use_bottle(False)
                bottle = self.charges * 60 + (35 if self.t < self.bottle_until else 0)
                if self.mana + bottle - rc - mc - kc < 40:
                    break
                self.advance(t_last + T["march_to_rearm"]["mean"])
                if self.mana < rc * self.mult():
                    break
                self.spend("rearm")
                self.advance(self.t + T["rearm_to_march"]["mean"])
                self.keen_ready = self.t
                self.march_ready = self.t
            self.ensure_mana(mc * self.mult())
            self.spend("march")
            self.march_ready = self.t + self.M["cooldowns"]["march"][str(self.march_lvl())]
            marches += 1
            t_last = self.t
        # payoff
        if S == "B" and wave is None:
            pay = {"lh": 0, "gold": 0.0, "L": 0, "tail": 1.0, "walk": walk}
        else:
            pay = self.pay.sample(rng, S, max(marches, 1), self.march_lvl(), M if M is not None else 2, first)
            if marches == 0:
                pay = {"lh": 0, "gold": 0.0, "L": 0, "tail": 1.0, "walk": walk}
        # laser attempts: the sampled record's attempts, each spends mana only if the creep takes it
        lc = self.price("laser")
        lasers_ok = 0
        tail = pay["tail"]
        if plan.get("laser", True) and pay["L"] > 0 and marches > 0:
            pok = P["laser_ok"].get(S, {"p": 0.5})["p"]
            for _ in range(pay["L"]):
                if self.mana < lc * self.mult() + kc * self.mult():
                    break
                if rng.random() < pok:
                    self.spend("laser")
                    lasers_ok += 1
        elif pay["L"] > 0 and not plan.get("laser", True):
            tail = max(1.0, tail - 1.0 * pay["L"])
        t_home = t_last + tail
        self.advance(max(t_home, self.t))
        # kills credited around the Keen-home order
        if pay["lh"] or pay["gold"]:
            tc = max(t_first + 2.0, t_home + rng.gauss(-2.2, 3.5))
            self.credit(tc, pay["lh"], pay["gold"])
            if S != "B":
                self.kill(S, pay["lh"])
            else:
                if wave:
                    self.waves[wave["j"]]["used"] = True
        elif S == "B" and wave:
            self.waves[wave["j"]]["used"] = True
        trip = {"S": S, "t_out": None, "t_land": t_land, "t_home": self.t, "N": marches, "lh": pay["lh"], "gold": pay["gold"],
                "lasers_ok": lasers_ok, "mana_land": None}
        self.trips.append(trip)
        return trip


# ====================================================================== policies
TRIP_GOLD = {"A": (32, 18.0, 19.9), "C": (41, 11.8, 24.0), "D": (56, 3.0, 17.8), "E": (0, 17.0, 24.2)}
UNSEEN_SET = {"A": 5, "C": 6, "D": 6, "E": 9}
LAB_PLAN = {3: {"A": (3, True), "D": (3, True), "E": (3, False)},
            4: {"A": (2, True), "D": (3, True), "E": (2, True), "C": (3, True)}}


class Policy:
    """Interface: everything the simulator asks of a player."""
    name = "policy"

    def reset(self, sim):
        pass

    def on_arrival(self, sim, S):
        pass

    def on_book(self, sim, trip):
        pass

    def note_trip(self, sim, trip):
        pass

    def decide(self, sim, in_f, here):          # next station: 'A'..'E' or 'F' (wait in fountain)
        raise NotImplementedError

    def plan(self, sim, S):                     # {'N': Marches, 'laser': bool}
        raise NotImplementedError

    def leave_ok(self, sim, pick, dwell):       # leave the fountain now?
        raise NotImplementedError

    def after_trip(self, sim, trip):            # 'F' or a station to chain to
        return "F"


class BotPolicy(Policy):
    """Port of bot_lua/addon_game_mode.lua: --plan lab, --router rate, fountain after every trip, the camp belief."""
    name = "bot (lab plan, fountain after every trip)"

    def __init__(self, p_away=None, threat_p=0.0, b_marches=None):
        self.p_away = p_away
        self.threat_p = threat_p
        self.b_marches = b_marches

    def reset(self, sim):
        P = sim.P
        if self.p_away is None:
            b = P["camps"]["booked_vs_real_same_minute"]
            self.p_away = max(0.0, 1 - b["booked_mean"] / b["real_mean"])
        self.camps = []
        for S in "ECDA":
            for i in P["camps"]["tracked"][S]:
                self.camps.append({"S": S, "i": i, "n": 4, "seen": -1.0, "left": None, "full": None, "low": 0, "stuck": None, "stuck_at": 0.0})
        self.last_trip_lh = {}
        self.last = None
        self.minute = int(sim.t // 60)

    # ---- belief (the bot's own camp memory)
    def minute_update(self, sim):
        m = int(sim.t // 60)
        while self.minute < m:
            self.minute += 1
            for c in self.camps:
                if c["n"] == 0:
                    c["n"], c["left"] = (c["full"] or 4), 0

    def on_arrival(self, sim, S):
        self.minute_update(sim)
        for c in self.camps:
            if c["S"] == S:
                n = sim.camps[S][c["i"]]
                c["n"], c["seen"] = n, sim.t
                if not c["full"] and n > 0:
                    c["full"] = n
                if c["left"] is not None and n < c["left"]:
                    c["left"] = n

    def on_book(self, sim, trip):
        S = trip["S"]
        now = sim.t
        self.last_trip_lh[S] = trip["lh"]
        if S == "B":
            return
        for c in self.camps:
            if c["S"] == S:
                truth = sim.camps[S][c["i"]]
                pa = 0.0 if S in sim.P["camps"].get("left_after_trip_override", {}) else self.p_away     # E: the override already is what is booked
                c["n"] = sum(1 for _ in range(truth) if sim.rng.random() > pa)
                c["seen"] = now
                c["left"] = c["n"]
                c["low"] = (c["low"] + 1) if (trip["lh"] <= 1 and c["n"] > 0) else 0
                if c["low"] >= 2 and not c["stuck"]:
                    c["stuck"], c["stuck_at"] = c["n"], now

    def station_value(self, sim, S):
        v = 0
        for c in self.camps:
            if c["stuck"] and (c["n"] == 0 or c["n"] >= c["stuck"] + 3 or sim.t - c["stuck_at"] > 90):
                c["stuck"], c["low"] = None, 0
            if c["S"] == S and not c["stuck"]:
                v += c["n"]
        return v

    def landing_creeps(self, sim, S, t, arrive):
        self.station_value(sim, S)
        spawn = 60 - t % 60 <= arrive
        n = 0.0
        for c in self.camps:
            if c["S"] == S and not c["stuck"]:
                if c["seen"] < 0:
                    n += UNSEEN_SET[S]
                else:
                    left = min(c["n"], c["left"] or 0)
                    lh = self.last_trip_lh.get(S)
                    if 0 < left <= 3 and c["n"] == left and S != "C" and (lh is None or lh >= 2):
                        n += left + 0.5 * (c["full"] or 4)
                    else:
                        n += (c["n"] - left) + 0.3 * left
                    if c["n"] == 0 and spawn:
                        n += c["full"] or 4
        return n

    def station_rate(self, sim, S, t, arrive, wave):
        if S == "B":
            if not wave:
                return 0.0
            if wave["n"] >= 5:
                return 130 / 17
            if wave["n"] >= 4:
                return 106 / 16.4
            return wave["n"] * 25 / 16
        n = min(self.landing_creeps(sim, S, t, arrive), 14)
        if n < 1:
            return 0.0
        g = TRIP_GOLD[S]
        return min(g[0] + g[1] * n, 35 * n) / g[2]

    def plan_need(self, sim, S):
        mc, rc, kc = sim.price("march"), sim.price("rearm"), sim.price("keen")
        n = 2 if S in ("B", "D") else 3
        return n * mc + (n - 1) * rc + kc + 40 - sim.charges * 60

    def rate_route(self, sim, t, wave, here, in_f):
        ml = sim.march_lvl()
        last = self.last
        arrive = 7 if in_f else 3.5
        spawning = any(c["n"] == 0 and not c["stuck"] for c in self.camps)
        bar = 0.5 if not spawning else (4.5 if 60 - t % 60 <= 15 else 2.5)
        pick, best = "F", bar
        for s in ("A", "C", "D", "E", "B"):
            ok = s != here and (in_f or sim.mana + sim.charges * 60 >= self.plan_need(sim, s))
            if s == "C" and ml < 4:
                ok = False
            if s == "B" and (not wave or (last == "B" and wave["n"] < 4)):
                ok = False
            if s == last:                                   # no_repeat (plan lab)
                ok = False
            if ok:
                r = self.station_rate(sim, s, t, arrive, wave)
                if r > best:
                    best, pick = r, s
        return pick

    def decide(self, sim, in_f, here):
        self.minute_update(sim)
        wave = sim.wave_at(sim.t)
        sim.wave_seen = wave
        if wave and sim.rng.random() < self.threat_p:       # a wave at your tower is always taken
            return "B"
        return self.rate_route(sim, sim.t, wave, here, in_f)

    def plan(self, sim, S):
        if S == "B":
            if self.b_marches:
                return {"N": self.b_marches, "laser": True}
            r = sim.rng.random()
            b = sim.pay.b_N
            N = 1 if r < b[1] else (2 if r < b[1] + b[2] else 3)
            return {"N": N, "laser": True}
        n, laser = LAB_PLAN[sim.march_lvl()][S]
        return {"N": n, "laser": laser}

    def leave_ok(self, sim, pick, dwell):
        mc, rc, kc = sim.price("march"), sim.price("rearm"), sim.price("keen")
        have = sim.mana - kc + sim.charges * 60
        two = 2 * mc + rc + kc + 40
        return (have >= self.plan_need(sim, pick) + sim.charges * 60 or sim.mana >= sim.maxm() * 0.97
                or (dwell >= 3.5 and have >= two) or dwell >= 7)

    def after_trip(self, sim, trip):
        """PrefetchStation + LeaveDecision: chain only when the mana is above 90% of max after the Keen out."""
        kc = sim.price("keen")
        arrive = sim.mana + sim.charges * 60 - kc
        if arrive < 0.9 * sim.maxm():
            return "F"
        wave = sim.wave_at(sim.t)
        pick = self.rate_route(sim, sim.t, wave, trip["S"], False)
        if pick == "F":
            return "F"
        if sim.mana + sim.charges * 60 - kc < self.plan_need(sim, pick):
            return "F"
        if pick != "B" and self.station_rate(sim, pick, sim.t, 3.5, wave) <= 0:
            return "F"
        return pick

    def note_trip(self, sim, trip):
        self.last = trip["S"]


# ====================================================================== the run
def fountain_stop(sim, policy, prev_trip):
    """Landed in fountain: Bottle, Rearm, Book + decision at +3.5 s, leave by the policy. Returns the destination."""
    T = sim.P["time"]
    t0 = sim.t
    pick = None
    rearmed = False
    booked = False
    t_ref = t0
    step = 0.1
    while True:
        dwell = sim.t - t_ref
        sim.maybe_buy_kaya()
        sim.use_bottle()
        if not rearmed and sim.t - t0 >= T["fountain_rearm_delay"]:
            if sim.t < sim.keen_ready:
                sim.ensure_mana(sim.price("rearm") * sim.mult())
                sim.spend("rearm")
                sim.keen_ready = sim.t + T["rearm_total"]
                sim.march_ready = sim.keen_ready
            rearmed = True
        if not booked and sim.t - t0 >= T["decision_after_landing"]:
            booked = True
            if prev_trip:
                policy.on_book(sim, prev_trip)
        if booked and pick is None:
            pick = policy.decide(sim, True, None)
        if booked and pick is not None:
            if pick == "F":
                if dwell > 5:
                    pick = None
                    t_ref = sim.t - 3
                    continue
            elif sim.t >= sim.keen_ready - 1e-9 and policy.leave_ok(sim, pick, dwell):
                break
        if sim.t >= sim.max_end:
            return None
        sim.advance(sim.t + step)
    return pick


def run(P, policy, seed=0):
    sim = Sim(P, policy, seed)
    policy.reset(sim)
    end = sim.max_end
    pick = policy.decide(sim, True, None)           # the bot decides in fountain at once, then leaves
    sim.stops.append(0.0)
    dest = pick if pick != "F" else None
    while dest is not None and sim.t < end:
        sim.log_out.append(sim.mana)
        t_out = sim.t
        sim.keen(dest)
        trip = sim.do_trip(dest, policy.plan(sim, dest))
        trip["t_out"] = t_out
        trip["mana_out"] = sim.log_out[-1]
        policy.note_trip(sim, trip)
        nxt = policy.after_trip(sim, trip)
        while nxt != "F" and sim.t < end:
            # chain: Rearm for March (and Keen), Keen straight to the next station
            if sim.t < sim.march_ready or sim.t < sim.keen_ready:
                sim.rearm()
            trip["chain"] = True
            sim.log_out.append(sim.mana)
            t_o = sim.t
            sim.keen(nxt)
            trip = sim.do_trip(nxt, policy.plan(sim, nxt))
            trip["t_out"] = t_o
            trip["mana_out"] = sim.log_out[-1]
            policy.note_trip(sim, trip)
            nxt = policy.after_trip(sim, trip)
        if sim.t >= end:
            break
        sim.log_home.append(sim.mana)
        t_home = sim.t
        sim.keen("F")
        t_land = sim.t
        pick = fountain_stop(sim, policy, trip)
        if pick is None:
            break
        sim.stops.append(sim.t - t_land)
        sim.home_secs += sim.t - t_home
        dest = pick
    sim.advance(end)
    gain = sim.gain + P["passive_gold_per_s"] * (end - 297.5)
    return {"gain": gain, "lh": sim.lh, "trips": len(sim.trips), "camp_trips": sum(1 for t in sim.trips if t["S"] != "B"),
            "wave_trips": sum(1 for t in sim.trips if t["S"] == "B"), "home_secs": sim.home_secs,
            "log_home": sim.log_home, "log_out": sim.log_out, "stops": sim.stops, "level": sim.lvl, "sim": sim}


if __name__ == "__main__":
    import statistics as st
    P = load_params()
    pol = BotPolicy()
    res = [run(P, pol, seed=i) for i in range(30)]
    print("gain %.0f sd %.0f | LH %.1f | trips %.1f | home secs %.0f | mana at keen home %.0f" % (
        st.mean(r["gain"] for r in res), st.pstdev([r["gain"] for r in res]), st.mean(r["lh"] for r in res),
        st.mean(r["trips"] for r in res), st.mean(r["home_secs"] for r in res),
        st.mean(sum(r["log_home"]) / len(r["log_home"]) for r in res)))
