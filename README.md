# Bourse de Casablanca – archive automatique

Scrape toutes les 15 min (séance 09h00–15h30, heure du Maroc) via GitHub Actions :
cours, carnet d'ordres (meilleure limite), indices, droits/dérivés, transactions.

- `data/csv/AAAA-MM-JJ/*.csv` : instantanés bruts (horodatage, créneau 15 min, phase de séance…)
- `data/excel/bourse_casablanca_AAAA-MM.xlsx` : classeur mensuel (mis à jour chaque soir)
- `data/referentiel.csv` : fiche des valeurs (ISIN, groupe de cotation, ratios), mise à jour hebdo

Local : `pip install -r requirements.txt`, `python scraper/scrape.py --force`, `python scraper/build_excel.py`.
