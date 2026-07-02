# 📕 Playbook — Construire le jeu de données réel, de A à Z

Ce document est un **mode opératoire complet** : suis les étapes dans l'ordre,
toutes les décisions sont déjà prises. À la fin tu as : un warehouse rempli de
vraies stats, des grades de scouts réels, un dataset labellisé pour valider le
modèle, et le board qui tourne sur du réel.

---

## Décisions déjà prises (tu n'as rien à choisir)

| Question | Décision | Pourquoi |
|---|---|---|
| Quel vivier ? | NCAA Division I + Cape Cod League | Le meilleur ratio qualité/accessibilité des données amateur |
| Quelles saisons ? | 2021 → saison courante (5 cohortes) | Assez pour un split temporel train/test |
| Clé joueur ? | `(player_name, team)` normalisés | Déjà la clé primaire du warehouse |
| Cible du modèle (v1) ? | La FV FanGraphs (échelle 20-80) | Disponible immédiatement, même format que `scout_grades` |
| Cible du modèle (v2) ? | « A atteint MLB sous 5 ans » via le draft + Baseball-Reference | Le vrai test moneyball, à faire une fois la v1 validée |
| Split train/test ? | **Temporel** : train 2021-2023, test 2024+ | Un split aléatoire entre années fuit de l'information |

**Règles de normalisation des noms** (à appliquer partout, avant toute jointure) :
minuscules → majuscules initiales, accents retirés, espaces multiples réduits,
suffixes `Jr.`/`Sr.`/`II`/`III` supprimés, format `"Last, First"` retourné en
`"First Last"`. Le validateur Pydantic fait déjà le `strip()`.

---

## Étape A — Infrastructure (5 min)

```bash
cp .env.example .env       # ajuste les mots de passe
make infra                 # MinIO + PostgreSQL
docker compose ps          # les 2 services doivent être "running"
```

---

## Étape B — Stats NCAA : les features (1-2 h la première fois)

> Deux voies. **La voie manuelle (B.1→B.3, export Excel/copier) est la
> recommandée** : plus fiable que le scraping, zéro souci de robots. La voie
> scraper (B.4) sert à automatiser plus tard.

### B.1 Quoi exporter, pour chaque saison (2021 → saison courante)

Sur `https://stats.ncaa.org/rankings?sport_code=MBA&division=1` :
sélectionne la **saison**, puis la catégorie individuelle, puis exporte le
tableau (bouton *Excel*, ou *Copy* → coller dans un fichier `.txt`).

| # | Catégorie NCAA | Colonnes qu'elle apporte | Nom de fichier conseillé |
|---|---|---|---|
| 1 | **Batting Average** | G, AB, H | `ncaa_d1_2024_ba.xlsx` |
| 2 | **Home Runs** | G, HR | `ncaa_d1_2024_hr.xlsx` |
| 3 | **Base on Balls** (walks) | G, BB | `ncaa_d1_2024_bb.xlsx` |
| 4 | *(si la catégorie existe)* Strikeouts frappeurs | K/SO | `ncaa_d1_2024_so.xlsx` |

C'est tout : **3 fichiers par saison** (4 si les strikeouts existent), soit
~15 exports pour 5 saisons. La fusion `GREATEST` du pipeline recompose les
profils complets à partir de ces vues partielles. Si la catégorie strikeouts
n'existe pas pour les frappeurs : pas grave — les grades (`contact`, `eye`,
`on_base`, `power`) n'en dépendent pas ; seules deux features du modèle ML
(`k_rate`, `bb_per_k`) resteront à 0.

Règles d'export :
- **Affiche le maximum de lignes avant d'exporter** (l'export ne contient que
  ce qui est affiché) ; s'il y a plusieurs pages, exporte chaque page — la
  fusion déduplique.
- **Tous les qualifiés**, pas le top 50 : indispensable pour la calibration
  (étape G).
- Garde les fichiers bruts dans `exports/<saison>/` : c'est ta couche Bronze
  locale (preuve + re-traitement sans re-télécharger).

### B.2 Convertir les exports en JSONL (une commande)

Le convertisseur `src/convert_ncaa.py` accepte `.xlsx`, `.csv` et le
copier-coller (tabulations). Il retrouve la ligne d'en-têtes même précédée de
titres, remet les noms « Last, First » en « First Last » (crucial pour les
jointures FanGraphs/draft), retire les bilans « (45-12) » collés aux équipes
(en préservant « Miami (OH) »), et valide chaque ligne via Pydantic :

```bash
make convert FILES="exports/2024/ncaa_d1_2024_ba.xlsx exports/2024/ncaa_d1_2024_hr.xlsx exports/2024/ncaa_d1_2024_bb.xlsx" OUTDIR=data_ncaa/2024
# → data_ncaa/2024/*.jsonl  (le log affiche le nombre de joueurs par fichier)
```

Vérification immédiate, sans infra — tu dois voir des noms réels et des
grades plausibles :

```bash
PYTHONPATH=src python3 src/report.py --source local --dir data_ncaa/2024 --top 15
```

