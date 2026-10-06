"""
Aplica a pre-configuração nos servidores, sem precisar de comando no Discord.

Roda dentro do container (`docker exec aura-bot python tools/preconfig_aplicar.py`).
Ele lê canais e cargos pela API do Discord, monta a config com o perfil certo de
cada servidor (coc no do Clash, generico nos outros) e grava no Mongo.

Antes de gravar, faz backup dos documentos em /app/backups.

Uso:
    python tools/preconfig_aplicar.py            # aplica
    python tools/preconfig_aplicar.py --dry-run  # só mostra o que faria
"""
import asyncio
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import preconfig as pc  # noqa: E402

TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("TOKEN")
API = "https://discord.com/api/v10"
BACKUP = "/app/backups"
GUILDS = [g.strip() for g in os.getenv("PRECONFIG_GUILDS", "").split(",") if g.strip()]
DRY = "--dry-run" in sys.argv


def _get(path):
    req = urllib.request.Request(
        API + path, headers={"Authorization": f"Bot {TOKEN}",
                             "User-Agent": "AURA/2.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


class CanalLeve:
    def __init__(self, d):
        self.id = int(d["id"])
        self.name = d.get("name") or ""
        self.type = int(d.get("type", 0))


class GuildLeve:
    """Só o que a detecção de canais/cargos usa."""

    def __init__(self, guild_id):
        info = _get(f"/guilds/{guild_id}?with_counts=false")
        self.id = int(guild_id)
        self.name = info.get("name") or ""
        self.text_channels = [CanalLeve(c) for c in _get(f"/guilds/{guild_id}/channels")]
        self.roles = [CanalLeve(r) for r in _get(f"/guilds/{guild_id}/roles")]
        self.text_channels = [c for c in self.text_channels if c.type in (0, 5)]
        self.voices = [c for c in
                       (CanalLeve(x) for x in _get(f"/guilds/{guild_id}/channels"))
                       if c.type == 2]

    def __repr__(self):
        return f"<GuildLeve {self.name} {self.id}>"


async def salvar_backup():
    import mongo_db
    mongo_db.conectar()
    docs = mongo_db.list_all_guild_configs()
    os.makedirs(BACKUP, exist_ok=True)
    destino = os.path.join(
        BACKUP, f"guild_configs_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.json")
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(docs, f, ensure_ascii=False, indent=2, default=str)
    print(f"backup: {destino} ({len(docs)} documento(s))")
    return destino


async def main() -> int:
    if not TOKEN:
        print("ERRO: DISCORD_TOKEN nao encontrado no ambiente", file=sys.stderr)
        return 2
    guilds = GUILDS or [g["id"] for g in _get("/users/@me/guilds")]
    print(f"servidores: {guilds}")

    if DRY:
        print("dry-run: nada vai ser gravado\n")

    import mongo_db
    from core import settings as st

    for guild_id in guilds:
        guild = GuildLeve(guild_id)
        perfil = pc.perfil_padrao_para(guild_id)
        cfg, falta = pc.montar(guild_id, guild.name, None, perfil, guild=guild)
        ligados = [k for k, v in cfg["modules"].items() if v]

        print("=" * 60)
        print(f"{guild.name} ({guild_id})")
        print(f"  perfil: {perfil}")
        print(f"  modulos ligados ({len(ligados)}): {', '.join(ligados)}")
        cats = cfg["tickets"].get("categories") or []
        print(f"  categorias de ticket ({len(cats)}): "
              f"{', '.join(c.get('label', c.get('key', '?')) for c in cats)}")
        mod = cfg.get("moderation") or {}
        esc = (mod.get("escalation") or {}).get("steps") or []
        print(f"  moderacao: filtros apagam, escalada="
              f"{[s.get('action') for s in esc]}, punish_channel="
              f"{mod.get('punish_channel_id')}")
        print(f"  owner_ids: {cfg.get('owner_ids')}")
        coc = (cfg.get("games") or {}).get("coc") or {}
        print(f"  clash: tag={coc.get('clan_tag')!r} "
              f"registro={coc.get('registration_channel_id')}")
        print(f"  canais de voz para status: "
              f"{[v.name for v in guild.voices] or 'nenhum encontrado'}")
        if falta:
            print(f"  FALTA FECHAR ({len(falta)}):")
            for f in falta:
                print(f"    - {f}")
        else:
            print("  falta fechar: nada")

        if DRY:
            continue

        ok = mongo_db.upsert_guild_config(guild_id, cfg,
                                          updated_by="preconfig_aplicar")
        st.invalidate(str(guild_id))
        print(f"  gravado: {ok}")

    return 0


if __name__ == "__main__":
    if not DRY:
        asyncio.run(salvar_backup())
    sys.exit(asyncio.run(main()))