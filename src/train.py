import os
import logging
import pandas as pd
import psycopg2
import boto3
import joblib
from typing import Tuple
from xgboost import XGBRegressor
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ml-trainer")

def extract_features() -> pd.DataFrame:
    """Croise la donnée quantitative (Bronze) et qualitative (Silver) via INNER JOIN."""
    query = """
        SELECT 
            n.games_played, n.at_bats, n.hits, n.home_runs, n.walks, n.strikeouts,
            s.hit_grade, s.power_grade, s.run_grade, s.arm_grade, s.field_grade,
            s.overall_fv
        FROM ncaa_hitting_stats n
        INNER JOIN scout_grades s ON n.player_name = s.player_name;
    """
    try:
        conn = psycopg2.connect(
            host=os.getenv("PG_HOST", "postgres"),
            port=os.getenv("PG_PORT", "5432"),
            user=os.getenv("PG_USER", "mlops"),
            password=os.getenv("PG_PASSWORD", "moneyball_password"),
            dbname=os.getenv("PG_DB", "scouting_db")
        )
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except Exception as e:
        logger.error(f"Échec de l'extraction des features : {e}")
        raise

def train_model(df: pd.DataFrame) -> Pipeline:
    """Entraîne un pipeline Scikit-Learn/XGBoost pour prédire la Draft Suitability (FV)."""
    if df.empty:
        raise ValueError("Le Feature Store est vide. L'entraînement est annulé.")
        
    # Séparation Features (X) et Target (y)
    X = df.drop(columns=['overall_fv'])
    y = df['overall_fv']
    
    # Construction du pipeline (Normalisation + Algorithme)
    pipeline = Pipeline([
        ('scaler', StandardScaler()),
        ('xgb', XGBRegressor(n_estimators=100, learning_rate=0.1, max_depth=3, random_state=42))
    ])

    # Logique de protection architecturale pour les tests unitaires avec peu de données
    if len(df) < 5:
        logger.warning("Volume de données insuffisant pour un split Train/Test. Entraînement PoC (Sur-apprentissage volontaire).")
        pipeline.fit(X, y)
        mae = mean_absolute_error(y, pipeline.predict(X))
        logger.info(f"Modèle Proof-of-Concept généré. MAE d'entraînement : {mae:.2f}")
        return pipeline
        
    # Validation MLOps standard
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    pipeline.fit(X_train, y_train)
    
    preds = pipeline.predict(X_test)
    mae = mean_absolute_error(y_test, preds)
    logger.info(f"Entraînement validé. Erreur Absolue Moyenne (MAE) : {mae:.2f} points de FV")
    
    return pipeline

def upload_model_to_s3(model: Pipeline, bucket_name: str, file_name: str) -> None:
    """Versionne l'algorithme entraîné dans le Model Registry S3."""
    local_path = f"/tmp/{file_name}"
    joblib.dump(model, local_path)
    
    s3 = boto3.client('s3',
        endpoint_url=os.getenv('S3_ENDPOINT', 'http://minio:9000'),
        aws_access_key_id=os.getenv('S3_ACCESS_KEY', 'admin'),
        aws_secret_access_key=os.getenv('S3_SECRET_KEY', 'password123'),
        region_name='us-east-1'
    )
    
    try:
        try:
            s3.head_bucket(Bucket=bucket_name)
        except Exception:
            logger.info(f"Création du bucket de Model Registry : {bucket_name}")
            s3.create_bucket(Bucket=bucket_name)
            
        s3.upload_file(local_path, bucket_name, file_name)
        logger.info(f"Modèle packagé poussé dans le Datalake : s3://{bucket_name}/{file_name}")
    except Exception as e:
        logger.error(f"Échec de l'archivage du modèle : {e}")
        raise
    finally:
        if os.path.exists(local_path):
            os.remove(local_path)

if __name__ == "__main__":
    dataset = extract_features()
    model = train_model(dataset)
    
    MODEL_BUCKET = os.getenv("S3_MODEL_BUCKET", "ml-models")
    MODEL_VERSION = os.getenv("MODEL_NAME", "draft_fv_predictor_v1.joblib")
    
    upload_model_to_s3(model, MODEL_BUCKET, MODEL_VERSION)