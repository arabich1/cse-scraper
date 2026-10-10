"""Instantané de la Bourse de Casablanca : cours, meilleure limite (carnet), indices, tape des transactions.

Source : pages publiques « Live Market » de casablanca-bourse.com (JSON embarqué dans le HTML).
Usage :  python scraper/scrape.py            # instantané (ignoré hors horaires de séance)
         python scraper/scrape.py --force    # forcer, même hors horaires
         python scraper/scrape.py --final    # instantané de fin de journée (après clôture)
"""
import argparse
import csv
import hashlib
import json
import re
import ssl
import sys
import time as _time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime

from common import (CSV_DIR, REFERENTIEL, REF_COLS, SCHEMAS, STATE_FILE, WINDOW_END,
                    WINDOW_START, now_local, phase_of)

UA = "Mozilla/5.0 (compatible; bourse-casa-archiver/1.0)"
SETTINGS_RE = re.compile(
    r'<script type="application/json" data-drupal-selector="drupal-settings-json">(.*?)</script>', re.S)


def fetch_settings(path: str, tries: int = 4) -> dict:
    url = "https://www.casablanca-bourse.com/live-market/" + path
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "fr"})
            try:
                resp = urllib.request.urlopen(req, timeout=60)
            except urllib.error.URLError as exc:
                # Le site envoie une chaîne de certificats incomplète : sur Linux (GitHub Actions)
                # la vérification échoue. Données publiques en lecture seule -> repli sans vérification.
                if not isinstance(exc.reason, ssl.SSLCertVerificationError):
                    raise
                resp = urllib.request.urlopen(req, timeout=60, context=ssl._create_unverified_context())
            html = resp.read().decode("utf-8")
            m = SETTINGS_RE.search(html)
            if not m:
                raise ValueError("bloc drupal-settings-json introuvable")
            return json.loads(m.group(1))
        except Exception as exc:  # réseau, 5xx, structure changée
            last = exc
            _time.sleep(3 * (i + 1))
    raise RuntimeError(f"échec {url}: {last}")


def fr(d, default=""):
    if isinstance(d, dict):
        return (d.get("fr") or d.get("en") or default).strip()
    return (d or default) if isinstance(d, str) else default


def num(v):
    return "" if v is None else v