### B.3 Charger dans le warehouse (2 options)

- **Option console (zéro code)** : ouvre `http://localhost:9001` (console
  MinIO), bucket `bronze-amateur-stats`, glisse-dépose les `.jsonl`, puis
  `make load FILE_NAME=ncaa_d1_2024_ba.jsonl` pour chaque fichier.
- **Option 100 % locale** : garde tout dans `data_ncaa/` — le board, la
  calibration et `evaluate --data` fonctionnent sans warehouse. PostgreSQL
  n'est indispensable que pour `make train` (le JOIN SQL stats × scouts).

### B.4 Voie scraper (automatisation, optionnelle)

Le scraper attend `<table><thead><th>…` avec des en-têtes contenant
`PLAYER`/`NAME`, `TEAM`, `G`, `AB`, `H`, `HR`, `BB`, `K`/`SO`. Vérifie sur la
première page réelle :

```bash
PYTHONPATH=src python3 - <<'PY'
from scraper import CCBLScraper
s = CCBLScraper("COLLE_ICI_L_URL_DE_LA_PAGE")
players = s.extract_stats(s.fetch_page())
print(len(players), "joueurs ;", players[0] if players else "RIEN — voir ci-dessous")
PY
```

- **≥ 50 joueurs avec noms/équipes corrects** → utilise
  `make ingest TARGET_URL=… FILE_NAME=…` puis `make load FILE_NAME=…`.
  Cadence : 3-5 s entre pages.
- **0 joueur** → ajoute les en-têtes réels comme alias dans `src/scraper.py`
  (`get_str`/`get_val`).
- **Erreur HTTP/403** → reste sur la voie manuelle B.1→B.3 : c'est son rôle.

### B.5 Contrôles qualité (à chaque saison chargée)

```sql
-- dans psql (make infra ; docker compose exec postgres psql -U mlops scouting_db)
SELECT COUNT(*) FROM ncaa_hitting_stats;                          -- attendu : 1500-3000/saison
SELECT COUNT(*) FROM ncaa_hitting_stats WHERE at_bats > 0;        -- attendu : > 80 %
SELECT player_name, COUNT(DISTINCT team) c FROM ncaa_hitting_stats
GROUP BY player_name HAVING COUNT(DISTINCT team) > 1 LIMIT 10;    -- homonymes à vérifier
```

Red flags : < 500 lignes (pagination ratée) ; > 50 % de `at_bats = 0` (tu n'as
chargé que la catégorie HR) ; des noms vides (mapping de colonnes cassé).

---

## Étape C — Cape Cod League (optionnel, recommandé : 30 min)

Les stats officielles CCBL sont chez Pointstreak (`leagueid=166`) :
`https://pointstreak.com/baseball/stats.html?leagueid=166&seasonid=…` et le
menu des saisons `https://baseball.pointstreak.com/textstats/menu_seasons.html?leagueid=166`.
Même procédure que l'étape B : exporte/copie les tableaux de frappeurs, puis
`make convert` (le convertisseur gère les mêmes formats) — ou la voie scraper
B.4. Intérêt : la CCBL utilise des battes en bois — signal plus proche du
niveau pro.

---

## Étape D — Grades de scouts réels : FanGraphs The Board (30 min)

1. Va sur `https://www.fangraphs.com/prospects/the-board`, section **Draft**,
   année correspondant à ta cohorte (les classes 2021…2025 sont archivées).
2. Utilise le bouton **Export Data** (CSV). Crée un compte FanGraphs si le
   bouton l'exige. **Respecte leurs CGU** : usage personnel/recherche, pas de
   republication du fichier.
3. Convertis le CSV en JSONL `scout_grades` avec ce mapping :

| Colonne FanGraphs | Champ pipeline | Règle |
|---|---|---|
| `Name` | `player_name` | normalisation des noms (voir plus haut) |
| — | `scout_name` | mets `"FanGraphs Board 2024"` (la source fait office de scout) |
| `Hit` (future) | `hit_grade` | d'un `"40/55"` prends la **future** (55) ; un `"45+"` → 45 |
| `Game Pwr` (future) | `power_grade` | idem |
| `FV` | `overall_fv` | `"45+"` → 45 |

```bash
python3 - <<'PY'
import csv, json, re
def grade(v, default=40):
    m = re.findall(r"\d{2}", str(v));  return int(m[-1]) if m else default
with open("board_draft_2024.csv") as f, open("scouts_2024.jsonl", "w") as out:
    for r in csv.DictReader(f):
        out.write(json.dumps({
            "player_name": r["Name"].strip(),
            "scout_name": "FanGraphs Board 2024",
            "hit_grade": grade(r.get("Hit")),
            "power_grade": grade(r.get("Game Pwr")),
            "overall_fv": grade(r.get("FV"), 40),
        }) + "\n")
PY
```

4. Vérifie immédiatement le croisement :

```bash
PYTHONPATH=src python3 src/report.py --source postgres --scouts scouts_2024.jsonl --top 20
```

