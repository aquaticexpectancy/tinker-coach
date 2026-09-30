"""Offline check of the bot script: it compiles, and every self:Method() it calls is defined."""
import re, sys, pathlib
from lupa import LuaRuntime
src = pathlib.Path(__file__).with_name("bot_lua").joinpath("addon_game_mode.lua").read_text(encoding="utf-8")
err = LuaRuntime().eval('function(s) local f, e = load(s); return e end')(src)
defined = set(re.findall(r"function TinkerBot:(\w+)\(", src))
called = set(re.findall(r"self:(\w+)\(", src))
missing = sorted(called - defined)
print("compile:", err or "ok", "| methods defined:", len(defined), "| called but missing:", missing or "none")
sys.exit(1 if err or missing else 0)
