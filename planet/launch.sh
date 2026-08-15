#!/bin/bash
# Lance la 3D/2D Knowledge Map (ex-« planète de connaissance ») : régénère le graphe, sert planet/ en local, ouvre le navigateur.
# (Un serveur est requis car le globe charge graph.json par fetch() — impossible en file://.)
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
BRAIN="$(cd "$DIR/.." && pwd)"
PORT="${1:-8765}"

python3 "$BRAIN/hooks/coactivation.py"            # chaleur + session courante à jour (Étage 2)
python3 "$BRAIN/hooks/graph_export.py"            # graphe à jour avant d'ouvrir

# tue un serveur déjà sur ce port (relance propre)
lsof -ti tcp:"$PORT" 2>/dev/null | xargs kill 2>/dev/null || true

echo "📟  Planète du tronc — signature MOTHER — http://localhost:$PORT  (Ctrl+C pour arrêter)"
( sleep 1; open "http://localhost:$PORT" ) &
cd "$DIR"
exec python3 -m http.server "$PORT"