def write_rows(name: str, day: str, rows: list[dict], rewrite: bool = False):
    if not rows and not rewrite:
        return
    folder = CSV_DIR / day
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.csv"
    cols = [c for c, _ in SCHEMAS[name]]
    new = rewrite or not path.exists()
    with path.open("w" if rewrite else "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerows(rows)


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8")


def parse_actions(lm, ctx):
    cours, carnet = [], []
    for a in lm.get("actions", []):
        sym = a["symbol"].strip()
        base = dict(ctx, symbole=sym, emetteur=fr(a.get("emetteur")))
        cours.append(dict(
            base, code_emetteur=a.get("ce", ""), secteur=fr(a.get("secteur")),
            compartiment=fr(a.get("compartiment")), statut_valeur=fr(a.get("statut")),
            ouverture=num(a.get("ouverture")), plus_haut=num(a.get("plusHaut")),
            plus_bas=num(a.get("plusBas")), dernier_cours=num(a.get("dernierCours")),
            cours_reference=num(a.get("reference")), variation_pct=num(a.get("variation")),
            volume_mad=num(a.get("volume")), quantite_titres=num(a.get("quantite")),
            nb_transactions=num(a.get("nbTransactions")),
            capitalisation_mad=num(a.get("capitalisation")), nombre_titres=num(a.get("nombreTitres"))))
        carnet.append(carnet_row(base, "Action", a.get("achat") or {}, a.get("vente") or {},
                                 a.get("dernierCours"), a.get("reference")))
    return cours, carnet


def carnet_row(base, instrument, achat, vente, dernier, ref):
    bp, ap = achat.get("prix"), vente.get("prix")
    both = bp is not None and ap is not None
    mid = (bp + ap) / 2 if both else None
    return dict(base, instrument=instrument, achat_prix=num(bp), achat_quantite=num(achat.get("quantite")),
                vente_prix=num(ap), vente_quantite=num(vente.get("quantite")),
                prix_milieu=num(mid), spread=num(ap - bp if both else None),
                spread_pct=num(round((ap - bp) / mid * 100, 4) if both and mid else None),
                dernier_cours=num(dernier), cours_reference=num(ref))


def parse_autres(ctx):
    autres, carnet = [], []
    droits = fetch_settings("droits")["live_market"].get("droits", [])
    for d in droits:
        base = dict(ctx, symbole=d["symbol"].strip(), emetteur=fr(d.get("emitter")))
        autres.append(dict(
            ctx, categorie="Droit", symbole=d["symbol"].strip(), libelle=fr(d.get("label")),
            sous_jacent=d.get("underlying", ""), statut_valeur=fr(d.get("status")),
            cours_reference=num(d.get("ref_price")), ouverture=num(d.get("open")),
            dernier_cours=num(d.get("price")), plus_haut=num(d.get("high")), plus_bas=num(d.get("low")),
            variation_pct=num(d.get("change_pct")), quantite_titres=num(d.get("quantity")),
            volume_mad=num(d.get("volume")), achat_prix=num(d.get("bid_price")),
            achat_quantite=num(d.get("bid_qty")), vente_prix=num(d.get("ask_price")),
            vente_quantite=num(d.get("ask_qty"))))
        carnet.append(carnet_row(base, "Droit", {"prix": d.get("bid_price"), "quantite": d.get("bid_qty")},
                                 {"prix": d.get("ask_price"), "quantite": d.get("ask_qty")},
                                 d.get("price"), d.get("ref_price")))
    for d in fetch_settings("produits-derives")["live_market"].get("derives", []):
        autres.append(dict(
            ctx, categorie="Dérivé", symbole=d["symbol"], libelle=fr(d.get("label")),
            sous_jacent=d.get("underlying", ""), statut_valeur=fr(d.get("status")),
            cours_reference=num(d.get("refPrice")), ouverture=num(d.get("openPrice")),
            dernier_cours=num(d.get("lastPrice")), plus_haut=num(d.get("high")), plus_bas=num(d.get("low")),
            variation_pct=num(d.get("changePct")), quantite_titres=num(d.get("quantityTraded")),
            volume_mad=num(d.get("volume")), nb_transactions=num(d.get("nbTransactions")),
            achat_prix=num(d.get("bestBidPrice")), achat_quantite=num(d.get("bestBidQty")),
            vente_prix=num(d.get("bestAskPrice")), vente_quantite=num(d.get("bestAskQty")),
            echeance=d.get("maturityDate", ""), cours_compensation=num(d.get("coursCompensation")),
            positions_ouvertes=num(d.get("positionOuverte"))))
        base = dict(ctx, symbole=d["symbol"], emetteur=fr(d.get("label")))
        carnet.append(carnet_row(base, "Dérivé", {"prix": d.get("bestBidPrice"), "quantite": d.get("bestBidQty")},
                                 {"prix": d.get("bestAskPrice"), "quantite": d.get("bestAskQty")},
                                 d.get("lastPrice"), d.get("refPrice")))
    return autres, carnet


def parse_indices(lm_idx, ctx):
    seen, rows = set(), []
    for famille in ("principaux", "all"):
        for i in lm_idx.get(famille, []):
            if i["code"] in seen:
                continue
            seen.add(i["code"])
            rows.append(dict(
                ctx, code=i["code"], indice=fr(i.get("label")), famille=fr(i.get("type_label"), famille),
                valeur=num(i.get("value")), cloture_precedente=num(i.get("previous_close")),
                variation_pct=num(i.get("change_pct")), variation_ytd_pct=num(i.get("change_ytd")),
                plus_haut=num(i.get("high")), plus_bas=num(i.get("low"))))
    return rows


CAT = {"actions": "Action", "rights": "Droit", "bonds": "Obligation", "funds": "Fonds", "futures": "Dérivé"}


def parse_tape(tp, capture):
    """Tape complète de la dernière séance : une ligne par transaction."""
    by_day: dict[str, list[dict]] = {}
    for key, cat in CAT.items():
        counter = Counter()
        for t in tp.get(key, []):
            raw = t.get("time") or ""
            ident = (t["symbol"], raw, t.get("price"), t.get("quantity"), fr(t.get("market_label")))
            counter[ident] += 1
            day = raw[:10] or "inconnu"
            by_day.setdefault(day, []).append(dict(
                date=day, heure=raw[11:19], symbole=t["symbol"].strip(), instrument=fr(t.get("label")),
                categorie=cat, marche=fr(t.get("market_label")), prix=num(t.get("price")),
                quantite=num(t.get("quantity")), volume_mad=num(t.get("volume")),
                horodatage_bourse=raw, rang_doublon=counter[ident], capture_le=capture))
    return by_day


def merge_tape(day: str, rows: list[dict]):
    path = CSV_DIR / day / "transactions.csv"
    keep = {}
    if path.exists():
        with path.open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                keep[(r["symbole"], r["categorie"], r["marche"], r["horodatage_bourse"], r["prix"], r["quantite"], r["rang_doublon"])] = r
    for r in rows:
        k = (r["symbole"], r["categorie"], r["marche"], r["horodatage_bourse"], str(r["prix"]), str(r["quantite"]), str(r["rang_doublon"]))
        keep.setdefault(k, r)
    ordered = sorted(keep.values(), key=lambda r: (r["horodatage_bourse"], r["symbole"]))
    write_rows("transactions", day, ordered, rewrite=True)
    return len(ordered)


def refresh_referentiel(actions, stamp):
    """Fiche de référence (ISIN, groupe de cotation, ratios…) — rafraîchie une fois par semaine."""
    rows = []
    for a in actions:
        sym, ce = a["symbol"].strip(), a.get("ce", "")
        try:
            s = fetch_settings(f"actions/cours?symbol={sym}&ce={ce}", tries=2)
            d = s["live_market"]["action_data"]
        except Exception as exc:
            print(f"  référentiel {sym}: {exc}", file=sys.stderr)
            continue
        ins = d.get("instrument_details") or {}
        perf = ins.get("performance") or {}
        ratios = sorted((d.get("financials_details") or {}).get("ratios") or [], key=lambda r: -r.get("exercice", 0))
        rt = ratios[0] if ratios else {}
        divs = sorted(d.get("dividend_details") or [], key=lambda r: -r.get("exercice", 0))
        dv = divs[0] if divs else {}
        rows.append(dict(
            symbole=sym, code_emetteur=ce, emetteur=fr(d.get("emetteur")), secteur=fr(d.get("secteur")),
            compartiment=fr(d.get("compartiment")), isin=ins.get("isin", ""),
            date_introduction=ins.get("intro_date", ""), nombre_titres=num(ins.get("shares_count")),
            valeur_nominale=num(ins.get("nominal_value")), groupe_cotation=fr(ins.get("cycle")),
            devise=fr(ins.get("currency")), perf_ytd_pct=num(perf.get("ytd")), perf_1an_pct=num(perf.get("a1")),
            perf_3ans_pct=num(perf.get("a3")), perf_5ans_pct=num(perf.get("a5")),
            exercice_ratios=num(rt.get("exercice")), per=num(rt.get("per")), pbr=num(rt.get("pbr")),
            roe_pct=num(rt.get("roe")), payout_pct=num(rt.get("payout")), rendement_div_pct=num(rt.get("divYield")),
            dernier_dividende_exercice=num(dv.get("exercice")), dernier_dividende_mad=num(dv.get("montant")),
            maj_le=stamp))
        _time.sleep(0.4)
    if rows:
        with REFERENTIEL.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=REF_COLS)
            w.writeheader()
            w.writerows(rows)
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="ignorer la fenêtre horaire de séance")
    ap.add_argument("--final", action="store_true", help="instantané de fin de journée")
    args = ap.parse_args()

    now = now_local()
    in_window = now.weekday() < 5 and WINDOW_START <= now.time() <= WINDOW_END
    if not (in_window or args.force or args.final):
        print(f"{now:%Y-%m-%d %H:%M} hors fenêtre de séance — rien à faire.")
        return 0

    main_set = fetch_settings("actions")
    lm = main_set["live_market"]
    status = (lm.get("session") or {}).get("status", "")
    quarter = now.replace(minute=now.minute // 15 * 15, second=0, microsecond=0)
    ctx = dict(horodatage=now.strftime("%Y-%m-%d %H:%M:%S"), date=now.strftime("%Y-%m-%d"),
               heure=now.strftime("%H:%M:%S"), creneau_15min=quarter.strftime("%H:%M"),
               phase_seance=phase_of(now) if not args.final else "Après clôture (final)",
               statut_seance_bourse=status)

    cours, carnet_a = parse_actions(lm, ctx)
    autres, carnet_b = parse_autres(ctx)
    indices = parse_indices(fetch_settings("indices")["live_market"].get("indices", {}), ctx)
    tape = parse_tape(fetch_settings("transactions?type=actions")["live_market"].get("transactions_page", {}), ctx["horodatage"])

    # Évite d'archiver des instantanés identiques quand le marché est fermé (week-end, jour férié).
    digest = hashlib.sha1(json.dumps(
        [[c["symbole"], c["dernier_cours"], c["volume_mad"], c["nb_transactions"], c["statut_valeur"],
          carnet["achat_prix"], carnet["achat_quantite"], carnet["vente_prix"], carnet["vente_quantite"]]
         for c, carnet in zip(cours, carnet_a)], default=str).encode()).hexdigest()
    state = load_state()
    changed = digest != state.get("digest")
    if status != "open" and not changed and not args.force:
        print(f"{ctx['horodatage']} séance « {status} » et données inchangées — instantané ignoré.")
        return 0

    day = ctx["date"]
    write_rows("cours", day, cours)
    write_rows("carnet", day, carnet_a + carnet_b)
    write_rows("indices", day, indices)
    write_rows("autres", day, autres)
    n_tape = {d: merge_tape(d, rows) for d, rows in tape.items() if d != "inconnu"}

    state.update(digest=digest, last_snapshot=ctx["horodatage"], last_status=status)
    save_state(state)
    print(f"{ctx['horodatage']} [{ctx['phase_seance']} / {status}] {len(cours)} valeurs, "
          f"{len(indices)} indices, tape {n_tape}")

    # Fiche de référence : au plus une fois par semaine
    last_ref = state.get("referentiel_maj", "")
    if not last_ref or (now - datetime.fromisoformat(last_ref)).days >= 7 or not REFERENTIEL.exists():
        try:
            n = refresh_referentiel(lm["actions"], ctx["horodatage"])
            state["referentiel_maj"] = now.isoformat()
            save_state(state)
            print(f"référentiel actualisé ({n} valeurs)")
        except Exception as exc:
            print(f"référentiel non actualisé: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
