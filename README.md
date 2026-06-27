# Brenner and Rector's The Kidney 題庫產生與選題系統

本專案用於建立「Brenner and Rector's The Kidney」腎臟專科醫師考試題庫產生、審題、去重、匯出與選題流程。核心原則是：所有題目只能根據使用者提供的 Brenner 原文內容產生，並保留可追溯來源，但不得公開散布原文或大量重製原文。

本資料夾同時保留既有線上練習網站檔案，例如 `index.html`、`app.js`、`questions-data.js`。題庫產生 pipeline 位於 `src/`、`prompts/`、`data/`、`outputs/`。

## 專案目的

- 依 Brenner 全書 85 章建立高品質基礎題庫。
- 每章目標 100 題，全書目標 8,500 題。
- 題目形式為英文五選一單選題，A-E，只有一個最佳答案。
- 每題保留章節、來源小節、chunk ID、段落範圍與簡短依據摘要。
- 題庫需經過命題、審題、修訂、去重、品質評分與正式考卷選題。

## 重要限制

1. 只能根據使用者提供的 Brenner 原文命題。
2. 不得使用外部知識、guideline、臨床經驗或模型自行補充內容。
3. 不得大量輸出或重製 Brenner 原文。
4. 最終題庫只保留 `source_chunk_id`、`source_paragraph_range` 與簡短 `source_basis`。
5. 若原文不足以支持明確單選題，應標記為不適合命題，不可硬出題。

## 資料夾結構

```text
data/
  raw_chapters/          # 放入 chapter_001.txt 至 chapter_085.txt
  chunks/                # chunking.py 輸出的章節 chunks
  blueprints/            # 章節命題藍圖 JSON
  generated_questions/   # 初稿題目
  reviewed_questions/    # 審題後題目
  final_item_bank/       # 最終可收錄題庫
  exams/                 # 正式考卷資料
prompts/
  01_chapter_blueprint_prompt.txt
  02_question_generation_prompt.txt
  03_quality_review_prompt.txt
  04_deduplication_prompt.txt
  05_exam_selection_prompt.txt
  06_revision_prompt.txt
src/
  schemas.py
  chunking.py
  export.py
outputs/
  item_bank.jsonl
  item_bank.csv
  item_bank.xlsx
  exam_sets/
```

## 如何放入 Brenner 原文

將每章純文字放在 `data/raw_chapters/`：

```text
data/raw_chapters/chapter_001.txt
data/raw_chapters/chapter_002.txt
...
data/raw_chapters/chapter_085.txt
```

請保留原文順序。系統不會修改原始檔，chunking 只會讀取並產生可追蹤的 JSON。

若提供的完整 Brenner PDF 含有章節書籤，可自動辨識並抽取 85 章：

```bash
python src/extract_brenner_pdf.py --pdf "Brenner 11th Edition PDF.pdf"
```

輸出：

- `data/chapter_catalog.json`: 85 章名稱、PDF 起訖頁與小節書籤
- `data/raw_chapters/chapter_001.txt` 至 `chapter_085.txt`
- 每章對應的 `chapter_001_manifest.json` 至 `chapter_085_manifest.json`

原文與 chunks 已列入 `.gitignore`，不可上傳至公開 GitHub。每章 manifest 會保留來源 PDF hash、PDF 頁碼、文字檔 hash 與每頁字元偏移，供後續追蹤。

可先透過匯入工具複製原文並建立 SHA-256 manifest：

```bash
python src/ingest.py --input authorized_chapter_001.txt --chapter CH001 --title "Embryology of the Kidney"
```

## 如何執行 chunking

單章切分：

```bash
python src/chunking.py --input data/raw_chapters/chapter_001.txt --output data/chunks/chapter_001_chunks.json --chapter-id CH001 --chapter-title "Embryology of the Kidney"
```

批次切分：

```bash
python src/chunking.py --input-dir data/raw_chapters --output-dir data/chunks
```

每個 chunk 會包含：

- `chapter_id`
- `chapter_title`
- `section_title`
- `chunk_id`
- `paragraph_range`
- `text`
- `word_count`

建議 chunk 長度為 500-1,200 words。程式會盡量依小節標題與段落切分。

## 如何建立章節 blueprint

先建立只包含本章 chunks 的 blueprint prompt：

```bash
python src/blueprint.py --chapter CH001
```

模型回傳 JSON 後，先驗證再存入正式 blueprint：

```bash
python src/blueprint.py --chapter CH001 --response model_blueprint.json
```

每章 blueprint 應規劃 100 題，包含核心考點、題型分布、難度分布與不適合命題內容。

## 如何分批產生題目

建立第一批 10 題的命題 prompt：

```bash
python src/generate_questions.py --chapter CH001 --batch 1
```

模型回傳 JSON array 後驗證：

```bash
python src/generate_questions.py --chapter CH001 --batch 1 --response model_batch_01.json
```

每章 100 題需分成 10 批，每批 10 題：

```text
CH001-Q001 至 CH001-Q010
CH001-Q011 至 CH001-Q020
...
CH001-Q091 至 CH001-Q100
```

每批輸入需包含：

- 本章 blueprint
- 已產生題目摘要
- 本批題號範圍
- 指定來源 chunks

初稿題目會存到：

```text
data/generated_questions/CH001_batch_01.json
```

## 如何審題

