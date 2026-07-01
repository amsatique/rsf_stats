"""Minimal i18n: English/French strings and a `translate()` lookup."""

from __future__ import annotations

LANGS = ("en", "fr")

_STRINGS: dict[str, dict[str, str]] = {
    # --- Navigation / common ---
    "nav.overview": {"en": "Overview", "fr": "Aperçu"},
    "nav.stages": {"en": "Stages", "fr": "Spéciales"},
    "nav.analysis": {"en": "Analysis", "fr": "Analyse"},
    "nav.compete": {"en": "Compete", "fr": "Compétition"},
    "nav.rallies_online": {"en": "Rallies", "fr": "Rallyes"},
    "nav.dashboard": {"en": "dashboard", "fr": "tableau de bord"},
    "nav.targets": {"en": "Targets", "fr": "Cibles"},
    "nav.rivals": {"en": "Rivals", "fr": "Rivaux"},
    "nav.refresh": {"en": "Refresh", "fr": "Rafraîchir"},
    "nav.back": {"en": "back to my board", "fr": "retour à mon tableau"},
    "nav.json": {"en": "JSON API", "fr": "API JSON"},
    "nav.csv": {"en": "CSV", "fr": "CSV"},
    "common.updated": {"en": "updated", "fr": "mis à jour"},
    "common.ago": {"en": "ago", "fr": "il y a"},
    "common.just_now": {"en": "just now", "fr": "à l'instant"},
    # --- Dashboard ---
    "dash.subtitle": {
        "en": "RallySimFans hotlap progress — completion & reference times per stage",
        "fr": "Progression RallySimFans — complétion & temps de référence par spéciale",
    },
    "dash.total_stages": {"en": "Total stages", "fr": "Spéciales totales"},
    "dash.completed": {"en": "Completed", "fr": "Terminées"},
    "dash.completion": {"en": "Completion", "fr": "Complétion"},
    "dash.km_driven": {"en": "Km driven", "fr": "Km parcourus"},
    "dash.stages_driven": {"en": "Stages driven", "fr": "Spéciales roulées"},
    "dash.rallies_entered": {"en": "Rallies entered", "fr": "Rallyes disputés"},
    "dash.rallies_finished": {"en": "Rallies finished", "fr": "Rallyes terminés"},
    "dash.progress_over_time": {"en": "Progress over time", "fr": "Progression dans le temps"},
    "dash.activity": {"en": "Activity", "fr": "Activité"},
    "dash.activity_sub": {
        "en": "times set, last {n} weeks",
        "fr": "temps posés, {n} dernières semaines",
    },
    "dash.since_last": {"en": "Since your last visit", "fr": "Depuis ta dernière visite"},
    "dash.pbs": {"en": "Recent personal bests", "fr": "Records personnels récents"},
    "dash.time_on_table": {"en": "Time on the table", "fr": "Temps à gratter"},
    "dash.to_gain": {"en": "{s}s to gain", "fr": "{s}s à gagner"},
    "dash.strengths": {"en": "Your strengths", "fr": "Tes points forts"},
    "dash.strengths_surface": {"en": "By surface", "fr": "Par surface"},
    "dash.strengths_country": {"en": "By country", "fr": "Par pays"},
    "dash.suggested": {"en": "Suggested next stages", "fr": "Spéciales suggérées"},
    "dash.shortest": {"en": "Shortest to tackle", "fr": "Les plus courtes"},
    "dash.near": {"en": "Countries near completion", "fr": "Pays presque complétés"},
    "dash.by_surface": {"en": "Completion by surface", "fr": "Complétion par surface"},
    "dash.by_country": {"en": "Completion by country", "fr": "Complétion par pays"},
    # --- Toolbar / table ---
    "tb.search": {"en": "Search a stage…", "fr": "Chercher une spéciale…"},
    "tb.all_status": {"en": "All statuses", "fr": "Tous les statuts"},
    "tb.done": {"en": "Completed", "fr": "Terminées"},
    "tb.todo": {"en": "Not completed", "fr": "Non terminées"},
    "tb.all_surfaces": {"en": "All surfaces", "fr": "Toutes surfaces"},
    "tb.all_countries": {"en": "All countries", "fr": "Tous pays"},
    "tb.compare": {"en": "Compare", "fr": "Comparer"},
    "col.id": {"en": "ID", "fr": "ID"},
    "col.stage": {"en": "Stage", "fr": "Spéciale"},
    "col.country": {"en": "Country", "fr": "Pays"},
    "col.surface": {"en": "Surface", "fr": "Surface"},
    "col.length": {"en": "Length (km)", "fr": "Longueur (km)"},
    "col.status": {"en": "Status", "fr": "Statut"},
    "col.reference_time": {"en": "Reference time", "fr": "Temps de réf."},
    "col.rank": {"en": "Rank", "fr": "Rang"},
    "col.car": {"en": "Car", "fr": "Voiture"},
    "col.diff": {"en": "Diff 1st", "fr": "Écart 1er"},
    "col.uploaded": {"en": "Uploaded", "fr": "Envoyé le"},
    "pill.done": {"en": "Completed", "fr": "Terminée"},
    "pill.todo": {"en": "Not yet", "fr": "Pas encore"},
    "pill.unranked": {"en": "unranked", "fr": "non classé"},
    "empty.no_results": {
        "en": "No stage matches your filters.",
        "fr": "Aucune spéciale ne correspond.",
    },
    "foot.snapshot_from": {"en": "Snapshot from", "fr": "Instantané depuis"},
    # --- Tooltips (explanations) ---
    "tip.completion": {
        "en": "Share of the full stage catalog you have a time on.",
        "fr": "Part du catalogue de spéciales où tu as un temps.",
    },
    "tip.rank": {
        "en": "Your position among all drivers ranked on this stage (top-%).",
        "fr": "Ta position parmi tous les pilotes classés sur la spéciale (top-%).",
    },
    "tip.time_on_table": {
        "en": "Seconds you'd save by matching the fastest sector times of the field.",
        "fr": "Secondes gagnées en égalant les meilleurs temps par secteur du peloton.",
    },
    "tip.strengths": {
        "en": "Average share of the field you beat on ranked stages — higher is better.",
        "fr": "Part moyenne du peloton que tu bats sur les spéciales classées — plus haut = mieux.",
    },
    "strengths.beats": {"en": "beats", "fr": "bat"},
    "tip.activity": {
        "en": "Days on which you set your current times.",
        "fr": "Jours où tu as posé tes temps actuels.",
    },
    "tip.targets": {
        "en": "Stages where a followed rival is only slightly ahead of you.",
        "fr": "Spéciales où un rival suivi n'est que légèrement devant toi.",
    },
    "analysis.empty": {
        "en": (
            "Nothing to analyse yet — ranks load once your times are on the stage "
            "leaderboards (a ~ marks an estimated rank)."
        ),
        "fr": (
            "Rien à analyser pour l'instant — les rangs se remplissent dès que tes "
            "temps sont sur les classements (un ~ indique un rang estimé)."
        ),
    },
    "col.driver": {"en": "Driver", "fr": "Pilote"},
    "col.pos": {"en": "Pos", "fr": "Pos"},
    "col.finish_time": {"en": "Finish time", "fr": "Temps final"},
    # --- Stage detail ---
    "stage.by": {"en": "by", "fr": "par"},
    "stage.hotlaps": {"en": "hotlaps", "fr": "hotlaps"},
    "stage.open_on": {"en": "open on rallysimfans.hu", "fr": "ouvrir sur rallysimfans.hu"},
    "stage.sector_analysis": {"en": "Sector analysis", "fr": "Analyse par secteur"},
    "stage.sector": {"en": "Sector", "fr": "Secteur"},
    "stage.finish": {"en": "Finish", "fr": "Arrivée"},
    "stage.ideal": {"en": "Ideal lap", "fr": "Tour idéal"},
    "stage.best_combined": {"en": "best sectors combined", "fr": "meilleurs secteurs combinés"},
    "stage.your_sectors": {"en": "Your sectors", "fr": "Tes secteurs"},
    "stage.est_note": {
        "en": "estimated — not listed on the public board yet",
        "fr": "estimé — pas encore au classement public",
    },
    "stage.top_cars": {"en": "Top cars", "fr": "Voitures fréquentes"},
    "stage.search_driver": {
        "en": "Search a driver or car…",
        "fr": "Chercher un pilote ou une voiture…",
    },
    "stage.all_cars": {"en": "All cars", "fr": "Toutes voitures"},
    "stage.since": {"en": "Since", "fr": "Depuis"},
    "stage.me_only": {"en": "me only", "fr": "moi seulement"},
    "stage.you": {"en": "you", "fr": "toi"},
    "stage.no_match": {
        "en": "No hotlap matches your filters.",
        "fr": "Aucun hotlap ne correspond.",
    },
    # --- Compete (rivals / targets / compare) ---
    "compete.compare": {"en": "Compare", "fr": "Comparaison"},
    "compete.follow": {"en": "Follow a driver", "fr": "Suivre un pilote"},
    "compete.id_or_name": {"en": "username or user_id", "fr": "pseudo ou user_id"},
    "compete.label_opt": {"en": "label (optional)", "fr": "libellé (optionnel)"},
    "compete.follow_btn": {"en": "Follow driver", "fr": "Suivre"},
    "compete.lookup_hint": {
        "en": (
            "Username lookup covers drivers seen in leaderboards you've opened; "
            "otherwise use the numeric user_id."
        ),
        "fr": (
            "La recherche par pseudo couvre les pilotes vus dans les leaderboards "
            "ouverts ; sinon utilise le user_id numérique."
        ),
    },
    "compete.notfound": {
        "en": 'Couldn\'t find a driver named "{name}". Try the exact name or the numeric user_id.',
        "fr": "Aucun pilote nommé « {name} ». Essaie le nom exact ou le user_id numérique.",
    },
    "compete.driver_a": {"en": "driver A (default: me)", "fr": "pilote A (défaut : moi)"},
    "compete.driver_b": {"en": "driver B user_id", "fr": "user_id pilote B"},
    "compete.rivals_title": {"en": "Rivals — head to head", "fr": "Rivaux — face à face"},
    "compete.shared": {"en": "Shared", "fr": "Communes"},
    "compete.h2h": {"en": "Head-to-head", "fr": "Face à face"},
    "compete.details": {"en": "details", "fr": "détails"},
    "compete.remove": {"en": "Remove", "fr": "Retirer"},
    "compete.no_rivals": {
        "en": "No rivals yet. Follow a driver above to track your head-to-head.",
        "fr": "Aucun rival. Suis un pilote ci-dessus pour suivre ton face à face.",
    },
    "compete.targets_title": {"en": "Beatable targets", "fr": "Cibles atteignables"},
    "compete.rival": {"en": "Rival", "fr": "Rival"},
    "compete.your_time": {"en": "Your time", "fr": "Ton temps"},
    "compete.their_time": {"en": "Their time", "fr": "Son temps"},
    "compete.gap": {"en": "Gap", "fr": "Écart"},
    "compete.no_targets": {
        "en": "You're ahead of your rivals on every shared stage. 🏆",
        "fr": "Tu devances tes rivaux sur toutes les spéciales communes. 🏆",
    },
    "compete.faster_on": {"en": "faster on", "fr": "plus rapide sur"},
    "compete.shared_note": {
        "en": "{n} stage(s) where both drivers have a time.",
        "fr": "{n} spéciale(s) où les deux pilotes ont un temps.",
    },
    "compete.neg_delta": {"en": "Negative delta =", "fr": "Écart négatif ="},
    "compete.delta": {"en": "Delta", "fr": "Écart"},
    "compete.no_shared": {
        "en": "No stage where both drivers have a recorded time.",
        "fr": "Aucune spéciale où les deux pilotes ont un temps.",
    },
    "compete.championship": {"en": "Rivals championship", "fr": "Championnat des rivaux"},
    "compete.points": {"en": "Points", "fr": "Points"},
    "compete.wins": {"en": "Wins", "fr": "Victoires"},
    "compete.contested": {"en": "Contested", "fr": "Disputées"},
    "analysis.rank_movers": {"en": "Biggest rank movers", "fr": "Plus gros mouvements de rang"},
    # --- Status ---
    "status.title": {"en": "Status", "fr": "État"},
    "status.sub": {
        "en": "In-memory caches and rate-limit state.",
        "fr": "Caches en mémoire et état du rate-limit.",
    },
    "status.session": {"en": "Session", "fr": "Session"},
    "status.cooldown": {"en": "Rate-limit", "fr": "Rate-limit"},
    "status.leaderboards": {"en": "Leaderboards cached", "fr": "Leaderboards en cache"},
    "status.snapshots": {"en": "Boards cached", "fr": "Tableaux en cache"},
    "status.hint": {
        "en": "Caches reduce load on the RallySimFans servers; they refresh automatically.",
        "fr": (
            "Les caches réduisent la charge sur les serveurs RallySimFans ; "
            "ils se rafraîchissent automatiquement."
        ),
    },
    # --- Error page ---
    "error.title": {"en": "Could not fetch stats", "fr": "Impossible de récupérer les stats"},
    "error.check_env": {"en": "Check your credentials in", "fr": "Vérifie tes identifiants dans"},
}


def translate(key: str, lang: str) -> str:
    entry = _STRINGS.get(key)
    if entry is None:
        return key
    return entry.get(lang) or entry.get("en") or key
