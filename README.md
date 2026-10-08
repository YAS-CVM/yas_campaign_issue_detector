# Yas CVM Monitor

Surveillance automatique des campagnes CVM Yas Sénégal à partir du fichier quotidien
`Yas_Senegal_Daily_Dashboard_till_<JJ>_<Mois>_<AAAA>.xlsb`.

Chaque nouveau fichier est **historisé** (SQLite), **analysé** (environ 25 règles de détection), et donne lieu à des **alertes**
(Teams, e-mail) et à un **tableau de bord** Streamlit. Le vocabulaire métier et le catalogue des règles sont décrits
dans [ROADMAP.md](ROADMAP.md).

```
 inbox/*.xlsb ─► ingestion ─► SQLite (historique) ─► règles ─► anomalies ─► Teams / e-mail
                                     │                               │
                                     └──────► tableau de bord ◄──────┘
```

---

## Installation

Prérequis : **Python 3.10 ou plus récent**. Aucun droit administrateur n'est nécessaire.

### Linux

```bash
cd yas_campaign_issue_detector
python3 -m venv .venv
.venv/bin/pip install -e ".[dashboard]"
cp config/.env.example config/.env      # puis renseigner Teams / SMTP (facultatif)
```

### Windows (PowerShell)

```powershell
cd yas_campaign_issue_detector
py -m venv .venv
.venv\Scripts\pip install -e ".[dashboard]"
copy config\.env.example config\.env    # puis renseigner Teams / SMTP (facultatif)
```

Sous Windows, si le port SMTP est bloqué, envoyez les e-mails via Outlook : installez `pip install -e ".[outlook]"`
puis mettez `backend: outlook` dans la section `notify.email` de `config/config.yaml`.

Dans la suite, `cvm-monitor` désigne `.venv/bin/cvm-monitor` (Linux) ou `.venv\Scripts\cvm-monitor` (Windows).

---

## Utilisation au quotidien

**Depuis le tableau de bord** : page **Importer**, glisser le ou les fichiers `.xlsb`, puis cliquer sur « Importer ».
Le traitement est le même que `cvm-monitor run` : historisation, détection, alertes (désactivables) et archivage.
Un fichier déjà importé est reconnu et ignoré.

**En ligne de commande** :

1. Déposer le fichier `.xlsb` du jour dans **`inbox/`**.
2. Lancer :
   ```bash
   cvm-monitor run
   ```
   Le fichier est chargé, analysé, puis déplacé dans `archive/`. Un CSV des anomalies est écrit dans `reports/`
   et les alertes sont envoyées. Un fichier déjà traité est ignoré (contrôle par empreinte).
3. Consulter :
   ```bash
   cvm-monitor dashboard          # http://localhost:8501
   ```

### Première utilisation : charger l'historique

```bash
cvm-monitor backfill Yas_Senegal_Daily_Dashboard_till_*.xlsb
```

Cette commande n'envoie pas d'alerte et ne déplace pas les fichiers. Plus il y a de fichiers historisés, plus la
comparaison à l'historique (médiane glissante) et la courbe de maturité des conversions sont fiables.

### Toutes les commandes

| Commande | Rôle |
|---|---|
| `cvm-monitor run [fichiers…] [--no-notify]` | Traite les fichiers de `inbox/` (ou ceux indiqués) |
| `cvm-monitor watch` | Surveille `inbox/` en continu et traite chaque fichier dès son dépôt |
| `cvm-monitor backfill <fichiers…>` | Historise d'anciens fichiers, sans alerte |
| `cvm-monitor status` | Snapshots ingérés et nombre d'anomalies par statut et sévérité |
| `cvm-monitor list [--severity major] [--status open] [--rule PM-EXE-01]` | Liste les anomalies |
| `cvm-monitor ack <id…> [--note "..."] [--by nom] [--mute] [--reopen]` | Acquitte, met en sourdine ou rouvre |
| `cvm-monitor report --period week\|month` | Rapport Excel : KPI, scorecards campagnes, règles IM, anomalies |
| `cvm-monitor preview` | Écrit l'e-mail récapitulatif en HTML, sans l'envoyer |
| `cvm-monitor notify-test` | Envoie un message de test sur Teams et par e-mail |
| `cvm-monitor dashboard [--port 8501]` | Lance le tableau de bord |

