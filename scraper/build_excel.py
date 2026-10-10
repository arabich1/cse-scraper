"""Construit le classeur Excel mensuel à partir des CSV.

Usage : python scraper/build_excel.py            # mois courant
        python scraper/build_excel.py 2026-10    # mois donné
        python scraper/build_excel.py --all      # tous les mois présents
"""
import csv
import sys

import xlsxwriter

from common import CSV_DIR, REFERENTIEL, REF_COLS, SCHEMAS, XLSX_DIR, now_local

SHEETS = [("cours", "Cours"), ("carnet", "Carnet d'ordres"), ("indices", "Indices"),
          ("autres", "Droits & Dérivés"), ("transactions", "Transactions")]


def cast(v, t):
    if v == "":
        return None
    try:
        return float(v) if t == "f" else int(float(v)) if t == "i" else v
    except ValueError:
        return v


def write_sheet(wb, title, cols, rows, fmt_head, fmts):
    ws = wb.add_worksheet(title)
    for j, (name, _) in enumerate(cols):
        ws.write(0, j, name, fmt_head)
        ws.set_column(j, j, max(11, min(34, len(name) + 3)))
    for i, r in enumerate(rows, 1):
        for j, (name, t) in enumerate(cols):
            v = cast(r.get(name, ""), t)
            if v is not None:
                ws.write(i, j, v, fmts.get(t))
    ws.freeze_panes(1, 0)
    if rows:
        ws.autofilter(0, 0, len(rows), len(cols) - 1)


def build_month(month: str) -> int:
    days = sorted(p for p in CSV_DIR.iterdir() if p.is_dir() and p.name.startswith(month))
    if not days:
        return 0
    XLSX_DIR.mkdir(parents=True, exist_ok=True)
    out = XLSX_DIR / f"bourse_casablanca_{month}.xlsx"
    wb = xlsxwriter.Workbook(out, {"constant_memory": False})
    head = wb.add_format({"bold": True, "bg_color": "#1F3864", "font_color": "white", "border": 1})
    fmts = {"f": wb.add_format({"num_format": "#,##0.00"}), "i": wb.add_format({"num_format": "#,##0"})}
    total = 0
    for key, title in SHEETS:
        rows = []
        for d in days:
            p = d / f"{key}.csv"
            if p.exists():
                with p.open(encoding="utf-8", newline="") as f:
                    rows.extend(csv.DictReader(f))
        write_sheet(wb, title, SCHEMAS[key], rows, head, fmts)
        total += len(rows)
    if REFERENTIEL.exists():
        with REFERENTIEL.open(encoding="utf-8", newline="") as f:
            ref = list(csv.DictReader(f))
        write_sheet(wb, "Référentiel", [(c, "s") for c in REF_COLS], ref, head, fmts)
    wb.close()
    print(f"{out.name}: {total} lignes")
    return total


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else now_local().strftime("%Y-%m")
    if arg == "--all":
        months = sorted({p.name[:7] for p in CSV_DIR.iterdir() if p.is_dir()})
    else:
        months = [arg]
    for m in months:
        build_month(m)


if __name__ == "__main__":
    main()
