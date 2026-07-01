import os
import json
import logging
import boto3
import psycopg2
from psycopg2.extras import execute_values

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("silver-loader")

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("PG_HOST", "postgres"),
        port=os.getenv("PG_PORT", "5432"),
        user=os.getenv("PG_USER", "mlops"),
        password=os.getenv("PG_PASSWORD", "moneyball_password"),
        dbname=os.getenv("PG_DB", "scouting_db")
    )

def load_s3_to_postgres(bucket_name: str, file_key: str):
    # 1. Connexion S3 et téléchargement
    s3 = boto3.client('s3',
        endpoint_url=os.getenv('S3_ENDPOINT', 'http://minio:9000'),
        aws_access_key_id=os.getenv('S3_ACCESS_KEY', 'admin'),
        aws_secret_access_key=os.getenv('S3_SECRET_KEY', 'password123'),
        region_name='us-east-1'
    )
    
    # basename : évite qu'une clé S3 contenant un '/' (ex: "2024/hitters.jsonl")
    # ne pointe vers un sous-dossier /tmp inexistant, ou hors de /tmp.
    local_tmp_path = os.path.join("/tmp", os.path.basename(file_key))
    try:
        s3.download_file(bucket_name, file_key, local_tmp_path)
        logger.info(f"Fichier {file_key} téléchargé depuis S3.")
    except Exception as e:
        logger.error(f"Échec du téléchargement S3 : {e}")
        return

    # Le fichier temporaire est toujours supprimé (données vides, erreur de
    # lecture ou d'insertion) pour ne pas saturer /tmp entre deux runs.
    try:
        # 2. Lecture des données
        records = []
        with open(local_tmp_path, 'r', encoding='utf-8') as f:
            for line in f:
                data = json.loads(line)
                # On extrait les valeurs dans l'ordre de notre table SQL
                records.append((
                    data.get("player_name"), data.get("team"),
                    data.get("games_played", 0), data.get("at_bats", 0),
                    data.get("hits", 0), data.get("home_runs", 0),
                    data.get("walks", 0), data.get("strikeouts", 0)
                ))

        if not records:
            logger.warning("Aucune donnée à insérer.")
            return

        # 3. UPSERT dans PostgreSQL (Mise à jour si conflit sur la clé primaire)
        upsert_query = """
            INSERT INTO ncaa_hitting_stats
            (player_name, team, games_played, at_bats, hits, home_runs, walks, strikeouts)
            VALUES %s
            ON CONFLICT (player_name, team) DO UPDATE SET
                games_played = GREATEST(ncaa_hitting_stats.games_played, EXCLUDED.games_played),
                at_bats = GREATEST(ncaa_hitting_stats.at_bats, EXCLUDED.at_bats),
                hits = GREATEST(ncaa_hitting_stats.hits, EXCLUDED.hits),
                home_runs = GREATEST(ncaa_hitting_stats.home_runs, EXCLUDED.home_runs),
                walks = GREATEST(ncaa_hitting_stats.walks, EXCLUDED.walks),
                strikeouts = GREATEST(ncaa_hitting_stats.strikeouts, EXCLUDED.strikeouts),
                last_updated = CURRENT_TIMESTAMP;
        """

        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                # execute_values est optimisé pour les insertions en masse (Bulk Insert)
                execute_values(cur, upsert_query, records)
            conn.commit()
            logger.info(f"SUCCESS : {len(records)} prospects fusionnés dans le Data Warehouse.")
        except Exception as e:
            conn.rollback()
            logger.error(f"Échec de l'insertion SQL : {e}")
        finally:
            conn.close()
    finally:
        if os.path.exists(local_tmp_path):
            os.remove(local_tmp_path)

if __name__ == "__main__":
    BUCKET = os.getenv("S3_BUCKET", "bronze-amateur-stats")
    FILE = os.getenv("FILE_NAME")
    
    if not FILE:
        logger.error("La variable FILE_NAME est requise pour le loader.")
        exit(1)
        
    load_s3_to_postgres(BUCKET, FILE)