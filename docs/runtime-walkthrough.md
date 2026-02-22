# topo2ifc 実行フロー（ステップバイステップ）

このドキュメントでは、`topo2ifc` コマンドを実行したときに、内部でどのような順番で処理が進むかをコードベースに沿って説明します。

対象コマンド例:

```bash
topo2ifc --input tests/fixtures/sbco_minimal.ttl --output out.ifc --solver heuristic --seed 42
```

## 0. CLI 引数の受け取り

エントリポイント `topo2ifc/cli.py` の `main()` が、`--input` / `--output` / `--config` / `--solver` / `--seed` / `--debug` / `--verbose` を受け取ります。

- `--verbose` 指定時はログレベルを `DEBUG` に変更。
- `--debug` 指定時はデバッグ出力ディレクトリを作成。

## 1. 設定の構築

`--config` があれば YAML から `Config` を読み込み、なければ `Config.default()` を使用します。
その後 CLI 引数の `solver` と `seed` を設定値へ反映します。

## 2. RDF のロード

`RDFLoader` が入力 RDF を読み込んで `rdflib.Graph` を構築します。

1. 拡張子から RDF フォーマットを自動判定（`.ttl`→`turtle`, `.jsonld`→`json-ld` など）。
2. `Graph.parse()` でトリプルを読み込み。

## 3. 空間・関係の抽出

同じ `RDFLoader` で以下を抽出します。

- `extract_spaces()` で `SpaceSpec` 一覧
- `extract_adjacencies()` で隣接エッジ
- `extract_connections()` で接続エッジ

`extract_spaces()` では、先に `extract_storeys()` を呼び出して階（Storey/Level）を収集し、
`space -> storey` 対応を作って `storey_id` / `storey_elevation` を `SpaceSpec` に付与します。

## 4. トポロジグラフ化とトポロジ検証

抽出したデータから `TopologyGraph.from_parts(...)` で内部グラフを構築し、
`validate_topology()` を実行します。

- エラーが1件でもあればログ出力後に `SystemExit(1)` で終了。
- ここで止まるとレイアウト以降は実行されません。


## 5. レイアウトソルバ詳細

`topo2ifc` は共通インターフェース `solve(topo) -> list[LayoutRect]` を満たす 2 種類のソルバを切り替えて使います。

### 5.1 HeuristicSolver（既定値）

`topo2ifc/layout/solver_heuristic.py` の軽量ソルバです。

- **特徴**: 依存追加なしで高速に実行可能。
- **手順**:
  1. BFS 順（廊下/入口優先）で空間を並べる。
  2. 面積ターゲットから初期矩形サイズを計算。
  3. ストリップパッキングで順次配置。
  4. ヒルクライムで矩形位置を入れ替え、隣接満足度を改善。
- **向いている用途**: 初期案作成、軽量実行、OR-Tools 未導入環境。

### 5.2 OrtoolsSolver（CP-SAT）

`topo2ifc/layout/solver_ortools.py` の制約最適化ソルバです。

- **特徴**: OR-Tools の CP-SAT で矩形配置問題を整数最適化。
- **制約**:
  - 矩形どうしの non-overlap
  - 面積下限制約（`w*h`）
  - 目標面積との差分最小化
- **設定項目**: `solver_time_limit_sec`, `grid_unit`, `seed`。
- **注意点**: `ortools` が未インストールの場合は利用できません。
- **向いている用途**: 制約条件をより厳密に満たしたいケース。

### 5.3 使い分け目安

- **まず heuristic**: 速度重視・依存最小で結果確認。
- **必要に応じて ortools**: 品質や制約厳密性を上げたい場合。

## 6. レイアウト実行と後処理

CLI の `--solver` 値に応じて `HeuristicSolver` または `OrtoolsSolver` を実行し、
`solve(topo)` の結果（矩形群）を `snap_to_grid(..., grid=0.05)` でグリッド整列します。

## 7. レイアウト検証とレポート生成

レイアウト結果に対して:

- `validate_layout(rects, spaces)`
- `compute_area_deviations(rects, spaces)`
- `build_constraints_report(...)`

を行い、必要なら警告をログに出します。
`--debug` 指定時は `layout.json` / `layout.geojson` / `constraints_report.json` を保存します。

## 8. 幾何生成（壁・床・ドア）

レイアウト矩形をポリゴン化し、以下を生成します。

- `extract_walls(...)`
- `extract_slabs(...)`
- `extract_doors(...)`

ドア生成では `TopologyGraph.connected_pairs()` の接続ペアを利用します。

## 9. IFC エクスポート

`IfcExporter(cfg).export(...)` を呼び、空間・レイアウト・部材情報を IFC4 として出力します。
最後に `Done. IFC written to ...` をログ表示して終了します。

---

## 10. HVAC連携観点でのIFCプロパティ現状

現在の実装では、`Pset_SpaceCommon` は `IfcSpace` に付与されていますが、
`IfcWall` / `IfcSlab` / `IfcDoor` に対する材質・熱特性などのプロパティは付与されていません。

HVACシミュレータ連携で必要になることが多い情報（例: 材質名、熱伝導率、比熱、密度、U値）については、
今後の実装計画として `PLANS.md` の **Phase 5 – IFC property enrichment for HVAC integration** に追加済みです。

## まとめ（処理順）

1. CLI 引数受け取り
2. 設定構築
3. RDF ロード
4. 空間/関係抽出
5. トポロジ検証
6. ソルバ実行＋後処理
7. レイアウト検証/レポート
8. 幾何生成
9. IFC 出力
10. （現状整理）HVAC連携向けプロパティ確認

この順序を押さえると、トラブルシュート時に「どのフェーズで失敗したか」を切り分けしやすくなります。
