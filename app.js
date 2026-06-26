const questions = Array.isArray(window.NEPHRO_QUESTIONS) ? window.NEPHRO_QUESTIONS : [];
const brennerChapters = Array.isArray(window.BRENNER_CHAPTERS) ? window.BRENNER_CHAPTERS : [];
const questionBankTarget = window.QUESTION_BANK_TARGET || { questionsPerChapter: 150, totalChapters: 85, totalQuestions: 12750 };
const views = ["homeView", "quizView", "resultView", "libraryView", "statsView"];
const storageKey = "nephroBoardPracticeStats";

const state = {
  mode: "mixed",
  activeQuestions: [],
  index: 0,
  correct: 0,
  answered: false,
  currentStreak: 0,
  customChapters: [],
  customLimit: 10,
  stats: loadStats()
};

function $(id) {
  return document.getElementById(id);
}

function loadStats() {
  const defaults = {
    total: 0,
    correct: 0,
    bestStreak: 0,
    bookmarks: [],
    missed: [],
    categoryTotals: {}
  };

  try {
    return { ...defaults, ...JSON.parse(localStorage.getItem(storageKey) || "{}") };
  } catch {
    return defaults;
  }
}

function saveStats() {
  localStorage.setItem(storageKey, JSON.stringify(state.stats));
  updateDashboard();
}

function showView(viewName) {
  views.forEach((id) => $(id).classList.toggle("hidden", id !== viewName));
  document.querySelectorAll(".nav-link").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === viewName);
  });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function shuffle(items) {
  return [...items].sort(() => Math.random() - 0.5);
}

function uniqueCategories() {
  return [...new Set(questions.map((question) => question.category))];
}

function questionChapter(question) {
  return question.chapter || question.category || "未分類章節";
}

function uniqueChapters() {
  return [...new Set([...brennerChapters, ...questions.map(questionChapter)])];
}

function buildCategoryCards() {
  const grid = $("categoryCards");
  if (!grid) return;
  const categories = uniqueCategories();
  const cards = [
    {
      title: "完整模擬考",
      label: "Mixed exam",
      description: "從目前題庫隨機抽題，適合快速檢查整章熟悉度。",
      meta: `${Math.min(10, questions.length)} 題`,
      mode: "mixed",
      accent: "dark"
    },
    ...categories.map((category) => {
      const count = questions.filter((question) => question.category === category).length;
      return {
        title: category,
        label: "Topic practice",
        description: "針對單一考點集中練習，作答後立即看到解析。",
        meta: `${count} 題`,
        mode: `category:${category}`,
        accent: ""
      };
    })
  ];

  grid.replaceChildren();
  cards.forEach((card) => {
    const article = document.createElement("article");
    article.className = `practice-card ${card.accent}`;
    article.innerHTML = `
      <span>${card.label}</span>
      <h3>${card.title}</h3>
      <p>${card.description}</p>
      <div class="card-footer">
        <strong>${card.meta}</strong>
        <button class="card-button" data-mode="${card.mode}">開始</button>
      </div>
    `;
    grid.appendChild(article);
  });

  grid.querySelectorAll("[data-mode]").forEach((button) => {
    button.addEventListener("click", () => startQuiz(button.dataset.mode));
  });
}

function buildChapterSelector() {
  const selector = $("chapterSelector");
  if (!selector) return;

  selector.replaceChildren();
  uniqueChapters().forEach((chapter) => {
    const chapterQuestions = questions.filter((question) => questionChapter(question) === chapter);
    const chapterProgress = Math.min(chapterQuestions.length, questionBankTarget.questionsPerChapter);
    const progressPercent = Math.round((chapterProgress / questionBankTarget.questionsPerChapter) * 100);
    const label = document.createElement("label");
    label.className = "chapter-option";
    label.innerHTML = `
      <input type="checkbox" value="${chapter}" checked>
      <span>
        <strong>${chapter}</strong>
        <small>${chapterProgress} / ${questionBankTarget.questionsPerChapter} 題</small>
        <i class="chapter-progress"><b style="width:${progressPercent}%"></b></i>
      </span>
    `;
    selector.appendChild(label);
  });

  selector.querySelectorAll('input[type="checkbox"]').forEach((input) => {
    input.addEventListener("change", updateCustomExamSummary);
  });
  updateCustomExamSummary();
}

function selectedChapters() {
  return [...document.querySelectorAll('#chapterSelector input[type="checkbox"]:checked')]
    .map((input) => input.value);
}

function updateCustomExamSummary() {
  const chapters = selectedChapters();
  const selectedCount = questions.filter((question) => chapters.includes(questionChapter(question))).length;

  $("selectedChapterCount").textContent = chapters.length;
  $("selectedQuestionCount").textContent = selectedCount;
  $("startCustomExam").disabled = selectedCount === 0;
}