---

## Automatisation

Le fichier est déposé à la main ; l'outil peut ensuite tourner seul.

- **Linux (cron)** : `scripts/install_cron.sh` lance `run` toutes les heures de 9 h à 18 h, du lundi au samedi.
  Désinstaller : `scripts/install_cron.sh --remove`.
- **Windows (Planificateur de tâches)** :
  `powershell -ExecutionPolicy Bypass -File scripts\install_task.ps1`
  (même rythme ; `-Remove` pour désinstaller).
- **Alternative** : laisser `cvm-monitor watch` ouvert dans un terminal. Le fichier est traité dès qu'il est déposé.

Comme `run` ne traite que les nouveaux fichiers, le lancer plusieurs fois par jour ne crée aucun doublon.

---

## Alertes

| Canal | Contenu | Quand |
|---|---|---|
| **Teams** | Carte : nouvelles anomalies majeures et critiques (top 5), lien vers le tableau de bord | Seulement s'il y a du nouveau, ou un rappel |
| **E-mail** | Récapitulatif : KPI du jour, nouvelles anomalies, anomalies toujours ouvertes, résolues ; CSV en pièce jointe | À chaque nouveau fichier |
| **Tableau de bord** | Tout, avec filtres et acquittement | Toujours |

**Pas de doublon :**
- une anomalie déjà signalée n'est pas renvoyée ;
- elle revient en rappel sur Teams après `realert_after_days` jours si elle est toujours ouverte ;
- elle est renvoyée immédiatement si sa sévérité augmente.

**Une anomalie acquittée** ne génère plus de rappel, sauf si elle s'aggrave. **Une anomalie en sourdine** ne génère plus jamais d'alerte.

### Configurer Teams

1. Dans le canal Teams, ouvrir **… > Workflows**.
2. Choisir le modèle **« Publier dans un canal lorsqu'une requête webhook est reçue »**.
3. Copier l'URL générée dans `TEAMS_WEBHOOK_URL` (`config/.env`).
4. Vérifier avec `cvm-monitor notify-test`.

Les anciens connecteurs « Incoming Webhook » d'Office 365 sont retirés par Microsoft : il faut utiliser Workflows.

### Configurer l'e-mail

Renseigner `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM` et `MAIL_TO` dans `config/.env`.
`MAIL_TO` accepte plusieurs adresses séparées par des virgules.

---

## Règles de détection

Les règles sont définies dans `src/cvm_monitor/detect/`. Leurs seuils, sévérités et leur activation se règlent
dans `config/config.yaml`, sans toucher au code.

| Famille | Règles | Exemples |
|---|---|---|
| Push : exécution | `PM-EXE-01` à `05` | Broadcast bloqué en Delivering, Aborted, en pause, blackout, ciblé mais non envoyé |
| Push : livraison | `PM-DLV-01` à `03` | 0 livré, chute du taux de livraison vs l'historique, acquittement SMSC faible |
| Push : performance | `PM-PRF-01` à `03` | 0 conversion, uplift négatif **significatif**, échecs de provisionnement |
| Push : qualité | `PM-DQ-01` à `06` | Envoyés > ciblés, conversions > envoyés, pas de groupe de contrôle, colonne vide, jour manquant |
| Inbound | `IM-FUL-*`, `IM-IMP-*`, `IM-DQ-*` | Règle IM en échec, hausse du taux d'échec, offre affichée sans activation, données non rafraîchies |
| Snapshots | `SNP-01` à `03` | Volumes révisés, broadcast disparu, données IM passées modifiées |

