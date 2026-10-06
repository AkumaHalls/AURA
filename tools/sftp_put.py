"""Envia arquivos para a VPS por SFTP (o ssh.exe local nao funciona nesta maquina).

Uso: python tools/sftp_put.py <local> <remoto> [<local> <remoto> ...]
"""
import os
import posixpath
import sys

import paramiko

HOST = "147.15.124.229"
USER = "ubuntu"
KEY = r"C:\Users\Administrator\Documents\ssh-key-2026-03-23.key"


def main() -> int:
    if len(sys.argv) < 3 or (len(sys.argv) - 1) % 2:
        print("uso: sftp_put.py <local> <remoto> [<local> <remoto> ...]",
              file=sys.stderr)
        return 2

    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(HOST, username=USER, key_filename=KEY, timeout=30)
    sftp = cli.open_sftp()
    try:
        for i in range(1, len(sys.argv), 2):
            local, remoto = sys.argv[i], sys.argv[i + 1]
            pasta = posixpath.dirname(remoto)
            if pasta:
                try:
                    sftp.mkdir(pasta)
                except IOError:
                    pass
            sftp.put(local, remoto)
            print(f"{local} -> {remoto} ({os.path.getsize(local)} bytes)")
    finally:
        sftp.close()
        cli.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())