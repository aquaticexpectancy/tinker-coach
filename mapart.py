"""Extract Dota's own minimap art from your local install (needs Pillow).

The map textures live in pak01_dir.vpk. resource/overviews/dota.txt maps world
coordinates onto them: pos_x -9472, pos_y 9472, scale 18.5 (per 1024 px).
"""
from __future__ import annotations

import pathlib
import struct

HERE = pathlib.Path(__file__).parent
DETAILED = HERE / "map_detailed.png"
SIMPLE = HERE / "map_simple.png"
WORLD_MIN, WORLD_MAX = -9472, 9472           # from resource/overviews/dota.txt
SIZE = 300


def _read_dir(path: pathlib.Path):
    f = open(path, "rb")
    sig, ver, tree = struct.unpack("<III", f.read(12))
    if sig != 0x55AA1234:
        raise ValueError("not a VPK")
    if ver == 2:
        f.read(16)
    header = 12 + (16 if ver == 2 else 0)

    def cstr():
        b = bytearray()
        while (c := f.read(1)) != b"\0":
            b += c
        return b.decode("utf-8", "replace")

    entries = {}
    while ext := cstr():
        while d := cstr():
            while n := cstr():
                _crc, pre, arc, off, ln, _t = struct.unpack("<IHHIIH", f.read(18))
                entries[f"{d}/{n}.{ext}"] = (arc, off, ln, f.read(pre))
    return entries, header + tree, f


def _extract(vpk: pathlib.Path, name: str, entries, data_off, f) -> bytes:
    arc, off, ln, pre = entries[name]
    if arc == 0x7FFF:
        f.seek(data_off + off)
        return pre + f.read(ln)
    with open(str(vpk).replace("_dir.vpk", f"_{arc:03d}.vpk"), "rb") as g:
        g.seek(off)
        return pre + g.read(ln)


def _ycocg_to_rgb(img):
    """Valve's 'YCoCg Conversion' DXT5: Y in alpha, Co/Cg in red/green, per-block scale in blue."""
    import numpy as np
    from PIL import Image
    a = np.asarray(img.convert("RGBA")).astype(np.float32)
    s = np.floor(a[..., 2] / 8.0) + 1.0
    co = (a[..., 0] - 128.0) / s
    cg = (a[..., 1] - 128.0) / s
    y = a[..., 3]
    rgb = np.stack([y + co - cg, y + cg, y - co - cg], axis=-1)
    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB").convert("RGBA")


def _decode_vtex(b: bytes):
    from PIL import Image
    if b"YCoCg Conv" in b[:4096]:
        return _ycocg_to_rgb(_decode_vtex_raw(b))
    return _decode_vtex_raw(b)


