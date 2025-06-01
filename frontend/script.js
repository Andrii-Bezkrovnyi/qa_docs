const form = document.getElementById('qa-form');
const questionInput = document.getElementById('question');
const answerDiv = document.getElementById('answer');
const historyUl = document.getElementById('history');
let history = [];

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const question = questionInput.value.trim();
  if (!question) return;

  answerDiv.textContent = "Thinking...";
  try {
    const res = await fetch('http://localhost:8000/api/ask', {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (!res.ok) throw new Error("API error");
    const data = await res.json();
    answerDiv.textContent = data.answer;
    history.unshift({ question, answer: data.answer });
    updateHistory();
  } catch (e) {
    answerDiv.textContent = "Request failed.";
  }
  questionInput.value = "";
});

function updateHistory() {
  historyUl.innerHTML = '';
  history.forEach(item => {
    const li = document.createElement('li');
    li.innerHTML = `<b>Q:</b> ${item.question}<br><b>A:</b> ${item.answer}`;
    historyUl.appendChild(li);
  });
}

// On page load, fetch history
window.onload = async () => {
  try {
    const res = await fetch('http://localhost:8000/api/history');
    if (!res.ok) return;
    const data = await res.json();
    history = data;
    updateHistory();
  } catch {}
};
