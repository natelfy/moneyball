import logging
import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential
from typing import List, Optional
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

    def parse_hitter_row(self, row) -> Optional[HitterStat]:
        """Parse une ligne (tr) du tableau HTML en objet Pydantic."""
        cols = row.find_all('td')
        if len(cols) < 10:
            return None
        
        try:
            # L'indexation dépend de la structure réelle du site cible.
            # Ceci est un mapping standard de démo industriel.
            return HitterStat(
                player_name=cols[0].text,
                team=cols[1].text,
                games_played=int(cols[2].text or 0),
                at_bats=int(cols[3].text or 0),
                hits=int(cols[5].text or 0),
                home_runs=int(cols[8].text or 0),
                walks=int(cols[11].text or 0),
                strikeouts=int(cols[12].text or 0)
            )
        except (ValueError, IndexError) as e:
            logger.warning(f"Erreur de parsing sur la ligne: {e}")
            return None

    def extract_stats(self, html: str) -> List[HitterStat]:
        """Extrait toutes les statistiques de la page."""
        soup = BeautifulSoup(html, 'html.parser')
        stats = []
        
        # Ciblage générique d'un tableau de statistiques
        table = soup.find('table', {'class': 'stats-table'})
        if not table:
            logger.error("Tableau des statistiques introuvable sur la page.")
            return stats

        rows = table.find('tbody').find_all('tr') if table.find('tbody') else table.find_all('tr')[1:]
        
        for row in rows:
            stat = self.parse_hitter_row(row)
            if stat:
                stats.append(stat)
                
        return stats