def _decode_vtex_raw(b: bytes):
    from PIL import Image
    block_off = 8 + struct.unpack("<I", b[8:12])[0]
    for i in range(struct.unpack("<I", b[12:16])[0]):
        o = block_off + i * 12
        if b[o:o + 4] == b"DATA":
            d = o + 4 + struct.unpack("<I", b[o + 4:o + 8])[0]
            w, h = struct.unpack("<HH", b[d + 20:d + 24])
            fmt = b[d + 26]
            break
    else:
        raise ValueError("no DATA block")
    if fmt == 2:                                   # DXT5 / BC3
        return Image.frombytes("RGBA", (w, h), b[-w * h:], "bcn", 3)
    if fmt == 1:                                   # DXT1 / BC1
        return Image.frombytes("RGBA", (w, h), b[-w * h // 2:], "bcn", 1)
    if fmt in (4, 28):                             # RGBA8888 / BGRA8888
        return Image.frombytes("RGBA", (w, h), b[-w * h * 4:], "raw", "BGRA" if fmt == 28 else "RGBA")
    raise ValueError(f"unsupported texture format {fmt}")


def _material_texture(vmat: bytes) -> str:
    import re
    m = re.search(rb"materials/overviews/[a-z0-9_]+\.vtex", vmat)
    return m.group(0).decode() + "_c"


def extract(dota_game_dir: pathlib.Path, size: int = SIZE) -> list[pathlib.Path]:
    """dota_game_dir = .../dota 2 beta/game/dota"""
    from PIL import Image
    vpk = dota_game_dir / "pak01_dir.vpk"
    entries, data_off, f = _read_dir(vpk)
    out = []
    for vmat, dest in (("materials/overviews/dota.vmat_c", DETAILED), ("materials/overviews/dota_minimal.vmat_c", SIMPLE)):
        tex = _material_texture(_extract(vpk, vmat, entries, data_off, f))
        img = _decode_vtex(_extract(vpk, tex, entries, data_off, f)).convert("RGB")
        img.resize((size, size), Image.LANCZOS).save(dest)
        out.append(dest)
    return out


if __name__ == "__main__":
    import sys
    base = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else \
        pathlib.Path(r"C:\Program Files (x86)\Steam\steamapps\common\dota 2 beta\game\dota")
    for p in extract(base) + extract_icons(base) + [extract_item_costs(base), extract_neutral_stats(base)]:
        print("wrote", p)


ITEM_COSTS = HERE / "item_costs.json"


def extract_item_costs(dota_game_dir: pathlib.Path) -> pathlib.Path:
    """Current-patch item prices from scripts/npc/items.txt (used to compute your net worth)."""
    import json
    import re
    vpk = dota_game_dir / "pak01_dir.vpk"
    entries, data_off, f = _read_dir(vpk)
    text = _extract(vpk, "scripts/npc/items.txt", entries, data_off, f).decode("utf-8", "replace")
    costs, depth, cur = {}, 0, None
    for line in text.splitlines():
        line = line.split("//")[0].strip()
        if not line:
            continue
        if line == "{":
            depth += 1
            continue
        if line == "}":
            depth -= 1
            if depth <= 1:
                cur = None
            continue
        m = re.match(r'"([^"]+)"$', line)
        if m and depth == 1:
            cur = m.group(1)
            continue
        m = re.match(r'"ItemCost"\s+"(\d+)"', line)
        if m and cur and depth == 2:
            costs[cur] = int(m.group(1))
    b = text.index('"item_bottle"')
    m = re.search(r'"mana_restore"\s+"(\d+)"', text[b:b + 4000])
    if m:
        costs["__bottle_mana_restore"] = int(m.group(1))
    ITEM_COSTS.write_text(json.dumps(costs, indent=0), encoding="utf-8")
    return ITEM_COSTS


ICONS = HERE / "icons"
ICON_FILES = {
    "march": "panorama/images/spellicons/tinker_march_of_the_machines_png.vtex_c",
    "rearm": "panorama/images/spellicons/tinker_rearm_png.vtex_c",
    "laser": "panorama/images/spellicons/tinker_laser_png.vtex_c",
    "keen": "panorama/images/spellicons/tinker_keen_teleport_png.vtex_c",
    "turrets": "panorama/images/spellicons/tinker_deploy_turrets_png.vtex_c",
    "bottle": "panorama/images/items/bottle_png.vtex_c",
    "blink": "panorama/images/items/blink_png.vtex_c",
}


def extract_icons(dota_game_dir: pathlib.Path) -> list[pathlib.Path]:
    """Tinker's ability icons from your Dota install, for the in-game HUD."""
    vpk = dota_game_dir / "pak01_dir.vpk"
    entries, data_off, f = _read_dir(vpk)
    ICONS.mkdir(exist_ok=True)
    out = []
    for key, name in ICON_FILES.items():
        if name not in entries:
            continue
        img = _decode_vtex(_extract(vpk, name, entries, data_off, f)).convert("RGBA")
        p = ICONS / f"{key}.png"
        img.save(p)
        out.append(p)
    return out


NEUTRALS = HERE / "neutrals.json"


def extract_neutral_stats(dota_game_dir: pathlib.Path) -> pathlib.Path:
    """HP and magic resistance of every neutral creep (scripts/npc/npc_units.txt)."""
    import json
    import re
    vpk = dota_game_dir / "pak01_dir.vpk"
    entries, data_off, f = _read_dir(vpk)
    text = _extract(vpk, "scripts/npc/npc_units.txt", entries, data_off, f).decode("utf-8", "replace")
    units = {}
    for m in re.finditer(r'^\t"(npc_dota_neutral_[a-z_]+)"\s*\n\t\{(.*?)\n\t\}', text, re.S | re.M):
        body = m.group(2)
        hp = re.search(r'"StatusHealth"\s+"(\d+)"', body)
        mr = re.search(r'"MagicalResistance"\s+"([-\d.]+)"', body)
        if hp:
            units[m.group(1)] = {"hp": int(hp.group(1)), "mr": float(mr.group(1)) if mr else 0.0}
    NEUTRALS.write_text(json.dumps(units, indent=0), encoding="utf-8")
    return NEUTRALS