function buildLibraryTable() {
  const table = $("libraryTable");
  table.replaceChildren();

  uniqueCategories().forEach((category) => {
    const section = document.createElement("section");
    section.className = "library-group";
    const list = questions.filter((question) => question.category === category);
    section.innerHTML = `
      <div class="library-group-title">
        <h3>${category}</h3>
        <span>${list.length} 題</span>
      </div>
    `;

    list.forEach((question, index) => {
      const row = document.createElement("button");
      row.className = "library-row";
      row.type = "button";
      row.innerHTML = `
        <span>${String(index + 1).padStart(2, "0")}</span>
        <strong>${question.question}</strong>
        <em>${question.difficulty}</em>
      `;
      row.addEventListener("click", () => startQuiz(`single:${question.id}`));
      section.appendChild(row);
    });

    table.appendChild(section);
  });
}

function getQuestionPool(mode) {
  if (mode.startsWith("category:")) {
    const category = mode.replace("category:", "");
    return questions.filter((question) => question.category === category);
  }

  if (mode === "missed") {
    return questions.filter((question) => state.stats.missed.includes(question.id));
  }

  if (mode === "custom") {
    return questions.filter((question) => state.customChapters.includes(questionChapter(question)));
  }

  if (mode.startsWith("single:")) {
    const id = mode.replace("single:", "");
    return questions.filter((question) => question.id === id);
  }

  return questions;
}

function startQuiz(mode = "mixed") {
  let pool = getQuestionPool(mode);
  if (!pool.length && mode === "missed") {
    alert("目前沒有錯題紀錄。");
    return;
  }

  state.mode = mode;
  const requestedCount = mode === "custom" ? state.customLimit : 100;
  const limit = requestedCount === "all" ? pool.length : Number(requestedCount);
  state.activeQuestions = shuffle(pool).slice(0, Math.min(limit, pool.length));
  state.index = 0;
  state.correct = 0;
  state.answered = false;
  state.currentStreak = 0;

  $("totalNumber").textContent = state.activeQuestions.length;
  $("quizLabel").textContent = getModeLabel(mode);
  showView("quizView");
  renderQuestion();
}

function startCustomQuiz() {
  const chapters = selectedChapters();
  const limit = $("customQuestionLimit").value;
  const pool = questions.filter((question) => chapters.includes(questionChapter(question)));

  if (!pool.length) {
    alert("請至少選擇一個有題目的章節。");
    return;
  }

  state.customChapters = chapters;
  state.customLimit = limit;
  startQuiz("custom");
}

function getModeLabel(mode) {
  if (mode === "mixed") return "完整模擬考";
  if (mode === "custom") return "自選章節";
  if (mode === "missed") return "錯題複習";
  if (mode.startsWith("category:")) return mode.replace("category:", "");
  if (mode.startsWith("single:")) return "單題練習";
  return "模擬考";
}

function renderQuestion() {
  state.answered = false;
  const question = state.activeQuestions[state.index];
  const progress = ((state.index + 1) / state.activeQuestions.length) * 100;

  $("currentNumber").textContent = state.index + 1;
  $("quizProgress").style.width = `${progress}%`;
  $("questionCategory").textContent = `${questionChapter(question)} / ${question.category}`;
  $("questionDifficulty").textContent = question.difficulty;
  $("questionText").textContent = question.question;
  $("answerHint").textContent = "請選擇一個答案";
  $("nextQuestion").classList.add("hidden");
  $("explanation").classList.add("hidden");
  $("bookmarkButton").textContent = state.stats.bookmarks.includes(question.id) ? "★" : "☆";

  const options = $("options");
  options.replaceChildren();
  question.options.forEach((option, index) => {
    const button = document.createElement("button");
    button.className = "option";
    button.dataset.index = index;

    const letter = document.createElement("span");
    letter.className = "option-letter";
    letter.textContent = String.fromCharCode(65 + index);

    const text = document.createElement("span");
    text.textContent = option;

    button.append(letter, text);
    button.addEventListener("click", selectAnswer);
    options.appendChild(button);
  });
}

function selectAnswer(event) {
  if (state.answered) return;
  state.answered = true;

  const selected = Number(event.currentTarget.dataset.index);
  const question = state.activeQuestions[state.index];
  const isCorrect = selected === question.answer;

  document.querySelectorAll(".option").forEach((button, index) => {
    button.disabled = true;
    if (index === question.answer) button.classList.add("correct");
    if (index === selected && !isCorrect) button.classList.add("wrong");
  });

  state.stats.total += 1;
  state.stats.categoryTotals[question.category] = (state.stats.categoryTotals[question.category] || 0) + 1;

  if (isCorrect) {
    state.correct += 1;
    state.stats.correct += 1;
    state.currentStreak += 1;
    state.stats.bestStreak = Math.max(state.stats.bestStreak, state.currentStreak);
    state.stats.missed = state.stats.missed.filter((id) => id !== question.id);
    $("answerHint").textContent = "答對了";
  } else {
    state.currentStreak = 0;
    if (!state.stats.missed.includes(question.id)) state.stats.missed.push(question.id);
    $("answerHint").textContent = `正確答案是 ${String.fromCharCode(65 + question.answer)}`;
  }

  renderExplanation(question);
  $("nextQuestion").classList.remove("hidden");
  $("nextQuestion").textContent = state.index === state.activeQuestions.length - 1 ? "查看結果" : "下一題";
  saveStats();
}

