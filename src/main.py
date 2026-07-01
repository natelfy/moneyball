import os
import logging
import boto3
from botocore.exceptions import ClientError
from scraper import CCBLScraper

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ingestion-pipeline")

def upload_to_s3(file_path: str, bucket_name: str, object_name: str):
    """Pousse le fichier dans le Datalake compatible S3."""
    s3 = boto3.client('s3',
        endpoint_url=os.getenv('S3_ENDPOINT', 'http://minio:9000'),
        aws_access_key_id=os.getenv('S3_ACCESS_KEY', 'admin'),
        aws_secret_access_key=os.getenv('S3_SECRET_KEY', 'password123'),
        region_name='us-east-1' # Requis par boto3 même pour MinIO
    )
    
    try:
        # Vérification et création du bucket (Dossier racine du Datalake)
        try:
            s3.head_bucket(Bucket=bucket_name)
        except ClientError:
            logger.info(f"Création du bucket S3 : {bucket_name}")
            s3.create_bucket(Bucket=bucket_name)

        # Upload
        s3.upload_file(file_path, bucket_name, object_name)
        logger.info(f"SUCCESS: {object_name} archivé dans le bucket '{bucket_name}'.")
    except Exception as e:
        logger.error(f"Échec de l'upload S3 : {e}")
        raise

def main():
    TARGET_URL = os.getenv("TARGET_URL")
    OUTPUT_DIR = os.getenv("OUTPUT_DIR", "/app/data")
    FILE_NAME = os.getenv("FILE_NAME", "raw_extract.jsonl")
    BUCKET_NAME = os.getenv("S3_BUCKET", "bronze-amateur-stats")
    
    if not TARGET_URL:
        logger.error("TARGET_URL non définie. Arrêt.")
        exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    local_file_path = os.path.join(OUTPUT_DIR, FILE_NAME)

    scraper = CCBLScraper(target_url=TARGET_URL)
    
    try:
        html_content = scraper.fetch_page()
        players = scraper.extract_stats(html_content)
        
        if not players:
            logger.warning("Aucune donnée. Abandon de l'ingestion.")
            return

        # 1. Écriture du cache local
        with open(local_file_path, 'w', encoding='utf-8') as f:
            for player in players:
                f.write(player.model_dump_json() + "\n")
                
        logger.info(f"Extraction terminée : {len(players)} joueurs identifiés.")

        # 2. Archivage dans le Datalake
        upload_to_s3(local_file_path, BUCKET_NAME, FILE_NAME)

    except Exception as e:
        logger.error(f"Échec critique : {e}")
        exit(1)

if __name__ == "__main__":
    main()