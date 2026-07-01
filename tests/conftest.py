import os
import sys

# Rend les modules de src/ importables sans installer le paquet
# (miroir du PYTHONPATH=/app/src défini dans le Dockerfile).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
