"""
Executa um comando na VPS por paramiko.

Uso: python tools/ssh_run.py "<comando>"

Nota: nesta máquina o canal sem pty nao devolve saida, entao sempre usamos pty
e limpamos os codigos de cor antes de imprimir.
"""
import re
import sys

import paramiko

HOST = "147.15.124.229"
USER = "ubuntu"
KEY = r"C:\Users\Administrator\Documents\ssh-key-2026-03-23.key"

ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07|\x1b[=>]|\r")


def main() -> int:
    if len(sys.argv) < 2:
        print("informe o comando", file=sys.stderr)
        return 2
    cmd = sys.argv[1]

    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(HOST, username=USER, key_filename=KEY, timeout=30,
                banner_timeout=30, auth_timeout=30)
    try:
        _, out, err = cli.exec_command(cmd, get_pty=True)
        for line in iter(out.readline, ""):
            limpa = ANSI.sub("", line).strip()
            if limpa:
                print(limpa, flush=True)
        codigo = out.channel.recv_exit_status()
        e = ANSI.sub("", err.read().decode("utf-8", "replace")).strip()
        if e:
            print(e, file=sys.stderr, flush=True)
        return codigo
    finally:
        cli.close()


if __name__ == "__main__":
    sys.exit(main())