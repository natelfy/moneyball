import os
import re
import logging
import boto3
import fitz  # PyMuPDF
import psycopg2
from pydantic import BaseModel, Field, ValidationError

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("nlp-scout-parser")

# 1. Définition stricte du schéma du rapport (Validation MLOps)
class ScoutReport(BaseModel):
    player_name: str
    scout_name: str
    hit_grade: int = Field(ge=20, le=80, multiple_of=5)
    power_grade: int = Field(ge=20, le=80, multiple_of=5)
    run_grade: int = Field(ge=20, le=80, multiple_of=5)
    arm_grade: int = Field(ge=20, le=80, multiple_of=5)
    field_grade: int = Field(ge=20, le=80, multiple_of=5)
    overall_fv: int = Field(ge=20, le=80, multiple_of=5)

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("PG_HOST", "postgres"),
        port=os.getenv("PG_PORT", "5432"),
        user=os.getenv("PG_USER", "mlops"),
        password=os.getenv("PG_PASSWORD", "moneyball_password"),
        dbname=os.getenv("PG_DB", "scouting_db")
    )

def extract_text_from_pdf(local_path: str) -> str:
    """Extrait le texte brut d'un PDF via PyMuPDF."""
    text = ""
    try:
        with fitz.open(local_path) as doc:
            for page in doc:
                text += page.get_text()
        return text
    except Exception as e:
        logger.error(f"Échec de lecture du PDF : {e}")
        raise

def parse_scout_text(text: str) -> ScoutReport:
    """Parse le texte non-structuré via Regex et valide via Pydantic."""
    try:
        # Regex dynamiques pour isoler les métriques dans le chaos d'un rapport texte
        player_match = re.search(r"(?i)Player:\s*([A-Za-z\s\-\']+)", text)
        scout_match = re.search(r"(?i)Scout:\s*([A-Za-z\s\-\']+)", text)
        
        # Extraction de l'échelle 20-80 (ex: "Hit: 55" ou "Hit Grade - 60")
        def get_grade(tool: str) -> int:
            match = re.search(rf"(?i){tool}.*?(20|25|30|35|40|45|50|55|60|65|70|75|80)", text)
            return int(match.group(1)) if match else 40 # 40 = Moyenne basse par défaut (MLB average is 50)

        # Création et validation stricte de l'objet
        return ScoutReport(
            player_name=player_match.group(1).strip() if player_match else "Unknown Player",
            scout_name=scout_match.group(1).strip() if scout_match else "Unknown Scout",
            hit_grade=get_grade("Hit"),
            power_grade=get_grade("Power"),
            run_grade=get_grade("Run"),
            arm_grade=get_grade("Arm"),
            field_grade=get_grade("Field"),
            overall_fv=get_grade("Overall FV")
        )
    except ValidationError as e:
        logger.error(f"Données de scout invalides (Hors échelle 20-80) : {e}")
        raise
    except Exception as e:
        logger.error(f"Échec du parsing NLP : {e}")
        raise

def process_report(bucket_name: str, file_key: str):
    s3 = boto3.client('s3',
        endpoint_url=os.getenv('S3_ENDPOINT', 'http://minio:9000'),
        aws_access_key_id=os.getenv('S3_ACCESS_KEY', 'admin'),
        aws_secret_access_key=os.getenv('S3_SECRET_KEY', 'password123'),
        region_name='us-east-1'
    )
    
    local_tmp = f"/tmp/{file_key}"
    try:
        s3.download_file(bucket_name, file_key, local_tmp)
        logger.info(f"Rapport {file_key} téléchargé depuis la couche Bronze.")
        
        # Extract & Transform (NLP)
        raw_text = extract_text_from_pdf(local_tmp)
        report = parse_scout_text(raw_text)
        logger.info(f"NLP Réussi pour le joueur : {report.player_name} (FV: {report.overall_fv})")

        # Load (PostgreSQL)
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO scout_grades 
                (player_name, scout_name, hit_grade, power_grade, run_grade, arm_grade, field_grade, overall_fv)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (player_name, scout_name) DO UPDATE SET
                    hit_grade = EXCLUDED.hit_grade,
                    power_grade = EXCLUDED.power_grade,
                    run_grade = EXCLUDED.run_grade,
                    arm_grade = EXCLUDED.arm_grade,
                    field_grade = EXCLUDED.field_grade,
                    overall_fv = EXCLUDED.overall_fv,
                    report_date = CURRENT_TIMESTAMP;
            """, (
                report.player_name, report.scout_name, report.hit_grade, 
                report.power_grade, report.run_grade, report.arm_grade, 
                report.field_grade, report.overall_fv
            ))
        conn.commit()
        conn.close()
        logger.info(f"Notes qualitatives fusionnées dans la couche Silver.")

    except Exception as e:
        logger.error(f"Échec du traitement global : {e}")
    finally:
        if os.path.exists(local_tmp):
            os.remove(local_tmp)

if __name__ == "__main__":
    BUCKET = os.getenv("S3_BUCKET", "bronze-scout-reports")
    FILE = os.getenv("FILE_NAME")
    if not FILE:
        logger.error("La variable FILE_NAME est requise.")
        exit(1)
    process_report(BUCKET, FILE)