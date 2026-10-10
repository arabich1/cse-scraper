"""Constantes et schémas partagés entre scrape.py et build_excel.py."""
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Africa/Casablanca")
BASE = "https://www.casablanca-bourse.com/live-market/"
ROOT = Path(__file__).resolve().parent.parent
CSV_DIR = ROOT / "data" / "csv"
XLSX_DIR = ROOT / "data" / "excel"
STATE_FILE = ROOT / "data" / "state.json"
REFERENTIEL = ROOT / "data" / "referentiel.csv"

# Horaires du marché au comptant (heure du Maroc) — à ajuster si la Bourse les modifie.
PHASES = [
    (time(0, 0), "Avant ouverture"),
    (time(9, 0), "Pré-ouverture"),
    (time(9, 30), "Séance continue"),
    (time(15, 30), "Fixing de clôture"),
    (time(15, 40), "Après clôture"),
]
WINDOW_START, WINDOW_END = time(9, 0), time(15, 40)  # ouverture -> fin de la séance


def now_local() -> datetime:
    return datetime.now(TZ)


def phase_of(dt: datetime) -> str:
    if dt.weekday() >= 5:
        return "Week-end"
    label = PHASES[0][1]
    for start, name in PHASES:
        if dt.time() >= start:
            label = name
    return label


# type: s = texte, f = décimal, i = entier
CTX = [  # colonnes de contexte communes à chaque instantané
    ("horodatage", "s"), ("date", "s"), ("heure", "s"), ("creneau_15min", "s"),
    ("phase_seance", "s"), ("statut_seance_bourse", "s"),
]

SCHEMAS = {
    "cours": CTX + [
        ("symbole", "s"), ("code_emetteur", "s"), ("emetteur", "s"), ("secteur", "s"),
        ("compartiment", "s"), ("statut_valeur", "s"), ("ouverture", "f"),
        ("plus_haut", "f"), ("plus_bas", "f"), ("dernier_cours", "f"),
        ("cours_reference", "f"), ("variation_pct", "f"), ("volume_mad", "f"),
        ("quantite_titres", "i"), ("nb_transactions", "i"),
        ("capitalisation_mad", "f"), ("nombre_titres", "i"),
    ],
    "carnet": CTX + [
        ("symbole", "s"), ("emetteur", "s"), ("instrument", "s"),
        ("achat_prix", "f"), ("achat_quantite", "i"),
        ("vente_prix", "f"), ("vente_quantite", "i"),
        ("prix_milieu", "f"), ("spread", "f"), ("spread_pct", "f"),
        ("dernier_cours", "f"), ("cours_reference", "f"),
    ],
    "indices": CTX + [
        ("code", "s"), ("indice", "s"), ("famille", "s"), ("valeur", "f"),
        ("cloture_precedente", "f"), ("variation_pct", "f"),
        ("variation_ytd_pct", "f"), ("plus_haut", "f"), ("plus_bas", "f"),
    ],
    "autres": CTX + [
        ("categorie", "s"), ("symbole", "s"), ("libelle", "s"), ("sous_jacent", "s"),
        ("statut_valeur", "s"), ("cours_reference", "f"), ("ouverture", "f"),
        ("dernier_cours", "f"), ("plus_haut", "f"), ("plus_bas", "f"),
        ("variation_pct", "f"), ("quantite_titres", "i"), ("volume_mad", "f"),
        ("nb_transactions", "i"), ("achat_prix", "f"), ("achat_quantite", "i"),
        ("vente_prix", "f"), ("vente_quantite", "i"), ("echeance", "s"),
        ("cours_compensation", "f"), ("positions_ouvertes", "i"),
    ],
    "transactions": [
        ("date", "s"), ("heure", "s"), ("symbole", "s"), ("instrument", "s"),
        ("categorie", "s"), ("marche", "s"), ("prix", "f"), ("quantite", "i"),
        ("volume_mad", "f"), ("horodatage_bourse", "s"), ("rang_doublon", "i"),
        ("capture_le", "s"),
    ],
}

REF_COLS = [
    "symbole", "code_emetteur", "emetteur", "secteur", "compartiment", "isin",
    "date_introduction", "nombre_titres", "valeur_nominale", "groupe_cotation",
    "devise", "perf_ytd_pct", "perf_1an_pct", "perf_3ans_pct", "perf_5ans_pct",
    "exercice_ratios", "per", "pbr", "roe_pct", "payout_pct", "rendement_div_pct",
    "dernier_dividende_exercice", "dernier_dividende_mad", "maj_le",
]
