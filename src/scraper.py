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
        """Parse une ligne (tr) du tableau de statistiques individuelles NCAA."""
        cols = row.find_all('td')
        
        # Un tableau NCAA standard contient au moins 18 colonnes pour les frappeurs
        # Structure typique: Rank, Player, Team, Cl, Pos, G, AB, R, H, 2B, 3B, HR, RBI, BB, SO, SB, CS, BA
        if len(cols) < 15:
            return None
        
        try:
            # Extraction propre avec gestion des chaînes vides (remplacées par 0)
            def safe_int(val: str) -> int:
                clean_val = val.strip().replace('-', '0')
                return int(clean_val) if clean_val.isdigit() else 0

            return HitterStat(
                player_name=cols[1].text,
                team=cols[2].text,
                games_played=safe_int(cols[5].text),
                at_bats=safe_int(cols[6].text),
                hits=safe_int(cols[8].text),
                home_runs=safe_int(cols[11].text),
                walks=safe_int(cols[13].text),
                strikeouts=safe_int(cols[14].text)
            )
        except (ValueError, IndexError) as e:
            logger.warning(f"Erreur de parsing sur la ligne joueur {cols[1].text if len(cols)>1 else 'inconnu'}: {e}")
            return None

    def extract_stats(self, html: str) -> List[HitterStat]:
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
        
        # 2. Parsing des lignes
        tbody = table.find('tbody')
        rows = tbody.find_all('tr') if tbody else table.find_all('tr')[1:]
        
        for row in rows:
            cols = row.find_all('td')
            if not cols or len(cols) < len(headers):
                continue
                
            try:
                # Fonctions utilitaires de récupération sécurisée
                def get_val(col_name: str) -> int:
                    if col_name in headers:
                        idx = headers.index(col_name)
                        val = cols[idx].text.strip().replace('-', '0')
                        return int(val) if val.isdigit() else 0
                    return 0 # Retourne 0 si la stat n'existe pas sur cette page

                def get_str(col_name: str) -> str:
                    # La NCAA utilise parfois "PLAYER" ou "NAME" selon les années
                    if col_name in headers:
                        return cols[headers.index(col_name)].text.strip()
                    elif col_name == "PLAYER" and "NAME" in headers:
                        return cols[headers.index("NAME")].text.strip()
                    return "Unknown"

                # Création de l'objet Pydantic. Les champs absents resteront à 0.
                stat = HitterStat(
                    player_name=get_str("PLAYER"),
                    team=get_str("TEAM"),
                    games_played=get_val("G"),
                    at_bats=get_val("AB"),
                    hits=get_val("H"),
                    home_runs=get_val("HR"),
                    walks=get_val("BB"),
                    strikeouts=get_val("K") # K ou SO selon les sites
                )
                stats.append(stat)
                
            except Exception as e:
                logger.warning(f"Erreur de parsing sur la ligne: {e}")
                
        return stats