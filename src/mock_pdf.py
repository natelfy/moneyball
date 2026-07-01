import fitz
import boto3
import os

print("Génération du rapport PDF de scout...")

# 1. Création du document
doc = fitz.open()
page = doc.new_page()
text = """MLB AMATEUR SCOUTING REPORT
Player: Charlie Condon
Scout: Billy Beane
Date: 2024-05-10
Notes: Generational raw power. Struggles slightly with inside breaking balls but adjusts well.
Hit: 55
Power: 70
Run: 40
Arm: 55
Field: 50
Overall FV: 60"""

page.insert_text((50, 50), text)
doc.save('/tmp/condon_report.pdf')

# 2. Upload vers la couche Bronze (MinIO)
s3 = boto3.client('s3', 
                  endpoint_url='http://minio:9000', 
                  aws_access_key_id='admin', 
                  aws_secret_access_key='password123', 
                  region_name='us-east-1')

try:
    s3.head_bucket(Bucket='bronze-scout-reports')
except Exception:
    s3.create_bucket(Bucket='bronze-scout-reports')

s3.upload_file('/tmp/condon_report.pdf', 'bronze-scout-reports', 'condon_report.pdf')
print("PDF uploadé sur S3 avec succès. Prêt pour l'ingestion NLP.")