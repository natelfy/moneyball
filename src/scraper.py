import logging

import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from models import HitterStat

logger = logging.getLogger(__name__)

class CCBLScraper:
    def __init__(self, target_url: str):
        self.target_url = target_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) MLOps-Scouting-Bot/1.0'
        })

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def fetch_page(self) -> str:
        """Récupère le HTML avec politique de retry (backoff exponentiel)."""
        logger.info(f"Tentative de requête vers {self.target_url}")
        response = self.session.get(self.target_url, timeout=10)
        response.raise_for_status()
        return response.text

    def extract_stats(self, html: str) -> list[HitterStat]:
        """Extrait les statistiques avec un mapping dynamique des colonnes."""
        soup = BeautifulSoup(html, 'html.parser')
        stats = []

        table = soup.find('table')
        if not table:
            logger.error("Tableau introuvable sur la page NCAA.")
            return stats

        # 1. Extraction dynamique des en-têtes (Mapping)
        thead = table.find('thead')
        if not thead:
            logger.error("En-tête (thead) introuvable. Impossible de mapper les colonnes.")
            return stats

        headers = [th.text.strip().upper() for th in thead.find_all('th')]
        # Index des colonnes calculé une seule fois. On accepte plusieurs
        # libellés possibles par stat car la NCAA et les autres sites varient
        # d'une année/source à l'autre (ex: "K" vs "SO", "PLAYER" vs "NAME").
        header_index = {name: i for i, name in enumerate(headers)}

        def find_index(*aliases: str) -> int:
            for alias in aliases:
                if alias in header_index:
                    return header_index[alias]
            return -1

        # Fonctions utilitaires de récupération sécurisée. `cols` est passé en
        # paramètre (pas capturé depuis la boucle) pour éviter tout effet de
        # bord de closure.
        def get_val(cols, *aliases: str) -> int:
            idx = find_index(*aliases)
            if idx == -1:
                return 0 # Stat absente de cette page
            val = cols[idx].text.strip().replace('-', '0')
            return int(val) if val.isdigit() else 0

        def get_str(cols, *aliases: str) -> str:
            idx = find_index(*aliases)
            return cols[idx].text.strip() if idx != -1 else "Unknown"

        # 2. Parsing des lignes
        tbody = table.find('tbody')
        rows = tbody.find_all('tr') if tbody else table.find_all('tr')[1:]

        for row in rows:
            cols = row.find_all('td')
            if not cols or len(cols) < len(headers):
                continue

            try:
                # Création de l'objet Pydantic. Les champs absents resteront à 0.
                stat = HitterStat(
                    player_name=get_str(cols, "PLAYER", "NAME"),
                    team=get_str(cols, "TEAM"),
                    games_played=get_val(cols, "G"),
                    at_bats=get_val(cols, "AB"),
                    hits=get_val(cols, "H"),
                    home_runs=get_val(cols, "HR"),
                    walks=get_val(cols, "BB"),
                    strikeouts=get_val(cols, "K", "SO") # K ou SO selon les sites
                )
                stats.append(stat)

            except Exception as e:
                logger.warning(f"Erreur de parsing sur la ligne: {e}")

        return stats
