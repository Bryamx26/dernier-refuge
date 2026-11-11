# Valcendre — fiche de zone (World Designer)

Village rural abandonné, zone de départ de *Dernier Refuge*. Carte `maps/valcendre.tmj`, générée par
`tools/mapgen/generate_valcendre.py` (graine fixe). Aperçu : `carte-valcendre.png` (dossier projet
`phase-2/`), ou `python3 -I tools/mapgen/render_preview.py maps/valcendre.tmj apercu.png`.

Ambiance : fin d'automne après l'effondrement. Herbe sèche, forêt sombre au nord-ouest, voitures
abandonnées en travers des routes, vitres brisées, herbe qui perce l'asphalte, barricades militaires
aux deux sorties de route. Tout reste lisible : routes et trottoirs dégagés, façades bien découpées.

## Plan (coordonnées en tuiles, x → est, y → sud ; carte 128 × 128)

```
  0         30        55   70 74       105       127
0 ┌──────────────────────────────────────────────┐  haie d'arbres (bordure solide, 2 cases)
  │ FORÊT DE CENDRE   ╲      clairière/          │
  │  (dense)  sentier  ╲     campement (62-80,16-24)
  │                     ╲          │piste        │
36│                      ╲  B1  place │ B4        │
  │                       ╲ Mairie ▒▒ │ B2  B3    │
62│        ═════════════════GRAND-RUE═══╬═══════════════▶ sortie EST (barricade x=126)
  │                         B5  B6    │ B7  B8   champs
80│              piste ╱    ══RUE BASSE═╬══════ piste → champs en friche (SE)
  │                   ╱     B9        │ B10      │
94│   CASSE (14-34,  ╱                │          │
  │   94-114)                         │          │
127└──────────────────────────────────▼───────────┘
                                 sortie SUD (barricade y=126)
```

| Élément | Emprise | Notes |
| --- | --- | --- |
| Grand-rue (est-ouest) | y 62-65, x 30 → 127 | 4 voies, double ligne jaune ; sort à l'est. À l'ouest de x 30 : sentier de terre vers la forêt |
| Route du sud | x 70-73, y 36 → 127 | sort au sud ; au nord de y 36, piste vers la clairière |
| Rue basse | y 80-83, x 44-100 | interne ; à l'est, piste vers les champs ; à l'ouest, piste vers la casse |
| Trottoirs | 2 cases de chaque côté, dans x 42-104 / y 36-98 | passages piétons autour des deux carrefours |
| Place des Cendres | x 55-67, y 46-59 | dallage abîmé, 4 arbres en bac ; **9 points d'apparition** (58/61/64 × 50/53/56) |
| Forêt de Cendre | quart nord-ouest (≈ x < 55, y < 52, bord bruité) | troncs solides, cimes dans `above`, buissons ; sentier de terre jusqu'au bord nord |
| Clairière du campement | x 62-80, y 16-24 | caisses, fûts, pneus, une épave |
| Casse | x 14-34, y 94-114 | gravier, 7 épaves, pneus et fûts |
| Champs en friche | x 108-122, y 72-115 | parcelles de terre, rangs de buissons morts |
| Bordure | 2 cases solides sur tout le pourtour | haie d'arbres et buissons ; barricades sur les deux routes |

### Bâtiments (fermés en phase 2 : tout le rectangle est solide)

Rendu « trois quarts » : toit plat dans `above` (le joueur passe derrière), façade sud de 2 rangées
(fenêtres, porte) dans `ground`/`decor`. La porte est décorative en phase 2 ; sa case est notée dans le
calque `buildings` (`door_x`, `door_y`) et la case devant est toujours libre et accessible.

| # | Nom | Rectangle (x, y, l, h) | Porte | Intention phase 3+ |
| --- | --- | --- | --- | --- |
| B1 | Mairie | 44, 47, 10, 13 | 50, 59 | archives, cartes de la région (quêtes), loot faible |
| B2 | Épicerie | 77, 49, 9, 11 | 82, 59 | **nourriture**, eau ; zombies au fond de la réserve |
| B3 | Pharmacie | 89, 51, 11, 9 | 93, 59 | **médicaments**, bandages ; loot rare, très disputé |
| B4 | Maison du notaire | 78, 37, 8, 9 | 82, 45 | maison bourgeoise : objets de valeur, coffre |
| B5 | Gendarmerie | 45, 68, 10, 10 | 49, 77 | **armes et munitions** (loot rare), zone dangereuse (zombies en uniforme) |
| B6 | Boulangerie | 57, 68, 9, 10 | 60, 77 | nourriture de base, four (artisanat plus tard) |
| B7 | Garage Bastide | 77, 68, 11, 10 | 81, 77 | **outils**, pièces, carburant ; futur atelier de véhicules |
| B8 | Maisons jumelles | 91, 68, 9, 10 | 96, 77 | habitations : vêtements, sacs, loot commun |
| B9 | Coopérative agricole | 47, 87, 13, 10 | 52, 96 | matériaux (bois, sacs, outils agricoles), grand volume |
| B10 | École | 78, 88, 12, 9 | 85, 96 | abri potentiel (refuge de joueurs), fournitures |

## Intentions de gameplay (phases 3+)

- **Départ sûr** : la place des Cendres est le point d'apparition, sans zombie au départ, bien éclairée,
  avec vue sur les deux carrefours.
- **Gradient de danger** : centre (place, mairie) calme → rue basse et gendarmerie plus risquées →
  forêt, casse et champs : rencontres fréquentes, hordes errantes.
- **Points de loot** (à poser dans un futur calque d'objets `loot`, type `loot_point`, table dans
  `content/loot/`) : intérieurs des 10 bâtiments ; coffres et boîtes à gants des voitures abandonnées
  (≈ 30 épaves) ; casse (pièces, pneus, carburant) ; campement de la clairière (sac de randonneur,
  hache) ; quelques poubelles de trottoir (loot pauvre).
- **Zones dangereuses** : forêt de Cendre (visibilité réduite sous les cimes, zombies qui sortent des
  arbres) ; casse (labyrinthe d'épaves, embuscades) ; barricades est et sud (anciens points de contrôle
  militaires : nids de zombies, mais loot militaire) ; gendarmerie.
- **Sorties de zone** : les deux routes barricadées (est, sud) sont les transitions naturelles vers
  d'autres zones dans une phase ultérieure.
- **Lecture de l'espace** : les routes guident vers les points d'intérêt ; les voitures en travers créent
  des abris et des goulets sans bloquer la circulation (au moins 2 voies libres partout).

## Limites connues (prototype)

- Tuiles Kenney génériques : pas de façades est/ouest/nord ni d'intérieurs ; les toits plats cachent
  tout. Les intérieurs arriveront avec les portes (phase 3), probablement en cartes séparées.
- Palette encore assez claire malgré l'étalonnage : prévoir côté client un éclairage (teinte globale
  froide ou multiplication ~0,85, vignettage, cycle jour/nuit) plutôt que d'assombrir davantage les PNG.
- Pas d'eau ni de clôtures cohérentes dans les packs retenus.