為指定題目建立 reviewer prompt：

```bash
python src/review_questions.py --questions data/generated_questions/CH001_batch_01.json --chunks data/chunks/chapter_001_chunks.json --question-id CH001-Q001
```

Reviewer 回傳 JSON 後套用審查：

```bash
python src/review_questions.py --questions data/generated_questions/CH001_batch_01.json --chunks data/chunks/chapter_001_chunks.json --response CH001_batch_01_reviews.json
```

每題需由第二階段 reviewer 檢查：

- 是否完全忠於原文
- 是否使用外部知識
- 是否只有一個最佳答案
- 選項是否同質且長度平衡
- 是否有 cueing
- 是否過度瑣碎
- 是否與既有題目重複

審題後題目會存到：

```text
data/reviewed_questions/CH001_batch_01_reviewed.json
```

品質分數建議：

- `>=90`: 可直接收錄
- `80-89`: 小修後收錄
- `70-79`: 需大修
- `<70`: 刪除或重寫

## 如何去重

同章去重：

```bash
python src/deduplicate.py --scope chapter --chapter CH001
```

跨章去重：

```bash
python src/deduplicate.py --scope all
```

程式會檢查：

- 題幹相似
- 考點相似
- 正解相似
- 解析相似
- 同一來源 chunk 過度集中

若高度重複，保留品質分數較高者；若考點重要，可改寫為不同角度，但仍須忠於原文。

## 如何匯出題庫

將 accepted 題目放入 `data/final_item_bank/`，可為 `.json` 或 `.jsonl`。

匯出全部格式：

```bash
python src/export.py --input-dir data/final_item_bank --output-dir outputs --format all
```

匯出單一格式：

```bash
python src/export.py --input-dir data/final_item_bank --output-dir outputs --format xlsx
python src/export.py --input-dir data/final_item_bank --output-dir outputs --format csv
python src/export.py --input-dir data/final_item_bank --output-dir outputs --format jsonl
```

輸出欄位包含：

`question_id`, `chapter_id`, `chapter_title`, `section_title`, `source_chunk_id`, `source_paragraph_range`, `tested_concept`, `question_type`, `difficulty`, `stem`, `option_a`, `option_b`, `option_c`, `option_d`, `option_e`, `correct_answer`, `explanation`, `option_a_explanation`, `option_b_explanation`, `option_c_explanation`, `option_d_explanation`, `option_e_explanation`, `source_basis`, `quality_score`, `review_status`, `revision_notes`, `created_at`, `updated_at`

## 如何產生正式考卷

`src/select_exam.py` 已實作正式考卷選題，規則如下：

- 只選 `review_status = accepted`
- 排除 `quality_score < 90`
- 章節分布均衡
- 題型分布均衡
- 難度以 `basic` 為主，少量 `basic_to_intermediate`
- 避免同一考點重複
- 避免同一來源 chunk 過度集中
- 可設定章節權重

執行命令：

```bash
python src/select_exam.py --num-questions 100 --exam-id exam_set_001
```

系統會產生：

- `exam_set_001.xlsx`
- `exam_set_001_questions_only.docx`
- `exam_set_001_answer_key.xlsx`
- `exam_set_001_with_explanations.docx`
- `exam_set_001_manifest.json`

## 版權注意事項

本系統只能在使用者合法提供原文的前提下，用於建立教學與複習題庫。不得公開散布 Brenner 原文、完整段落、表格、圖說或大量逐字摘錄。題庫應保留來源追蹤資訊，但 `source_basis` 只能是簡短依據摘要，不應重製受版權保護內容。

## 已完成功能

- `src/schemas.py`
- `src/extract_brenner_pdf.py`
- `src/ingest.py`
- `src/chunking.py`
- `src/blueprint.py`
- `src/generate_questions.py`
- `src/review_questions.py`
- `src/deduplicate.py`
- `src/select_exam.py`
- `src/export.py`
- `src/utils.py`
- `prompts/01_chapter_blueprint_prompt.txt`
- `prompts/02_question_generation_prompt.txt`
- `prompts/03_quality_review_prompt.txt`
- `prompts/04_deduplication_prompt.txt`
- `prompts/05_exam_selection_prompt.txt`
- `prompts/06_revision_prompt.txt`
- `data/blueprints/chapter_weights.json`
- `tests/test_pipeline.py`
- `README.md`

## 模型互動方式

為了確保所有題目只能根據使用者提供的原文產生，程式不會自行從網路取得醫學內容。流程分成：

1. CLI 產生包含指定 chunks 的 prompt。
2. 將 prompt 交給命題或審題模型。
3. 將模型回傳的 JSON 透過 `--response` 送回 CLI 驗證。
4. 通過 chapter、chunk、題號與 QuestionItem schema 驗證後才寫入題庫。

## 測試

```bash
set PYTHONPATH=src
python -m unittest discover -s tests -v
```

目前測試涵蓋 chunking、blueprint、分批題號、QuestionItem schema、去重、章節加權選題與 XLSX/DOCX 輸出。

## 後續可擴充

- 對接特定模型 API，但仍必須只傳送使用者提供的 chunks。
- 增加人工審題簽核介面與版本紀錄。
- 增加更進階的 embedding 去重；目前已提供不依賴外部服務的文字相似度去重。
- 將通過審核的 final item bank 自動轉換為線上網站 `questions-data.js`。
