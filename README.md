# 腎臟專科模擬考題平台

這是一個純前端的線上練習網站，可用來提供腎臟專科醫師考試模擬題練習。

## 目前功能

- 隨機模擬考
- 分類練習
- 自選章節組卷
- 單題練習
- 作答後立即顯示正解、解析與考點
- 收藏題目
- 錯題複習
- 本機成績紀錄

## 目前題庫

目前題庫已擴充為 100 題英文五選一，涵蓋腎生理、電解質酸鹼、AKI、腎絲球疾病、CKD、透析、移植、遺傳性腎病與尿路結石等核心範圍。

自選章節清單已依 Brenner 11th edition 全書 85 章建立。每題都有 `chapter` 欄位，系統會依考生勾選的章節自動配題。

## 本機預覽

目前本機預覽服務已啟動：

```text
http://127.0.0.1:4173
```

也可以直接開啟 `index.html` 預覽，但使用本機伺服器會比較接近正式上線環境。

## 擴充題庫

題目資料在 `questions-data.js`。新增題目時，依照以下格式加入：

```js
{
  id: "ckd-001",
  chapter: "59 Classification and Management of Chronic Kidney Disease",
  category: "CKD",
  difficulty: "臨床",
  question: "題目文字",
  options: ["A option", "B option", "C option", "D option", "E option"],
  answer: 1,
  explanation: "解析文字",
  pearl: "考點提示"
}
```

`answer` 使用 0 起算：A 是 0，B 是 1，C 是 2，D 是 3。
