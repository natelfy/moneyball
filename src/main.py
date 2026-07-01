import os
import json
import logging
from scraper import CCBLScraper

# Configuration standardisée du logging pour ingestion K8s (fluentd/Elastic)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ingestion-pipeline")

def main():
    # URL factice/représentative pour l'exercice.
    # En production, cela serait injecté via des variables d'environnement.
    TARGET_URL = os.getenv("TARGET_URL", "https://example-ccbl-stats.com/hitting")
    OUTPUT_DIR = os.getenv("OUTPUT_DIR", "/app/data")
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_file = os.path.join(OUTPUT_DIR, "ccbl_hitters_raw.jsonl")

    scraper = CCBLScraper(target_url=TARGET_URL)
    
    try:
        html_content = scraper.fetch_page()
        players = scraper.extract_stats(html_content)
        
        if not players:
            logger.warning("Aucune donnée extraite. Arrêt du process.")
            return

        # Écriture en JSON Lines (optimisé pour l'ingestion orientée objet type S3/MinIO)
        with open(output_file, 'w', encoding='utf-8') as f:
            for player in players:
                f.write(player.model_dump_json() + "\n")
                
        logger.info(f"Ingestion réussie : {len(players)} joueurs sauvegardés dans {output_file}")

    except Exception as e:
        logger.error(f"Échec critique du pipeline d'ingestion : {e}")
        exit(1)

if __name__ == "__main__":
    main()