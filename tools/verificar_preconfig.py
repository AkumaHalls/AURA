"""
Confere o que esta gravado no Mongo depois da pre-configuracao.

Uso (dentro do container): python tools/verificar_preconfig.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mongo_db  # noqa: E402

mongo_db.conectar()

for d in mongo_db.list_all_guild_configs():
    gid = d.get("guild_id")
    mods = [k for k, v in (d.get("modules") or {}).items() if v]
    tk = d.get("tickets") or {}
    mod = d.get("moderation") or {}
    esc = (mod.get("escalation") or {}).get("steps") or []
    acoes = sorted({(mod.get(f) or {}).get("action")
                    for f in ("words", "links", "invites", "caps", "flood",
                              "duplicate", "mentions", "zerospace")})
    coc = (d.get("games") or {}).get("coc") or {}

    print("=" * 58)
    print(f"{d.get('guild_name')} ({gid})")
    print(f"  perfil .............. {d.get('profile')}")
    print(f"  modulos ligados ..... {len(mods)}: {', '.join(mods)}")
    print(f"  categorias ticket ... {len(tk.get('categories') or [])}")
    print(f"  owner_ids ........... {d.get('owner_ids')}")
    print(f"  moderação: filtros={acoes} escalada="
          f"{[s.get('action') for s in esc]} punish={mod.get('punish_channel_id')}")
    print(f"  clash: enabled={coc.get('enabled')} tag={coc.get('clan_tag')!r} "
          f"registro={coc.get('registration_channel_id')}")
    print(f"  clash: log={coc.get('log_channel_id')} "
          f"elder={coc.get('roles', {}).get('elder')}")