Principes :
- **Maturité** : les conversions Push ne sont jugées qu'après `maturity_days` jours, car elles continuent d'arriver après l'envoi.
- **Seeding** : les offres gratuites (`Is Seeding = Yes`) sont exclues des règles de conversion.
- **BC techniques** : les « Dummy BC » qui démarrent un flow sont exclus des règles de livraison. Ils restent surveillés par `PM-EXE-01`.
- **Catégories sans objectif de conversion** (Informative, Engagements) : exclues des règles de performance.
- **Sévérité ajustée au volume** : elle monte d'un cran au-delà de `critical_volume` et descend à « mineure » sous `low_volume`.

### Ajouter une règle

```python
# src/cvm_monitor/detect/rules_push.py
@rule("PM-XXX-01", "Ma nouvelle règle", "push", "major", min_sent=1000)
def ma_regle(ctx, p):
    df = ctx.push[ctx.push["sent"] >= p["min_sent"]]
    for r in df.itertuples():
        if ...:
            yield Anomaly(entity_type="broadcast", entity_key=str(r.broadcast_id), date=r.date,
                          message="…", volume=r.sent)
```

Ajoutez ensuite `PM-XXX-01: {enabled: true, severity: major, min_sent: 1000}` dans `config.yaml`, puis un test dans `tests/`.

---

## Tableau de bord

| Page | Contenu |
|---|---|
| Vue d'ensemble | KPI du jour vs moyenne sur 7 jours, anomalies ouvertes, tendances Push et IM |
| Importer | Dépôt de fichiers `.xlsb` depuis le navigateur, résultat de la détection |
| Anomalies | Filtres, détail, **acquitter / mettre en sourdine / rouvrir** avec note, export CSV |
| Push | Entonnoir, statuts, carte de chaleur du taux de livraison par catégorie × jour, performance par catégorie |
| Inbound | Impressions, taux d'échec, règles avec le plus d'échecs |
| Campagnes | Uplift vs groupe de contrôle avec intervalle de confiance et p-value, verdict, fiche détaillée |
| Maturité | Courbe d'arrivée des conversions, estimation des conversions à maturité |
| Snapshots | Fichiers ingérés, écarts entre deux versions |
| Qualité des données | Contrôles de cohérence du dernier fichier |

---

## Structure

```
config/            config.yaml (seuils, canaux) · .env (secrets, non versionné)
inbox/  archive/   dépôt des fichiers · fichiers traités
data/monitor.db    historique SQLite (snapshots, faits Push/IM, anomalies, notifications)
reports/           CSV, rapports Excel, aperçus d'e-mail
scripts/           installation cron / Planificateur de tâches
src/cvm_monitor/
  ingest/          lecture et validation du .xlsb
  storage/         SQLite, cycle de vie des anomalies
  detect/          moteur, règles Push / IM / snapshots, historique (médiane + MAD)
  analytics/       KPI, uplift et significativité, maturité des conversions
  notify/          Teams, e-mail, choix de ce qui est envoyé
  dashboard/       application Streamlit
tests/             pytest (règles, cycle de vie, alertes, bout en bout sur les vrais fichiers)
```

## Tests

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

Les tests de bout en bout utilisent les fichiers `.xlsb` présents à la racine du projet. Ils sont ignorés si ces fichiers sont absents.

## Dépannage

| Problème | Solution |
|---|---|
| `Feuille 'Data_Push' : colonnes obligatoires absentes` | Le format du Daily Dashboard a changé : adapter `ingest/schema.py` |
| `déjà ingéré` | Normal : le même fichier a déjà été traité. Pour retraiter, supprimer `data/monitor.db` puis relancer `backfill` |
| Teams : `ERREUR 4xx` | URL du webhook invalide ou flux Workflows désactivé |
| E-mail bloqué au bureau | Passer au backend `outlook` (Windows) |
| Trop d'alertes | Relever les seuils ou désactiver une règle dans `config.yaml` ; ajouter des motifs à `technical_bc_patterns` |
