# IfcGenerator
RDFのトポロジからIFCデータを生成する

## topo2ifc

**RDF topology → Layout solver → Parametric geometry → IFC** パイプライン実装。

### 要件

- Python 3.10 以上
- 依存ライブラリ: `rdflib`, `networkx`, `shapely`, `numpy`, `ifcopenshell`, `click`, `pyyaml`
- オプション: `ortools`（CP-SATソルバ使用時）

### インストール

```bash
pip install -e .
# OR-Toolsソルバも使う場合
pip install -e ".[ortools]"
```

### 使い方

```bash
topo2ifc --input topology.ttl --output out.ifc
topo2ifc --input topology.ttl --output out.ifc --solver ortools --seed 42
topo2ifc --input topology.ttl --output out.ifc --debug /tmp/debug/
```

### オプション

| オプション | 説明 | デフォルト |
|---|---|---|
| `--input` | 入力 RDF ファイル（Turtle/JSON-LD） | 必須 |
| `--output` | 出力 IFC ファイルパス | `out.ifc` |
| `--config` | YAML 設定ファイル | なし |
| `--solver` | レイアウトソルバ（`heuristic` \| `ortools`） | `heuristic` |
| `--seed` | 乱数シード（再現性） | `42` |
| `--debug` | デバッグ出力ディレクトリ（`layout.json`, `.geojson`, レポート） | なし |

### パッケージ構成

```
topo2ifc/
  cli.py            # CLI エントリポイント
  config.py         # 設定クラス
  rdf/              # RDF 読み込み・語彙マッピング
  topology/         # SpaceSpec・グラフ内部表現
  layout/           # レイアウトソルバ（ヒューリスティック / OR-Tools）
  geometry/         # 2D→3D 形状生成（壁・床・ドア）
  ifc/              # IFC4 エクスポート（ifcopenshell）
  validate/         # バリデーション・レポート
```

### テスト

```bash
pip install pytest
pytest tests/
```