function renderExplanation(question) {
  const correctAnswer = `${String.fromCharCode(65 + question.answer)}. ${question.options[question.answer]}`;
  $("explanation").innerHTML = `
    <div class="correct-answer-line">正確答案：${correctAnswer}</div>
    <strong>解析</strong>
    <p>${question.explanation}</p>
    <strong>考點</strong>
    <p>${question.pearl}</p>
  `;
  $("explanation").classList.remove("hidden");
}

function finishQuiz() {
  const total = state.activeQuestions.length;
  const score = total ? Math.round((state.correct / total) * 100) : 0;

  $("resultScore").textContent = score;
  $("resultCorrect").textContent = state.correct;
  $("resultWrong").textContent = total - state.correct;
  $("resultAccuracy").textContent = `${score}%`;
  $("resultMessage").textContent =
    score >= 80
      ? "表現很好。可以進一步練習進階與臨床情境題。"
      : score >= 60
        ? "已有基礎掌握，建議回頭看錯題解析並補強薄弱分類。"
        : "建議先複習本章核心機轉，再用分類練習逐題確認。";

  showView("resultView");
}

function updateDashboard() {
  const stats = state.stats;
  const accuracy = stats.total ? Math.round((stats.correct / stats.total) * 100) : 0;

  $("heroAccuracy").textContent = stats.total ? `${accuracy}%` : "--";
  $("heroAnswered").textContent = stats.total;
  $("heroStreak").textContent = stats.bestStreak;
  $("heroBookmarks").textContent = stats.bookmarks.length;
  $("heroRing").style.background = `conic-gradient(#177a73 ${accuracy}%, #dfe8e5 0)`;

  $("statTotal").textContent = stats.total;
  $("statAccuracy").textContent = stats.total ? `${accuracy}%` : "--";
  $("statBest").textContent = stats.bestStreak;
  $("statMissed").textContent = stats.missed.length;
  $("statsEmpty").classList.toggle("hidden", stats.total > 0);
}

function toggleBookmark() {
  const question = state.activeQuestions[state.index];
  const bookmarks = state.stats.bookmarks;
  const position = bookmarks.indexOf(question.id);

  if (position >= 0) {
    bookmarks.splice(position, 1);
  } else {
    bookmarks.push(question.id);
  }

  $("bookmarkButton").textContent = bookmarks.includes(question.id) ? "★" : "☆";
  saveStats();
}

function bindEvents() {
  document.querySelectorAll(".nav-link").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.view === "libraryView") buildLibraryTable();
      if (button.dataset.view === "statsView") updateDashboard();
      showView(button.dataset.view);
    });
  });

  ["quickStart", "heroStart", "statsStart"].forEach((id) => {
    $(id).addEventListener("click", () => startQuiz("mixed"));
  });

  $("reviewMissed").addEventListener("click", () => startQuiz("missed"));
  $("startCustomExam").addEventListener("click", startCustomQuiz);
  $("customQuestionLimit").addEventListener("change", updateCustomExamSummary);
  $("selectAllChapters").addEventListener("click", () => {
    document.querySelectorAll('#chapterSelector input[type="checkbox"]').forEach((input) => {
      input.checked = true;
    });
    updateCustomExamSummary();
  });
  $("clearChapters").addEventListener("click", () => {
    document.querySelectorAll('#chapterSelector input[type="checkbox"]').forEach((input) => {
      input.checked = false;
    });
    updateCustomExamSummary();
  });
  $("quitQuiz").addEventListener("click", () => showView("homeView"));
  $("backHome").addEventListener("click", () => showView("homeView"));
  $("retryQuiz").addEventListener("click", () => startQuiz(state.mode));
  $("bookmarkButton").addEventListener("click", toggleBookmark);
  $("nextQuestion").addEventListener("click", () => {
    if (state.index < state.activeQuestions.length - 1) {
      state.index += 1;
      renderQuestion();
    } else {
      finishQuiz();
    }
  });

  $("resetStats").addEventListener("click", () => {
    if (!confirm("確定要清除本機練習紀錄嗎？")) return;
    state.stats = {
      total: 0,
      correct: 0,
      bestStreak: 0,
      bookmarks: [],
      missed: [],
      categoryTotals: {}
    };
    saveStats();
  });
}

buildCategoryCards();
buildChapterSelector();
buildLibraryTable();
bindEvents();
updateDashboard();
