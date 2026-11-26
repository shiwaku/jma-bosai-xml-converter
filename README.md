# jma-bosai-xml-converter

[気象庁防災情報XML](https://xml.kishou.go.jp/)を、GIS・WebGISでそのまま使える形式（GeoParquet、GeoJSON、PMTiles）に変換するツールです。

防災情報XMLは場所を地域コードで書くことが多く、地図上の形（ジオメトリ）を持っていません。このツールは、電文のコードを気象庁の[予報区等GISデータ](https://www.data.jma.go.jp/developer/gis.html)と結び付け、時系列の入れ子を表に平らにして、QGIS や MapLibre で開ける形にします。

> [!NOTE]
> 開発を始めたところです。今あるのは調査用のスクリプトと[概要の整理](docs/jma-xml-overview.md)だけです。

## 方針

電文は約100種類ありますが、**場所の表し方**で分けると4つに収まります（詳しくは[概要](docs/jma-xml-overview.md)の第3章）。変換は電文の種類ごとではなく、この分類ごとに作ります。

| 分類 | GIS にする方法 | 主な電文 |
|---|---|---|
| A. 地域コード | 予報区等GISデータと結び付けて面にする | 警報・注意報、天気予報、土砂災害警戒情報、海上予報 |
| B. 座標・図形 | 電文の中の座標（ISO 6709）をそのまま点・線・面にする | 震源、天気図、全般海上警報、降灰予報 |
| C. 観測地点のコード | 地点表と結び付けて点にする | 天気予報の地点予報、2週間気温予報、生物季節観測 |
| D. 文章が中心 | 発表した区域に文章を付ける | 府県天気概況、気象情報、潮位情報 |

## 関連リポジトリ

- MCP サーバー（Claude から「今どこに警報が出ている？」と聞くと地図付きで返す）は別のリポジトリで作ります（予定）。
- 変換した予報区等GISデータと履歴は、[shi-works-catalog](https://github.com/shiwaku/shi-works-catalog) の `jp-jma/` に載せることを検討しています。

## 開発

```bash
uv sync
uv run python scripts/survey.py data/survey > data/survey_summary.json  # フィードと電文の概要を集計する
```

## 出典と利用上の注意

- 元データ: 気象庁「[気象庁防災情報XML](https://xml.kishou.go.jp/)」、「[予報区等GISデータ](https://www.data.jma.go.jp/developer/gis.html)」
- 利用にあたっては、気象庁の「[気象庁ホームページを通じて公開するXML形式電文のご利用にあたっての留意事項](https://xml.kishou.go.jp/considerationforxml.pdf)」を確認してください。予報や警報の**内容を書き換えないこと**、**出典を明示すること**が求められています。このツールは形式だけを変換し、値は変えません。
- 1日に10GB以上ダウンロードすると、アクセス元のIPアドレスが遮断されます。このツールは、一度取得した電文を再び取得しないように作ります。
- 変換した警報などは**発表時点の記録**です。いま発表されている情報として扱わないでください。

## ライセンス

コードは [MIT License](LICENSE)。
