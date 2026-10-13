"""Lägger web/data (tiles, block och meta.json) som en enda commit på grenen kartdata, utan historik.

  python -m kantarell.publicera
  git push -f origin kartdata
  gh workflow run ci.yml --ref main      (publicerar om Pages med den nya kartdatan)

Kartdatan för ett helt län är flera hundra MB och byts ut vid varje förberäkning. Låg den i main skulle varje
omräkning växa historiken; på kartdata ersätts den i stället (force-push), och CI hämtar den när Pages byggs.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from .forberakna import WEB

REPO = WEB.parent.parent
GREN = "kartdata"


def git(*args: str, env: dict | None = None) -> str:
    return subprocess.run(["git", *args], cwd=REPO, env=env, check=True, capture_output=True, text=True).stdout.strip()


def main() -> None:
    if not (WEB / "meta.json").exists():
        raise SystemExit("web/data/meta.json saknas: kör förberäkningen först")
    with tempfile.TemporaryDirectory() as tmp:
        # Ett eget index, så att main:s index och arbetskatalog inte rörs
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(tmp) / "index")}
        git(f"--work-tree={WEB}", "add", "-A", "-f", ".", env=env)
        trad = git("write-tree", env=env)
    import json
    meta = json.loads((WEB / "meta.json").read_text(encoding="utf-8"))
    text = f"Kartdata för {meta['omrade']}, beräknad {meta['skapad']} ({meta['statistik']['skogsrutor']} skogsrutor)"
    commit = git("commit-tree", trad, "-m", text)
    git("update-ref", f"refs/heads/{GREN}", commit)
    print(f"{GREN} → {commit[:7]}: {text}")
    print(f"Publicera: git push -f origin {GREN} && gh workflow run ci.yml --ref main")


if __name__ == "__main__":
    main()
