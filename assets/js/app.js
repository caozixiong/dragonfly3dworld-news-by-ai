// Dragonfly 3D World News by AI — 前端小交互
// 目前主要做归档页的关键词过滤，数据来自 data/news.json（预留）
document.addEventListener("DOMContentLoaded", () => {
  const input = document.getElementById("filter");
  if (!input) return;
  const cards = Array.from(document.querySelectorAll("article.card"));
  input.addEventListener("input", () => {
    const q = input.value.trim().toLowerCase();
    cards.forEach((c) => {
      c.style.display = c.textContent.toLowerCase().includes(q) ? "" : "none";
    });
  });
});
