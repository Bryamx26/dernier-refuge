// Grille de collision en tuiles : construite depuis le calque `collision` d'une carte Tiled (.tmj)
// ou depuis des lignes de texte (fixtures : '#' solide, '.' libre). Aucune dépendance à Phaser.

/** Sous-ensemble du format JSON Tiled utilisé ici. */
export interface TiledLayerLike {
  readonly name: string;
  readonly type: string;
  readonly width?: number;
  readonly height?: number;
  readonly data?: readonly number[] | string;
  readonly layers?: readonly TiledLayerLike[];
}

export interface TiledMapLike {
  readonly width: number;
  readonly height: number;
  readonly layers: readonly TiledLayerLike[];
}

export const COLLISION_LAYER_NAME = 'collision';

export class CollisionGrid {
  readonly width: number;
  readonly height: number;
  private readonly solid: Uint8Array;

  constructor(width: number, height: number, solid?: Uint8Array) {
    if (!Number.isInteger(width) || !Number.isInteger(height) || width < 0 || height < 0) {
      throw new Error(`Dimensions de grille invalides : ${width} × ${height}`);
    }
    this.width = width;
    this.height = height;
    this.solid = solid ?? new Uint8Array(width * height);
    if (this.solid.length !== width * height) throw new Error('Taille du tableau de collision incohérente');
  }

  /** Grille des fixtures : une chaîne par ligne, '#' = solide, tout autre caractère = libre. */
  static fromRows(rows: readonly string[]): CollisionGrid {
    const height = rows.length;
    const width = height > 0 ? rows[0]!.length : 0;
    const solid = new Uint8Array(width * height);
    rows.forEach((row, ty) => {
      if (row.length !== width) throw new Error(`Ligne ${ty} de longueur ${row.length}, attendu ${width}`);
      for (let tx = 0; tx < width; tx += 1) solid[ty * width + tx] = row[tx] === '#' ? 1 : 0;
    });
    return new CollisionGrid(width, height, solid);
  }

  /** Grille d'une carte Tiled : toute tuile non nulle du calque `collision` est solide. */
  static fromTiledMap(map: TiledMapLike, layerName = COLLISION_LAYER_NAME): CollisionGrid {
    const layer = findTileLayer(map.layers, layerName);
    if (!layer) throw new Error(`Calque de tuiles « ${layerName} » absent de la carte`);
    if (!Array.isArray(layer.data))
      throw new Error(`Calque « ${layerName} » : données non compressées attendues`);
    const data = layer.data as readonly number[];
    const { width, height } = map;
    if (data.length !== width * height) {
      throw new Error(`Calque « ${layerName} » : ${data.length} tuiles pour une carte ${width} × ${height}`);
    }
    const solid = new Uint8Array(width * height);
    for (let i = 0; i < data.length; i += 1) solid[i] = data[i] !== 0 ? 1 : 0;
    return new CollisionGrid(width, height, solid);
  }

  /** Une tuile hors carte est solide. */
  isSolid(tx: number, ty: number): boolean {
    if (tx < 0 || ty < 0 || tx >= this.width || ty >= this.height) return true;
    return this.solid[ty * this.width + tx] === 1;
  }

  /** Vrai si une tuile du rectangle inclusif [tx0, tx1] × [ty0, ty1] est solide. */
  anySolid(tx0: number, tx1: number, ty0: number, ty1: number): boolean {
    for (let ty = ty0; ty <= ty1; ty += 1) {
      for (let tx = tx0; tx <= tx1; tx += 1) {
        if (this.isSolid(tx, ty)) return true;
      }
    }
    return false;
  }
}

function findTileLayer(layers: readonly TiledLayerLike[], name: string): TiledLayerLike | null {
  for (const layer of layers) {
    if (layer.type === 'tilelayer' && layer.name === name) return layer;
    if (layer.type === 'group' && layer.layers) {
      const found = findTileLayer(layer.layers, name);
      if (found) return found;
    }
  }
  return null;
}
