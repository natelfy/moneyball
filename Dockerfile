# Utilisation d'une image de base fine pour réduire la surface d'attaque et le poids
FROM python:3.11-slim as builder

# Création d'un utilisateur non-root (Best practice de sécurité K8s)
RUN useradd -m mlops

WORKDIR /app

# Installation des dépendances sans cache pour optimiser l'image
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie du code source
COPY src/ ./src/

# Création du répertoire de données avec les bons droits
RUN mkdir -p /app/data && chown -R mlops:mlops /app

USER mlops

# Définition des variables d'environnement par défaut
ENV PYTHONPATH=/app/src
ENV OUTPUT_DIR=/app/data

# Point d'entrée
CMD ["python", "src/main.py"]