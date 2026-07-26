#!/usr/bin/env python3
"""Status line Claude Code : % contexte restant + coût/durée de session.

Reçoit en stdin le JSON de session de Claude Code. Calcule le contexte
utilisé en relisant le dernier `usage` du transcript (input + cache),
puis affiche le % restant, le coût et la durée.
"""
import sys, json, os, subprocess, glob, time, datetime

# Limite de contexte (tokens). Opus/Sonnet = 200k. La zone "auto-compact"
# se déclenche ~avant la limite dure, on reste sur 200k comme référence.
CTX_LIMIT = 200_000

# Conso du jour : Claude Code n'expose nulle part le vrai compteur d'abonnement,
# on l'approxime en sommant l'usage des transcripts depuis minuit. Cache court
# pour ne pas relire les .jsonl à chaque redessin de la barre.
USAGE_CACHE = os.path.expanduser("~/.claude/.usage_today_cache.json")
USAGE_TTL = 25  # secondes

# Prix API ($/million de tokens) par famille de modèle. cache_read = 0.1x input,
# cache_write (5 min) = 1.25x input. Sert uniquement à l'équivalent ≈$ théorique.
PRICING = {
    "opus":   (15.0, 75.0),
    "sonnet": (3.0, 15.0),
    "haiku":  (1.0, 5.0),
}

def model_family(name):
    n = (name or "").lower()
    for fam in PRICING:
        if fam in n:
            return fam
    return "opus"  # défaut prudent (le plus cher)

def today_usage():
    """(usd, out_tokens) consommés depuis minuit, toutes sessions. Caché 25 s."""
    now = time.time()
    try:
        with open(USAGE_CACHE) as f:
            c = json.load(f)
        if now - c.get("ts", 0) < USAGE_TTL:
            return c["usd"], c["out"]
    except (OSError, ValueError, KeyError):
        pass

    midnight = datetime.datetime.now().replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    mid_ts = midnight.timestamp()
    usd = 0.0
    out_total = 0
    for path in glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl")):
        try:
            if os.path.getmtime(path) < mid_ts:
                continue
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        o = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    t = o.get("timestamp")
                    if not t:
                        continue
                    try:
                        d = datetime.datetime.fromisoformat(
                            t.replace("Z", "+00:00")
                        ).astimezone().replace(tzinfo=None)
                    except ValueError:
                        continue
                    if d < midnight:
                        continue
                    msg = o.get("message") or {}
                    u = msg.get("usage")
                    if not u:
                        continue
                    inp, outp = PRICING[model_family(msg.get("model"))]
                    i = u.get("input_tokens", 0)
                    out = u.get("output_tokens", 0)
                    cr = u.get("cache_read_input_tokens", 0)
                    cw = u.get("cache_creation_input_tokens", 0)
                    usd += (
                        i * inp + out * outp
                        + cr * inp * 0.1 + cw * inp * 1.25
                    ) / 1_000_000
                    out_total += out
        except OSError:
            continue

    try:
        with open(USAGE_CACHE, "w") as f:
            json.dump({"ts": now, "usd": usd, "out": out_total}, f)
    except OSError:
        pass
    return usd, out_total

def c(code, s):
    return f"\033[{code}m{s}\033[0m"

def read_context_tokens(transcript_path):
    """Dernier usage du transcript = empreinte contexte courante."""
    if not transcript_path or not os.path.exists(transcript_path):
        return None
    last = None
    try:
        with open(transcript_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                usage = (obj.get("message") or {}).get("usage")
                if usage:
                    last = usage
    except OSError:
        return None
    if not last:
        return None
    return (
        last.get("input_tokens", 0)
        + last.get("cache_read_input_tokens", 0)
        + last.get("cache_creation_input_tokens", 0)
    )

def git_branch(cwd):
    """Branche git courante, ou None hors dépôt."""
    if not cwd or not os.path.isdir(cwd):
        return None
    try:
        out = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    branch = out.stdout.strip()
    return branch or None

def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        data = {}

    parts = []

    # --- Modèle ---
    model = (data.get("model") or {}).get("display_name")
    if model:
        parts.append(c("1;35", model))

    # --- Branche git ---
    cwd = (data.get("workspace") or {}).get("current_dir") or data.get("cwd")
    branch = git_branch(cwd)
    if branch:
        parts.append(c("34", f"⎇ {branch}"))

    # --- Contexte ---
    used = read_context_tokens(data.get("transcript_path"))
    if used is not None:
        remaining_pct = max(0, min(100, round((1 - used / CTX_LIMIT) * 100)))
        if remaining_pct <= 15:
            color = "1;31"   # rouge gras
        elif remaining_pct <= 35:
            color = "33"     # jaune
        else:
            color = "32"     # vert
        parts.append(c(color, f"ctx {remaining_pct}%") + c("90", f" ({used//1000}k/{CTX_LIMIT//1000}k)"))
    else:
        parts.append(c("90", "ctx —"))

    # --- Coût ---
    cost = data.get("cost") or {}
    usd = cost.get("total_cost_usd")
    if usd is not None:
        # Abonnement : pas de coût réel au token. C'est l'équivalent API théorique.
        parts.append(c("36", f"≈${usd:.2f} API"))

    # --- Durée ---
    dur_ms = cost.get("total_duration_ms")
    if dur_ms is not None:
        secs = dur_ms // 1000
        h, rem = divmod(secs, 3600)
        m, s = divmod(rem, 60)
        dur = f"{h}h{m:02d}m" if h else (f"{m}m{s:02d}s" if m else f"{s}s")
        parts.append(c("90", dur))

    # --- Conso du jour (toutes sessions, depuis minuit) ---
    try:
        day_usd, day_out = today_usage()
    except Exception:
        day_usd, day_out = None, None
    if day_usd is not None:
        out_str = f"{day_out/1_000_000:.1f}M" if day_out >= 1_000_000 else f"{day_out//1000}k"
        parts.append(c("1;35", f"📅 ≈${day_usd:.0f}") + c("90", f" ({out_str} out)"))

    sys.stdout.write(c("90", " | ").join(parts))

    # --- Ligne 2 : modifications de code de CETTE session (Companion) ---------
    # Intégré à la session, tout en bas, en permanence — pas de fenêtre flottante.
    try:
        sys.path.insert(0, os.path.expanduser("~/claude-brain/companion"))
        import status_part
        second = status_part.line(data.get("session_id"))
        if second:
            sys.stdout.write("\n" + second)
    except Exception:
        pass          # la barre ne doit jamais casser à cause du suivi de diffs

if __name__ == "__main__":
    main()