Taux de croisement attendu : **60-80 %** des joueurs du Board matchent tes
stats NCAA. C'est normal (lycéens draftés, JUCO, orthographes) — **ne force pas
le reste**, un faux match est pire qu'un manquant. Pour les cas ambigus, le
référentiel d'identités Chadwick (`github.com/chadwickbureau/register`, CSV)
tranche par date de naissance/école.

---

## Étape E — Labels de draft : l'API MLB officielle (30 min)

JSON public, sans authentification, une URL par année :

```bash
for Y in 2021 2022 2023 2024; do
  curl -s "https://statsapi.mlb.com/api/v1/draft/$Y" -o "draft_$Y.json"; sleep 3
done
python3 - <<'PY'
import json
for y in (2021, 2022, 2023, 2024):
    d = json.load(open(f"draft_{y}.json"))
    picks = [p for r in d["drafts"]["rounds"] for p in r["picks"]]
    with open(f"draft_{y}.jsonl", "w") as out:
        for p in picks:
            out.write(json.dumps({
                "player_name": p["person"]["fullName"],
                "school": (p.get("school") or {}).get("name"),
                "year": y, "round": p["pickRound"], "pick": p["pickNumber"],
                "bonus": p.get("signingBonus"),
            }) + "\n")
    print(y, len(picks), "picks")
PY
```

Pour la **cible v2** (issue de carrière) : `baseball-reference.com/draft/`
(Draft Finder) affiche le WAR atteint par pick ; export **manuel** via
« Share & more → Get table as CSV » (pas de scraping automatisé chez eux, c'est
leur règle). Une page par année, 5 minutes au total.

---

## Étape F — Assembler le dataset labellisé (1 h)

Objectif : un JSONL où **chaque ligne = un joueur d'une cohorte**, avec ce
schéma exact (celui que `evaluate.py --data` attend) :

```json
{"games_played": 55, "at_bats": 210, "hits": 74, "home_runs": 18,
 "walks": 41, "strikeouts": 39,
 "hit_grade": 55, "power_grade": 60, "run_grade": 45, "arm_grade": 50,
 "field_grade": 50, "overall_fv": 50}
```

Procédure :
1. Extrais les stats de la cohorte N du warehouse (`SELECT … WHERE` ou les
   JSONL Bronze de la saison N).
2. Joins avec `scouts_N.jsonl` (étape D) **par nom normalisé** : le
   `overall_fv` FanGraphs devient le label. `run/arm/field_grade` absents des
   stats : mets 50 (neutre) ou reprends-les du Board s'ils y sont.
3. **Anti-fuite absolu** : les features viennent de la saison N uniquement, le
   label de l'année N. Jamais de stat postérieure au draft dans les features.
4. Concatène les cohortes → `labeled_2021_2024.jsonl`, puis :

```bash
make evaluate DATA=labeled_2021_2024.jsonl
```

Lecture du rapport : une **amélioration < 10 % vs baseline** = problème de
jointure (vérifie 20 lignes à la main) ou features trop pauvres — pas un
échec du concept. Volume cible : **300-600 lignes labellisées** sur 4 cohortes
(c'est un dataset de draft, pas du big data — c'est suffisant pour la MAE).

---

## Étape G — Calibration + board final (15 min)

Calibre les grades sur la **population complète** de l'étape B (jamais sur un
fichier de leaders — biais vers le haut documenté dans `scoring.py`) :

```bash
PYTHONPATH=src python3 - <<'PY'
import json, glob
from scoring import calibrate_benchmarks
recs = [json.loads(l) for f in glob.glob("data_ncaa_full/*.jsonl") for l in open(f) if l.strip()]
print(calibrate_benchmarks(recs))   # colle le résultat dans BENCHMARKS de scoring.py
PY
make board-html   # remplace --scouts par ton scouts_2025.jsonl réel dans le Makefile
```

---

## Garde-fous (légal + technique)

- **stats.ncaa.org / Pointstreak** : données publiques ; usage
  personnel/recherche OK ; cadence 1 page / 3-5 s ; User-Agent honnête (déjà
  configuré) ; ne republie pas les données brutes.
- **FanGraphs** : l'export est lié à ton compte ; ne redistribue pas le CSV.
- **Baseball-Reference** : pas de scraping automatisé — exports CSV manuels.
- **statsapi.mlb.com** : API publique de MLB, non documentée officiellement ;
  usage raisonnable (quelques requêtes, pas de polling).
- Archive tout HTML/CSV brut en Bronze (MinIO) : re-traitement sans re-scrape.

## Checklist finale

- [ ] A. `make infra` — MinIO + PostgreSQL up
- [ ] B. 3 catégories × 5 saisons NCAA ingérées et chargées, contrôles SQL OK
- [ ] C. (option) Cape Cod chargée
- [ ] D. Board FanGraphs exporté → `scouts_*.jsonl`, croisement 60-80 %
- [ ] E. Drafts 2021-2024 récupérés via l'API MLB
- [ ] F. `labeled_*.jsonl` assemblé → `make evaluate DATA=…` > +10 % vs baseline
- [ ] G. Benchmarks calibrés sur population complète → `make board-html`
