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

### 対応 RDF 語彙

入力 Turtle ファイルは以下の語彙を混在して使用できます。

| 語彙 | 名前空間 | 対応クラス例 |
|---|---|---|
| **BOT** (Building Topology Ontology) | `https://w3id.org/bot#` | `bot:Storey`, `bot:Space` |
| **Brick** | `https://brickschema.org/schema/Brick#` | `brick:Floor`, `brick:Room` |
| **SBCO** (Smart Building Co-creation Organization) | `https://www.sbco.or.jp/ont/` | `sbco:Level`, `sbco:Space` |
| **topo2ifc 独自** | `https://topo2ifc.example.org/ont#` | `topo:Storey`, `topo:Space` |

SBCO オントロジーの詳細は [smartbuiding_ontology](https://github.com/takashikasuya/smartbuiding_ontology) を参照してください。

#### SBCO 語彙の入力例

```turtle
@prefix sbco: <https://www.sbco.or.jp/ont/> .
@prefix topo: <https://topo2ifc.example.org/ont#> .
@prefix bot:  <https://w3id.org/bot#> .
@prefix ex:   <https://example.com/> .

ex:level_3f a sbco:Level ;
    sbco:name "3F" ;
    sbco:hasPart ex:space_office, ex:space_meeting .

ex:space_office a sbco:Space ;
    sbco:name "Office Area" ;
    sbco:isPartOf ex:level_3f ;
    topo:areaTarget "30.0"^^<http://www.w3.org/2001/XMLSchema#float> .

ex:space_meeting a sbco:Space ;
    sbco:name "Meeting Room" ;
    sbco:isPartOf ex:level_3f ;
    topo:areaTarget "20.0"^^<http://www.w3.org/2001/XMLSchema#float> .

# 隣接関係は BOT 述語で表現（SBCO は包含のみ）
ex:space_office bot:adjacentElement ex:space_meeting .
```

最小 SBCO サンプルは `tests/fixtures/sbco_minimal.ttl` にあります。
複数階（multi-storey）の例は `tests/fixtures/two_storey.ttl` にあります。

### パッケージ構成

```
topo2ifc/
  cli.py            # CLI エントリポイント
  config.py         # 設定クラス
  rdf/              # RDF 読み込み・語彙マッピング
  topology/         # SpaceSpec・StoreySpec・グラフ内部表現
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

### ドキュメント

- 実行フローの詳細: [docs/runtime-walkthrough.md](docs/runtime-walkthrough.md)
