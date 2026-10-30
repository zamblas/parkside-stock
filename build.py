"""Gera o site estático em site/ (index.html + data.json). Usado pelo GitHub Actions."""
import json
import shutil
import sys

import lidl

OUT = lidl.HERE / "site"


def main():
    data = lidl.build_data()
    OUT.mkdir(exist_ok=True)
    shutil.copy(lidl.HERE / "index.html", OUT / "index.html")
    (OUT / "data.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    errors = sum(1 for s in data["stock"].values() if "error" in s)
    print(f"{len(data['products'])} produtos, {len(data['stores'])} lojas, {errors} erros de stock")
    if data["products"] and errors == len(data["products"]):
        sys.exit("todos os pedidos de stock falharam (lidl.pt a bloquear?)")


if __name__ == "__main__":
    main()
