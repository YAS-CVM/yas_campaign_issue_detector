# ROADMAP — CVM Operations Specialist (Yas Sénégal)

> Guide de référence pour un·e stagiaire **CVM Operations Specialist** : glossaire, concepts métier,
> processus opérationnels, KPI, et feuille de route du projet *Campaign Issue Detector*.
>
> Les éléments marqués *(à confirmer)* sont des interprétations à valider avec l'équipe.

---

## Sommaire

1. [Le métier : CVM & CVM Operations](#1-le-métier--cvm--cvm-operations)
2. [Fondamentaux télécom](#2-fondamentaux-télécom)
3. [Cycle de vie client & segmentation](#3-cycle-de-vie-client--segmentation)
4. [Campagnes : types, canaux, cycle de vie](#4-campagnes--types-canaux-cycle-de-vie)
5. [Mesure de la performance](#5-mesure-de-la-performance)
6. [Opérations au quotidien](#6-opérations-au-quotidien)
7. [Le Daily Dashboard Yas](#7-le-daily-dashboard-yas)
8. [Catalogue des anomalies](#8-catalogue-des-anomalies)
9. [Glossaire A–Z](#9-glossaire-az)
10. [Roadmap](#10-roadmap)
11. [Questions ouvertes](#11-questions-ouvertes)

---

## 1. Le métier : CVM & CVM Operations

### 1.1 Qu'est-ce que le CVM ?

Le **Customer Value Management** a pour but d'**augmenter la valeur de chaque client existant** plutôt que d'en acquérir de nouveaux.
Il s'appuie sur la donnée client (usage, recharge, cycle de vie) pour envoyer **la bonne offre, au bon client, au bon moment, par le bon canal**.

Les quatre leviers CVM :

| Levier | Objectif | Exemple Yas |
|---|---|---|
| **Acquisition / Activation** | Faire démarrer un nouveau client | Nursery, First Pack Activation, Free Internet first month |
| **Développement (Upsell / Cross-sell)** | Augmenter la dépense ou l'usage | Upsell Campaign, Bundle Drive, ADU Boost, offres Mixx |
| **Rétention** | Éviter qu'un client devienne inactif | Bundle Drive Retention, offres ciblées sur clients en baisse |
| **Réactivation (Win-back)** | Récupérer un client inactif | Offres pour clients inactifs depuis 30 / 60 / 90 jours |

### 1.2 Le rôle de CVM Operations

L'équipe **CVM Strategy / Analytics** conçoit les campagnes (quelle cible, quelle offre, quel objectif).
L'équipe **CVM Operations** les **exécute et les surveille** :

- configurer les campagnes, les broadcasts et les règles inbound dans la plateforme de campagne ;
- vérifier (QA) le ciblage, le message, l'offre et le groupe de contrôle ;
- lancer les envois, les planifier et respecter les fenêtres horaires ;
- **surveiller** chaque jour la livraison, les conversions et le provisionnement ;
- **détecter et remonter les incidents** (envoi bloqué, offre qui échoue, chute de livraison) ;
- produire les **reportings** (daily dashboard, bilans de campagne).

> **À retenir :** un bon CVM Ops repère un problème **avant** que le business ne le voie dans le chiffre d'affaires.

### 1.3 L'écosystème

```
 Data (DWH, CDR, recharges, usage)
        │
        ▼
 Segmentation / scoring (NBO, propension)
        │
        ▼
 Plateforme de campagne ──► Push (SMS, notifications app)       ──► Client
        │                  └► Inbound (USSD, YAS APP, call center) ◄── Client
        ▼
 Système de facturation / provisionnement (OCS / IN) ──► Fulfillment
        │
        ▼
 Reporting (Daily Dashboard, tableaux de bord de campagne)
```

---

## 2. Fondamentaux télécom

| Concept | Explication |
|---|---|
| **Prépayé / Postpayé** | Au Sénégal la base est très majoritairement **prépayée** : le client recharge du crédit (airtime) puis achète des forfaits. |
| **Recharge (top-up)** | Achat de crédit. Principal indicateur d'activité d'un client prépayé. |
| **Airtime** | Crédit principal de communication (FCFA). |
| **Bundle / forfait / pass** | Paquet data, voix, SMS ou mixte, avec une validité (24 h, 7 j, 30 j). Ex. Illimax (data), Tawfekh (voix). |
| **Validité** | Durée d'utilisation d'un forfait. |
| **Mobile Money (MFS)** | Portefeuille électronique (Mixx by Yas). Un forfait peut être payé en airtime ou via Mixx. |
| **USSD** | Menus `#…#` : canal inbound majeur, fonctionne sur tous les téléphones. |
| **SMSC** | Centre SMS : passerelle qui achemine les SMS. |
| **DLR (Delivery Report)** | Accusé de livraison renvoyé par le terminal. |
| **Sender ID / Short code** | Expéditeur affiché du SMS. |
| **CDR** | Call Detail Record : trace de chaque appel, SMS ou session data. |
| **IN / OCS** | Système de facturation temps réel qui débite le crédit et active les forfaits (**provisionnement**). |
| **MSISDN** | Numéro de téléphone du client. |
| **Dual SIM** | Beaucoup de clients ont plusieurs SIM, d'où un enjeu de *share of wallet*. |
| **Gross Adds** | Nouvelles activations de SIM sur une période. |
| **DND / Opt-out** | Clients ayant refusé les messages commerciaux : à exclure systématiquement. |
| **Régulateur** | **ARTP** (Autorité de Régulation des Télécommunications et des Postes) au Sénégal. |

---

## 3. Cycle de vie client & segmentation

### 3.1 Cycle de vie

```
 Nouveau (J0–J90) ──► Actif ──► En baisse (declining) ──► Inactif / dormant ──► Churné
      Nursery         Upsell       Rétention                 Réactivation          Win-back
```

| Stade | Définition typique *(seuils à confirmer)* | Action CVM |
|---|---|---|
| **Nouveau** | Activé il y a moins de 90 jours | Onboarding (Nursery), 1er forfait, inscription Mixx |
| **Actif** | Activité payante dans les 30 derniers jours | Upsell, cross-sell |
| **En baisse** | ARPU ou usage en baisse vs le mois précédent | Rétention préventive |
| **Inactif** | Aucune activité payante depuis 30 jours ou plus | Réactivation |
| **Churné** | Aucune activité depuis 90 jours ou plus | Win-back |

### 3.2 Axes de segmentation

| Axe | Exemples de segments |
|---|---|
| **Valeur** | ARPU (low / medium / high / VIP) |
| **Usage** | Data only, Voice only, Mixte ; Data User vs Non Data User (DU30 / NDU30) |
| **Intensité** | Light / Medium / Heavy (ex. `Voice_Plan_Data_Only_User_Heavy`) |
| **Comportement de recharge** | Fréquence, montant moyen, canal |
| **Géographie** | Région, site radio (campagnes Geoloc, SitesBoost) |
| **Terminal** | Smartphone vs feature phone (impact sur data et app) |
| **Ancienneté** | Tenure |
| **RFM** | Récence, Fréquence, Montant des recharges ou achats |

### 3.3 NBO — Next Best Offer

Un modèle choisit **l'offre la plus pertinente** pour chaque client (propension × valeur).
Dans le dashboard : programmes `NBO_Inbound_Program`, `NBO_Inbound_Program_Mandatory Offer`.
Une offre **mandatory** est affichée prioritairement, quel que soit le score.

---

## 4. Campagnes : types, canaux, cycle de vie

### 4.1 Push vs Inbound

| | **Push (sortant)** | **Inbound (entrant)** |
|---|---|---|
| Déclencheur | Yas envoie | Le client interagit (USSD, app) |
| Canaux | SMS, notifications app | Menus USSD, YAS APP, call center |
| Mesure | Sent → Delivered → Conversions | Impressions → Acceptation → Fulfillment |
| Risque type | Non-livraison, spam, fatigue | Offre mal configurée, provisionnement en échec |

### 4.2 Modes de déclenchement

| Mode | Description | Exemple |
|---|---|---|
| **One-off** | Envoi unique | `2GO_yasapp_20260903_OneOff_MessagingBC` |
| **Récurrent** | Même BC réexécuté chaque jour sur une cible recalculée | Voice_Plan_* |
| **Trigger / évènementiel** | Déclenché par une action client (recharge, activation, seuil de consommation) | TriggerTest_Activation |
| **Flow / parcours** | Suite d'étapes conditionnelles (J0, J3, J7…) | Flow_Nursery_Day0 |
| **Géolocalisé** | Ciblage par zone ou site radio | Geoloc_push_*, SitesBoost_* |

### 4.3 Catégories Yas

| Catégorie | Rôle | Conversion attendue ? |
|---|---|---|
| **Informative** | Information, service | Non (ou faible) |
| **Engagements** | Relation client | Non |
| **Nursery Campaign** | Onboarding des nouveaux clients | Oui |
| **Bundle Drive Campaign** | Promotion de forfaits (Acquisition / Retention / ADU Boost) | Oui |
| **DATAFRAMEWORK** | Stimulation data par segment | Oui |
| **CVM** | Valeur, rétention | Oui |
| **Voice Campaigns** | Forfaits voix | Oui |
| **Upsell Campaign** | Montée en gamme | Oui |

### 4.4 Cycle de vie d'une campagne

```
 Brief ─► Ciblage ─► Config. offre ─► Message ─► QA ─► Envoi test ─► Lancement ─► Monitoring ─► Bilan
```

| Étape | Points de contrôle |
|---|---|
| **Brief** | Objectif, KPI cible, budget ou coût de l'offre, période |
| **Ciblage** | Taille de la cible, exclusions (DND, UCG, clients déjà sollicités, staff), déduplication |
| **Configuration de l'offre** | Code produit, prix, validité, éligibilité, canal de paiement (airtime / Mixx) |
| **Message** | Longueur (160 caractères, 70 s'il y a des accents ou de l'unicode), orthographe, code USSD correct, langue (FR / wolof) |
| **Groupe de contrôle** | Taille (souvent 5–10 %), tirage aléatoire |
| **QA** | Test sur numéros internes, vérification du provisionnement réel |
| **Envoi test** | Envoi à des numéros internes témoins pour vérifier le rendu réel du message |
| **Lancement** | Respect des heures autorisées (blackout), étalement du débit (throttling) |
| **Monitoring** | Livraison à H+1, conversions à J+1, J+3, J+7, échecs de provisionnement |
| **Bilan** | Uplift, ROI, recommandations (on continue, on ajuste ou on arrête) |

### 4.5 Contraintes de contact

| Règle | But |
|---|---|
| **Blackout / quiet hours** | Pas d'envoi la nuit |
| **Pression commerciale (contact policy)** | Nombre maximum de messages par client et par jour ou semaine |
| **Priorisation / arbitrage** | Un client éligible à plusieurs campagnes n'en reçoit qu'une |
| **Opt-out / DND** | Respect des refus de sollicitation |
| **Fatigue** | Baisse des performances quand un client est trop sollicité |

---

## 5. Mesure de la performance

### 5.1 KPI business (niveau base clients)

| KPI | Formule / définition |
|---|---|
| **Revenue** | Chiffre d'affaires total |
| **ARPU** | Revenue ÷ nombre de clients actifs (sur la période) |
| **ARPPU** | Revenue ÷ nombre de clients **payants** |
| **Base active (A30, A90)** | Clients avec activité payante sur 30 / 90 jours |
| **Churn rate** | Clients perdus ÷ base de début de période |
| **Retention rate** | 1 − churn |
| **Data users / Data penetration** | Part des actifs qui consomment de la data |
| **MOU** | Minutes of Usage (voix) par client |
| **MB/user** | Consommation data moyenne |
| **Recharge frequency / amount** | Fréquence et montant moyen des recharges |
| **Bundle penetration** | Part des clients ayant acheté au moins un forfait |

### 5.2 KPI de campagne Push

| KPI | Formule |
|---|---|
| **Delivery %** | Delivered ÷ Sent |
| **Ack %** | Acknowledged ÷ Sent |
| **TG Conv %** | Conversions ÷ Sent (ou ÷ Delivered selon convention) |
| **CG Conv %** | CG Conversions ÷ CG |
| **Net Conv % (uplift)** | TG Conv % − CG Conv % |
| **Incremental conversions** | (TG Conv % − CG Conv %) × Sent |
| **Incremental revenue** | Revenue par client TG − Revenue par client CG, × taille du TG |
| **Fulfillment %** | Fulfillment Success ÷ (Success + Failure) |
| **ROI** | (Revenue incrémental − coût) ÷ coût. Coût = remises accordées + coût SMS |

### 5.3 KPI Inbound

| KPI | Formule |
|---|---|
| **Impressions** | Nombre d'affichages d'offre |
| **Take rate** | Acceptations (ou Fulfillment Success) ÷ Impressions |
| **Fulfillment Failure %** | Failures ÷ (Success + Failures) |

### 5.4 Groupe de contrôle, uplift, significativité

- La **conversion brute** ne prouve rien : une partie des clients aurait acheté de toute façon.
- Seul l'**uplift** (TG − CG) mesure l'effet réel de la campagne.
- **UCG (Universal Control Group)** : petit groupe exclu de *toutes* les campagnes pendant longtemps ; il mesure l'effet global du CVM.
- **Significativité** : un uplift calculé sur un CG trop petit n'est pas fiable. Ordre de grandeur : CG ≥ 1 000 clients et ≥ 30 conversions ; idéalement un test statistique (test de proportions, p < 0,05).
- **Uplift négatif** : campagne contre-productive (cannibalisation d'une offre plus chère, irritation) **ou** CG biaisé.

### 5.5 Fenêtre d'attribution & maturité

Une conversion est attribuée à une campagne si le client achète **dans les N jours** suivant l'envoi.
Conséquence : **les derniers jours paraissent toujours sous-performants**.

> Observé sur le dashboard : les conversions du 01/09 sont passées de 3 092 (fichier du 01/09) à 10 848 (fichier du 22/09), soit ×3,5.

→ Comparer les campagnes **à maturité égale** (ex. J+7).

### 5.6 A/B test

Tester deux variantes (message, prix, heure) sur des sous-groupes aléatoires de même taille, puis comparer leurs uplifts.
Ne changer **qu'une variable** à la fois.

---

## 6. Opérations au quotidien

### 6.1 Checklist quotidienne (matin)

- [ ] Le dashboard du jour est-il à jour ? (`Last Refresh Date Time`)
- [ ] Des broadcasts sont-ils `Aborted`, `Delivery Stalled`, ou encore `Delivering` depuis la veille ?
- [ ] Des broadcasts ont-ils `Sent > 0` et `Delivered = 0` ?
- [ ] Le Delivery % par catégorie est-il dans la norme habituelle ?
- [ ] Des règles IM ont-elles un taux d'échec de provisionnement anormal ?
- [ ] Les impressions USSD sont-elles en chute ?
- [ ] Des campagnes récurrentes sont-elles en pause depuis plusieurs jours ?
- [ ] Les volumes envoyés correspondent-ils au planning prévu ?

### 6.2 Triage d'un incident

```
 1. Constater    → quelle métrique, quel périmètre, depuis quand ?
 2. Localiser    → global / catégorie / campagne / broadcast / règle ?
 3. Qualifier    → sévérité (volume impacté, revenu à risque)
 4. Diagnostiquer→ où casse l'entonnoir ? (voir 6.3)
 5. Escalader    → IT plateforme, réseau / SMSC, billing / IN, équipe offre
 6. Suivre       → ticket, correction, vérification, clôture
 7. Documenter   → cause racine, action préventive
```

### 6.3 Diagnostic par l'entonnoir

```
 Generated ─► Sent ─► Acknowledged ─► Delivered ─► Conversions ─► Fulfillment
```

| Rupture | Causes probables | À qui s'adresser |
|---|---|---|
| Generated → Sent | Blackout, pause, abort, quota, flow bloqué | Plateforme de campagne |
| Sent → Acknowledged | Rejet SMSC, sender ID, surcharge | SMSC / réseau |
| Acknowledged → Delivered | Numéros inactifs, terminaux éteints, DLR non remontés | SMSC / réseau |
| Delivered → Conversions | Offre peu attractive, mauvaise cible, code USSD erroné | CVM Strategy / offre |
| Conversions → Fulfillment | Erreur de configuration produit, solde insuffisant, IN en panne | Billing / IN |

### 6.4 Sévérité

| Niveau | Critère indicatif |
|---|---|
| **Critique** | Blocage total, ≥ 100 k clients impactés, ou ≥ 90 % d'échec de provisionnement |
| **Majeur** | Forte dégradation par rapport à l'historique, volume moyen |
| **Mineur** | Incohérence de données, petit volume |
| **Info** | Anomalie structurelle connue |

### 6.5 Bonnes pratiques

- Toujours **tester avant d'envoyer** (envoi test + test de l'offre sur un numéro interne).
- Ne jamais lancer sans **groupe de contrôle** une campagne dont on veut mesurer l'effet.
- **Nommer** les campagnes et broadcasts de façon normalisée (`<Objectif>_<Offre>_<Segment>_<Date>`).
- Garder un **journal** des lancements et incidents.
- Juger une campagne à **maturité** et sur l'**uplift**, jamais sur la conversion brute d'un seul jour.
- Distinguer **problème de données** (reporting faux) et **problème réel** (clients impactés).

---

## 7. Le Daily Dashboard Yas

Fichier : `Yas_Senegal_Daily_Dashboard_till_<JJ>_<Mois>_<AAAA>.xlsb`.
Chaque version est **cumulative** depuis le 1er du mois, et les jours passés peuvent être révisés.

### 7.1 Feuilles

| Feuille | Visibilité | Contenu |
|---|---|---|
| `Data_Push` | **masquée** | Données brutes Push, 1 ligne = 1 broadcast |
| `Data_IM` | **masquée** | Données brutes Inbound, 1 ligne = 1 règle × 1 jour |
| `Sheet1` | **masquée** | Tableau croisé dynamique : `BC Name → Campaign Name` |
| `PM_Summary` / `IM_Summary` | visible | Totaux journaliers + graphiques |
| `Campwise` | visible | Campagne × jour |
| `BCWISE Summary` | visible | Broadcast × jour |
| `Unique campaign Summary` | visible | Totaux du mois par campagne (TG / CG / Net) |
| `IM_Channelwise_Summary` | visible | Canal IM × jour |

Les feuilles visibles sont **calculées par formules** à partir de `Data_Push` et `Data_IM`.

### 7.2 Colonnes clés — `Data_Push`

`Scheduled Date` (serial Excel), `Broadcast ID` (clé unique), `BC Name`, `Campaign Name`, `Campaign Category`, `Status`,
`Generated`, `Sent`, `Acknowledged`, `Delivered`, `Conversions`, `Unique Conversions`, `Conversion Value`,
`Fulfillment Success/Failure`, `Overall Ctrl Grp`, `Overall Ctrl Grp Conversions`, `Net Conversion %`, `Is Seeding`.

### 7.3 Colonnes clés — `Data_IM`

`Date`, `Touchpoint` (USSD / YAS APP), `Program`, `Program Rule` / `Rule ID`, `Product`, `Offer`, statuts,
`Impressions`, `Fulfillment Success`, `Fulfillment Failures`, `Last Refresh Date Time`.

### 7.4 Statuts de broadcast

| Statut | Signification | Suspect si… |
|---|---|---|
| `Completed` | Terminé | `Delivered = 0` alors que `Sent > 0` |
| `Delivering` | En cours | Daté de plus de 24 h |
| `Paused` | Pause manuelle | Se répète plusieurs jours |
| `Aborted` | Interrompu | Toujours |
| `Blackout Pause` / `Blackout Expired` | Stoppé par la fenêtre horaire | Grosse part de la cible non servie |
| `Delivery Stalled` | Livraison bloquée | Toujours |

### 7.5 Pièges

1. Environ 3 250 lignes physiques, mais seulement 1 500 à 1 660 remplies → supprimer les lignes vides.
2. `Scheduled Date` apparaît deux fois (serial + texte).
3. Les synthèses ont des colonnes jusqu'à la fin du mois remplies de 0 → ce n'est pas « 0 envoi ».
4. Dates au format serial Excel : origine `1899-12-30` (`46266` = 2026-09-01).
5. `%` exprimés sur 0–100 dans `Data_Push`, sur 0–1 dans les synthèses.
6. `Generated = 0` est normal pour certains broadcasts (Geoloc, trigger).
7. Informative / Engagements : 0 conversion est normal.
8. Conversion IM = `Fulfillment Success` (la colonne `Conversions` IM est quasi vide).
9. Exclure le **seeding** (offres gratuites) des KPI de conversion : leurs « conversions » sont des bonus crédités, pas des achats.
10. Conversions Push non matures sur les derniers jours (§5.5).

---

## 8. Catalogue des anomalies

Constatées sur le snapshot du 22/09/2026 (1 521 broadcasts, 1 660 lignes IM).

### 8.1 Push — Exécution

| ID | Anomalie | Règle | Observé |
|---|---|---|---|
| `PM-EXE-01` | Bloqué en `Delivering` | `Status = Delivering`, âge ≥ 1 j | Flow_Nursery Dummy BC : 4,4 M + 1 M ciblés par jour, Sent = 0 depuis le 05/09 |
| `PM-EXE-02` | Interrompu | `Status ∈ {Aborted, Delivery Stalled}` | 17 + 1 |
| `PM-EXE-03` | Pause récurrente | même `BC Name` en `Paused` ≥ 2 j | Touch_Point_Call_Center depuis le 16/09 |
| `PM-EXE-04` | Blackout | `Status` Blackout | 38 |
| `PM-EXE-05` | Ciblé non envoyé | `Generated > 0`, `Sent = 0` | 70 lignes avec Sent = 0 |

### 8.2 Push — Livraison

| ID | Anomalie | Règle | Observé |
|---|---|---|---|
| `PM-DLV-01` | Livraison nulle | `Sent > 0`, `Delivered = 0` | 153 |
| `PM-DLV-02` | Chute de Delivery % | Delivery % très en dessous de sa médiane récente | Informative 13–21 % du 17 au 21/09 (contre 55–80 %) |
| `PM-DLV-03` | Ack % faible | `Ack % < 90` | 311 |

### 8.3 Push — Performance

| ID | Anomalie | Règle | Observé |
|---|---|---|---|
| `PM-PRF-01` | 0 conversion sur gros volume | `Conv = 0`, `Sent > 1000`, catégorie à objectif, maturité ≥ J+3 | 518 (avant filtre) |
| `PM-PRF-02` | Uplift négatif | `Net Conv % < 0`, CG significatif | 104 |
| `PM-PRF-03` | Échec de provisionnement | `Fulfillment Failure` élevé | 27 |

### 8.4 Push — Qualité de données

| ID | Anomalie | Observé |
|---|---|---|
| `PM-DQ-01` | `Sent > Generated` | 692 (souvent `Generated = 0`) |
| `PM-DQ-02` | `Conversions > Sent` | ADU_Boost : 733 k conversions pour 390 k envois |
| `PM-DQ-03` | `Fulfillment % > 100` | 2 |
| `PM-DQ-04` | Pas de groupe de contrôle | 303 |
| `PM-DQ-05` | `Value(Total_Con_Val)` toujours vide | 100 % |

### 8.5 Inbound

| ID | Anomalie | Règle | Observé |
|---|---|---|---|
| `IM-FUL-01` | Règle en échec massif | Fail % ≥ 50 %, ≥ 500 tentatives | NBO_Pass_65Go (100 %), NBO_Illimax 8000F (99,8 %), NBO_100Mo-100F (98,6 %), Test_Illimax_4000F (80 %) |
| `IM-FUL-02` | Hausse du taux d'échec global | Fail % au-dessus de sa médiane récente | 28 % → 35–37 % (16–18/09) |
| `IM-IMP-01` | Impressions sans succès | Impressions > 1000, Success = 0 | 4 règles |
| `IM-IMP-02` | Chute d'impressions | Impressions très en dessous de leur médiane récente | à surveiller |
| `IM-DQ-01` | Réponses non tracées | `Conversions` / `Accepted` ≈ 0 | 14 au total |
| `IM-DQ-02` | Canal sans résultat | YAS APP : 40 k impressions, 0 fulfillment | — |
| `IM-DQ-03` | Donnée périmée | `Last Refresh` > 24 h | à surveiller |

### 8.6 Entre deux snapshots

| ID | Anomalie |
|---|---|
| `SNP-01` | Sent / Delivered / CG modifié pour un même `Broadcast ID` (ces chiffres devraient être figés) |
| `SNP-02` | `Broadcast ID` disparu |
| `SNP-03` | Données IM passées révisées |

---

## 9. Glossaire A–Z

| Terme | Définition |
|---|---|
| **A/B test** | Comparaison de deux variantes sur des groupes aléatoires |
| **A30 / A90** | Clients actifs sur 30 / 90 jours |
| **Acknowledged** | Message accepté par le SMSC |
| **ADU** | Active Data User *(à confirmer)* |
| **Airtime** | Crédit principal prépayé |
| **ARPU / ARPPU** | Revenu moyen par client / par client payant |
| **ARTP** | Régulateur télécom sénégalais |
| **ATL** | Above The Line : offre communiquée publiquement |
| **Attribution (fenêtre)** | Délai pendant lequel un achat est imputé à une campagne |
| **BC (Broadcast)** | Une exécution d'envoi Push |
| **Blackout** | Plage horaire interdite d'envoi |
| **Bundle / Pass** | Forfait data, voix, SMS ou mixte |
| **Cannibalisation** | Le client achète l'offre promue à la place d'une offre plus rentable |
| **CDR** | Call Detail Record |
| **CG (Control Group)** | Groupe non contacté, référence de mesure |
| **Churn** | Perte d'un client (inactivité prolongée) |
| **Contact policy** | Règles de pression commerciale |
| **Conversion** | Achat attribué à une campagne |
| **Cross-sell** | Vente d'un autre produit (ex. Mixx à un client data) |
| **CVM** | Customer Value Management |
| **Delivered / DLR** | Message reçu par le terminal / accusé de livraison |
| **DND** | Do Not Disturb : client exclu des sollicitations |
| **DU30 / NDU30** | Data User / Non Data User sur 30 jours *(à confirmer)* |
| **Dummy BC** | Broadcast technique qui déclenche un flow |
| **Flow** | Campagne à étapes multiples |
| **Fulfillment** | Provisionnement technique de l'offre |
| **Generated** | Audience calculée par le ciblage |
| **Gross Adds** | Nouvelles activations |
| **Impression** | Affichage d'une offre inbound |
| **IN / OCS** | Système de facturation temps réel |
| **Inbound (IM)** | Campagne déclenchée par l'interaction du client |
| **Maturité** | Âge d'un envoi, en jours, au moment où on le mesure |
| **MFS / Mixx** | Mobile Money Yas |
| **MOU** | Minutes of Usage |
| **MSISDN** | Numéro de téléphone |
| **Net Conversion % / Uplift** | TG Conv % − CG Conv % |
| **NBO** | Next Best Offer |
| **Nursery** | Onboarding des nouveaux clients |
| **One-off** | Envoi ponctuel |
| **Propension** | Probabilité qu'un client achète une offre donnée |
| **Push (PM)** | Campagne sortante |
| **RFM** | Récence, Fréquence, Montant |
| **ROI** | Retour sur investissement |
| **Seeding** (`Is Seeding = Yes`) | Offre **gratuite** (bonus data / minutes) donnée pour stimuler l'activité de certains clients. Les « conversions » sont des bonus crédités, pas des achats → à exclure des analyses de conversion |
| **Sent** | Message soumis à l'envoi |
| **SMSC** | Centre de messagerie SMS |
| **SOB** | Smart Offer Bundle |
| **Take rate** | Taux d'acceptation d'une offre inbound |
| **TG (Target Group)** | Clients ciblés et contactés |
| **Throttling** | Limitation du débit d'envoi |
| **Trigger** | Campagne déclenchée par un évènement client |
| **UCG** | Universal Control Group |
| **Upsell** | Montée en gamme |
| **USSD** | Menus `#…#` |
| **Win-back** | Reconquête d'un client churné |

---

## 10. Roadmap

### 10.1 Montée en compétence (stagiaire)

| Semaine | Objectif | Livrable |
|---|---|---|
| **S1** | Comprendre le métier et le vocabulaire | Lecture de ce document ; tour des équipes (Strategy, Ops, BI, IT, Offres) |
| **S2** | Maîtriser le Daily Dashboard | Savoir commenter chaque feuille ; refaire un KPI à la main |
| **S3** | Suivre des campagnes réelles | Assister à un cycle complet brief → bilan ; tenir la checklist quotidienne (§6.1) |
| **S4** | Diagnostiquer | Analyser un incident réel avec la méthode de l'entonnoir (§6.3) |
| **S5+** | Automatiser | Projet *Campaign Issue Detector* (§10.2) |

### 10.2 Projet *Campaign Issue Detector*

Implémenté dans `src/cvm_monitor/` : voir `README.md` pour l'installation et l'usage.

**Phase 0 — Cadrage** (terminé)
- [x] Exploration de deux snapshots (01/09 et 22/09)
- [x] Identification des feuilles masquées
- [x] Glossaire, concepts, catalogue d'anomalies

**Phase 1 — Ingestion** (terminé)
- [x] `ingest/loader.py` : lecture `.xlsb` → DataFrames `push` et `im` typés
- [x] Nettoyage (lignes vides, dates, snake_case, % → fraction), date du snapshot tirée du nom de fichier
- [x] Validation du schéma (`ingest/schema.py`, erreur explicite si le format change)
- [x] Historisation SQLite de tous les snapshots (`data/monitor.db`), ingestion idempotente (hash)

**Phase 2 — Règles fixes** (terminé)
- [x] Moteur de règles (`detect/engine.py`, décorateur `@rule`)
- [x] Règles `PM-EXE-*`, `PM-DLV-01/03`, `PM-PRF-*`, `PM-DQ-*`, `IM-FUL-01`, `IM-IMP-01`, `IM-DQ-*`
- [x] Seuils, sévérités et activation dans `config/config.yaml`
- [x] Regroupement par BC Name (une alerte par série d'envois), exclusion des BC techniques et du seeding

**Phase 3 — Comparaison à l'historique** (terminé)
- [x] Médiane glissante + MAD (`detect/baseline.py`)
- [x] Règles `PM-DLV-02`, `IM-FUL-02`, `IM-IMP-02`
- [x] Conversions évaluées seulement à maturité J+N

**Phase 4 — Comparaison de deux snapshots** (terminé)
- [x] Règles `SNP-*`
- [x] Courbe de maturation des conversions et estimation à maturité (`analytics/maturity.py`)

**Phase 5 — Restitution** (terminé)
- [x] CLI `cvm-monitor` : `run`, `watch`, `backfill`, `status`, `list`, `ack`, `report`, `preview`, `notify-test`, `dashboard`
- [x] Export CSV des anomalies, rapport Excel hebdo / mensuel (scorecards campagnes avec uplift significatif)
- [x] Tableau de bord Streamlit (8 pages) avec acquittement

**Phase 6 — Industrialisation** (en cours)
- [x] Tests unitaires et de bout en bout (`pytest`)
- [x] Exécution planifiée : `scripts/install_cron.sh` (Linux), `scripts/install_task.ps1` (Windows)
- [x] Alertes Teams (webhook Workflows) et e-mail (SMTP ou Outlook), anti-doublon et rappels
- [ ] Configurer le webhook Teams et le SMTP de l'entreprise (`config/.env`)
- [ ] Ajuster les seuils après 2–3 semaines d'usage réel
- [ ] Valider les règles avec l'équipe (voir questions ci-dessous)

**Pistes suivantes**
- [ ] Pression commerciale : nombre de messages par client (nécessite des données au niveau client)
- [ ] Récupération automatique du fichier (pièce jointe e-mail, dossier partagé)
- [ ] Hébergement du tableau de bord sur un serveur pour toute l'équipe

---

## 11. Questions ouvertes

À valider avec le tuteur et les équipes CVM :

- [ ] Fenêtre d'attribution officielle des conversions Push (3, 7, 15 jours ?)
- [ ] Définitions internes : actif, inactif, churn, ADU, DU30 / NDU30
- [ ] Taille standard du groupe de contrôle, existence d'un UCG
- [ ] Contact policy : nombre maximum de SMS par client et par jour ou semaine, horaires de blackout
- [ ] Les Dummy BC des flows Nursery sont-ils censés avoir `Sent = 0` ?
- [ ] Pourquoi `Conversions > Sent` sur DATAFRAMEWORK / ADU_Boost (achats multiples comptés ?)
- [ ] Chute de Delivery % Informative du 17 au 21/09 : incident connu ?
- [ ] Règles IM à ~100 % d'échec : erreurs de configuration de l'offre ?
- [ ] La colonne `Value(Total_Con_Val)` doit-elle être alimentée ?
- [ ] Circuit d'escalade des incidents et seuils de sévérité
- [ ] BC `NBO_Value Segment_*` et `ADU_BOOST Campaign_*_OneOff_MessagingBC` : 0 livré et ~0 % acquitté alors que Sent est élevé. S'agit-il de BC techniques (marquage de segment, sans SMS) à ajouter à `technical_bc_patterns` ?
- [ ] Taux d'acquittement SMSC très bas sur les grosses promos (Illimax 3000F : ~35 %) : limitation de débit (throttling) connue ?
