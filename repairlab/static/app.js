"use strict";
const form = document.querySelector("#booking-form");
const grid = document.querySelector("#service-grid");
const statusBox = document.querySelector("#form-status");
let services = [];
function renderServices(category = "Все") {
  grid.replaceChildren();
  for (const service of services.filter(
    (s) => category === "Все" || s.category === category,
  )) {
    const article = document.createElement("article");
    article.className = "service";
    // Разметка постоянная; данные API вставляются через textContent.
    article.innerHTML =
      '<div class="service-illustration"><img width="240" height="160" alt=""></div><div class="service-body"><h3></h3><p></p><div class="service-bottom"><b></b><button type="button">→</button></div></div>';
    article.querySelector("img").src = `assets/${service.image}`;
    article.querySelector("h3").textContent = service.title;
    article.querySelector("p").textContent = service.description;
    article.querySelector("b").textContent =
      `от ${service.price.toLocaleString("ru-RU")} ₽`;
    const button = article.querySelector("button");
    button.setAttribute("aria-label", `Записаться: ${service.title}`);
    button.addEventListener("click", () => {
      form.elements.service.value = service.id;
      document
        .querySelector("#booking")
        .scrollIntoView({
          behavior: matchMedia("(prefers-reduced-motion: reduce)").matches
            ? "instant"
            : "smooth",
        });
      form.elements.name.focus({ preventScroll: true });
    });
    grid.append(article);
  }
}
async function loadServices() {
  try {
    const response = await fetch("api/services");
    if (!response.ok) throw new Error();
    services = await response.json();
    for (const service of services) {
      const option = document.createElement("option");
      option.value = service.id;
      option.textContent = service.title;
      form.elements.service.append(option);
    }
    renderServices();
  } catch {
    grid.textContent =
      "Не удалось загрузить услуги. Проверьте подключение и перезагрузите страницу. Запускайте сайт через python app.py, а не открытием HTML-файла.";
  }
}
for (const button of document.querySelectorAll(".filter")) {
  button.addEventListener("click", () => {
    for (const item of document.querySelectorAll(".filter")) {
      item.classList.toggle("active", item === button);
      item.setAttribute("aria-pressed", String(item === button));
    }
    renderServices(button.dataset.filter);
  });
}
function localDate(value) {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}
const now = new Date();
const limit = new Date();
limit.setDate(limit.getDate() + 90);
form.elements.visit_date.min = localDate(now);
form.elements.visit_date.max = localDate(limit);
function showErrors(errors) {
  for (const key of [
    "name",
    "phone",
    "service",
    "visit_date",
    "problem",
    "consent",
  ]) {
    const field = form.elements[key];
    document.querySelector(`#err-${key}`).textContent = errors[key] || "";
    field.setAttribute("aria-invalid", String(Boolean(errors[key])));
    field.setAttribute("aria-describedby", `err-${key}`);
  }
  const first = Object.keys(errors).find((key) => form.elements[key]);
  if (first) form.elements[first].focus();
}
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(form));
  data.consent = form.elements.consent.checked;
  const errors = {};
  if (data.name.trim().length < 2)
    errors.name = "Введите имя: минимум 2 символа.";
  if (
    !/^\+?[\d\s()\-]{10,25}$/.test(data.phone) ||
    data.phone.replace(/\D/g, "").length < 10 ||
    data.phone.replace(/\D/g, "").length > 15
  )
    errors.phone = "Введите телефон: от 10 до 15 цифр.";
  if (!services.some((s) => s.id === data.service))
    errors.service = "Выберите устройство.";
  if (
    !data.visit_date ||
    data.visit_date < form.elements.visit_date.min ||
    data.visit_date > form.elements.visit_date.max
  )
    errors.visit_date = "Выберите дату в ближайшие 90 дней.";
  if (data.problem.trim().length < 10)
    errors.problem = "Описание должно содержать минимум 10 символов.";
  if (!data.consent)
    errors.consent = "Подтвердите согласие на обработку данных.";
  showErrors(errors);
  statusBox.textContent = "";
  statusBox.className = "";
  if (Object.keys(errors).length) return;
  const button = form.querySelector(".submit");
  button.disabled = true;
  statusBox.textContent = "Отправляем заявку…";
  try {
    const response = await fetch("api/requests", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
      signal: AbortSignal.timeout(15000),
    });
    const result = await response.json();
    if (!response.ok) {
      showErrors(result.errors || {});
      throw new Error(result.message || "Не удалось отправить заявку.");
    }
    statusBox.textContent = `${result.message} Номер: ${result.id}`;
    form.reset();
  } catch (error) {
    statusBox.className = "failure";
    statusBox.textContent =
      error.name === "TimeoutError"
        ? "Сервер долго отвечает. Заявка могла сохраниться: уточните это перед повторной отправкой."
        : error instanceof TypeError
          ? "Нет связи с сервером. Проверьте подключение. Если запрос уже ушёл, уточните сохранение перед повтором."
          : error.message;
  } finally {
    button.disabled = false;
  }
});
loadServices();
