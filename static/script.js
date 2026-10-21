"use strict";

// Общее мобильное меню. Кнопка доступна с клавиатуры.
const menuButton = document.querySelector(".menu-toggle");
const mainNav = document.querySelector("#main-nav");
if (menuButton && mainNav) {
  function closeMenu() {
    menuButton.setAttribute("aria-expanded", "false");
    menuButton.setAttribute("aria-label", "Открыть меню");
    mainNav.classList.remove("is-open");
  }
  menuButton.addEventListener("click", () => {
    const opening = menuButton.getAttribute("aria-expanded") !== "true";
    menuButton.setAttribute("aria-expanded", String(opening));
    menuButton.setAttribute(
      "aria-label",
      opening ? "Закрыть меню" : "Открыть меню",
    );
    mainNav.classList.toggle("is-open", opening);
  });
  mainNav.addEventListener("click", (event) => {
    if (event.target.closest("a")) closeMenu();
  });
  document.addEventListener("keydown", (event) => {
    if (
      event.key === "Escape" &&
      menuButton.getAttribute("aria-expanded") === "true"
    ) {
      closeMenu();
      menuButton.focus();
    }
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".site-header")) closeMenu();
  });
}

// Фильтрация уже полученного от Python-сервера каталога.
const searchInput = document.querySelector("#service-search");
if (searchInput) {
  const cards = [...document.querySelectorAll("#catalog .service-card")];
  const buttons = document.querySelectorAll("[data-filter]");
  let category = "all";
  function filterServices() {
    const query = searchInput.value.trim().toLocaleLowerCase("ru");
    let count = 0;
    for (const card of cards) {
      const categoryMatches =
        category === "all" || card.dataset.category === category;
      const nameMatches = card.dataset.name
        .toLocaleLowerCase("ru")
        .includes(query);
      card.hidden = !(categoryMatches && nameMatches);
      if (!card.hidden) count++;
    }
    document.querySelector("#catalog-count").textContent =
      `Найдено услуг: ${count}`;
    document.querySelector("#catalog-empty").hidden = count > 0;
  }
  function activateFilter(value) {
    category = value;
    for (const item of buttons) {
      const active = item.dataset.filter === value;
      item.classList.toggle("active", active);
      item.setAttribute("aria-pressed", String(active));
    }
    filterServices();
  }
  for (const button of buttons) {
    button.addEventListener("click", () =>
      activateFilter(button.dataset.filter),
    );
  }
  searchInput.addEventListener("input", filterServices);
  document
    .querySelector("#reset-service-filters")
    ?.addEventListener("click", () => {
      searchInput.value = "";
      activateFilter("all");
      searchInput.focus();
    });
  filterServices();
}

// Портфолио: фильтры и нативное модальное окно с возвратом фокуса.
const galleryFilters = document.querySelectorAll("[data-gallery-filter]");
if (galleryFilters.length) {
  for (const button of galleryFilters) {
    button.addEventListener("click", () => {
      const category = button.dataset.galleryFilter;
      for (const item of galleryFilters) {
        const active = item === button;
        item.classList.toggle("active", active);
        item.setAttribute("aria-pressed", String(active));
      }
      for (const item of document.querySelectorAll(".gallery-item")) {
        item.hidden = category !== "all" && item.dataset.category !== category;
      }
    });
  }
  const dialog = document.querySelector("#gallery-dialog");
  if (dialog) {
    for (const button of document.querySelectorAll(".gallery-open")) {
      button.addEventListener("click", () => {
        const image = dialog.querySelector("#gallery-dialog-image");
        image.src = button.dataset.image;
        image.alt = `${button.dataset.title} — демонстрационная иллюстрация`;
        dialog.querySelector("#gallery-dialog-title").textContent =
          button.dataset.title;
        dialog.showModal();
      });
    }
    dialog
      .querySelector(".dialog-close")
      .addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", (event) => {
      const bounds = dialog.getBoundingClientRect();
      const outside =
        event.clientX < bounds.left ||
        event.clientX > bounds.right ||
        event.clientY < bounds.top ||
        event.clientY > bounds.bottom;
      if (event.target === dialog && outside) dialog.close();
    });
  }
}

// Запись: услуга → подходящий мастер → свободное время → POST на сервер.
const bookingForm = document.querySelector("#booking-form");
if (bookingForm) {
  const serviceSelect = bookingForm.elements.service;
  const masterSelect = bookingForm.elements.master;
  const dateInput = bookingForm.elements.visit_date;
  const timeInput = bookingForm.elements.visit_time;
  const slotsBox = document.querySelector("#time-slots");
  const availabilityMessage = document.querySelector("#availability-message");
  const submitButton = document.querySelector("#booking-submit");
  const formMessage = document.querySelector("#form-message");
  const successPanel = document.querySelector("#booking-success");
  let mastersRequest = null;
  let slotsRequest = null;
  let submitting = false;
  let currentSlotValues = [];
  let availabilityVersion = 0;
  const initialMaster = bookingForm.dataset.initialMaster;

  function setError(name, message = "") {
    const box = bookingForm.querySelector(`[data-error="${name}"]`);
    if (box) box.textContent = message;
    const input = bookingForm.elements[name];
    if (input) input.setAttribute("aria-invalid", String(Boolean(message)));
  }
  function clearErrors() {
    for (const item of bookingForm.querySelectorAll("[data-error]")) {
      setError(item.dataset.error);
    }
  }
  function showMessage(text, type = "error") {
    formMessage.className = type;
    formMessage.textContent = text;
  }
  function resetSlots(hint = "Выберите услугу, мастера и дату.") {
    currentSlotValues = [];
    timeInput.value = "";
    submitButton.disabled = true;
    slotsBox.replaceChildren();
    const text = document.createElement("p");
    text.className = "slots-hint";
    text.textContent = hint;
    slotsBox.append(text);
    availabilityMessage.textContent = "";
    setError("visit_time");
  }
  function updateSummary() {
    const option = serviceSelect.selectedOptions[0];
    const price = Number(option?.dataset.price);
    const duration = Number(option?.dataset.duration);
    const summary = document.querySelector("#booking-summary");
    summary.hidden = !serviceSelect.value;
    if (serviceSelect.value) {
      document.querySelector("#summary-price").textContent =
        `${price.toLocaleString("ru-RU")} ₸`;
      document.querySelector("#summary-duration").textContent =
        `${duration} минут`;
    }
  }

  async function loadSlots() {
    slotsRequest?.abort();
    const version = ++availabilityVersion;
    const service = serviceSelect.value;
    const master = masterSelect.value;
    const day = dateInput.value;
    resetSlots();
    setError("visit_date");
    if (!service || !master || !day) return;
    if (!dateInput.validity.valid) {
      setError("visit_date", "Выберите дату в указанном диапазоне.");
      return;
    }
    resetSlots("Проверяем свободное время…");
    const controller = new AbortController();
    slotsRequest = controller;
    try {
      const query = new URLSearchParams({ service, master, date: day });
      const response = await fetch(`/api/availability?${query}`, {
        signal: controller.signal,
        headers: { Accept: "application/json" },
      });
      const result = await response.json();
      if (version !== availabilityVersion) return;
      if (!response.ok) {
        resetSlots("Не удалось получить свободное время.");
        for (const [name, error] of Object.entries(result.errors || {}))
          setError(name, error);
        availabilityMessage.textContent =
          result.message || "Измените параметры записи.";
        return;
      }
      currentSlotValues = result.slots || [];
      slotsBox.replaceChildren();
      if (!currentSlotValues.length) {
        resetSlots("На этот день свободного времени нет.");
        availabilityMessage.textContent =
          "Попробуйте выбрать другой день или мастера.";
        return;
      }
      for (const value of currentSlotValues) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "slot-button";
        button.textContent = value;
        button.dataset.time = value;
        button.setAttribute("aria-pressed", "false");
        button.addEventListener("click", () => {
          timeInput.value = value;
          for (const slot of slotsBox.querySelectorAll("button")) {
            const selected = slot === button;
            slot.classList.toggle("selected", selected);
            slot.setAttribute("aria-pressed", String(selected));
          }
          setError("visit_time");
          submitButton.disabled = submitting;
        });
        slotsBox.append(button);
      }
      availabilityMessage.textContent =
        "Выберите удобное время. Время может измениться до отправки заявки.";
    } catch (error) {
      if (error.name === "AbortError" || version !== availabilityVersion)
        return;
      resetSlots("Нет ответа от сервера.");
      availabilityMessage.textContent =
        "Проверьте соединение и измените дату, чтобы повторить запрос.";
    }
  }

  async function loadMasters(preferred = "") {
    mastersRequest?.abort();
    slotsRequest?.abort();
    ++availabilityVersion;
    resetSlots();
    updateSummary();
    masterSelect.replaceChildren(new Option("Загружаем мастеров…", ""));
    masterSelect.disabled = true;
    setError("service");
    setError("master");
    const service = serviceSelect.value;
    if (!service) {
      masterSelect.replaceChildren(new Option("Сначала выберите услугу", ""));
      return;
    }
    const controller = new AbortController();
    mastersRequest = controller;
    try {
      const response = await fetch(
        `/api/masters?${new URLSearchParams({ service })}`,
        {
          signal: controller.signal,
          headers: { Accept: "application/json" },
        },
      );
      const result = await response.json();
      if (service !== serviceSelect.value) return;
      if (!response.ok || !Array.isArray(result)) throw new Error("masters");
      masterSelect.replaceChildren(new Option("Выберите мастера", ""));
      for (const master of result)
        masterSelect.append(new Option(master.name, master.id));
      masterSelect.disabled = false;
      if (result.some((master) => master.id === preferred))
        masterSelect.value = preferred;
      else if (result.length === 1) masterSelect.value = result[0].id;
      if (!result.length)
        setError("master", "Для этой услуги пока нет доступных мастеров.");
      await loadSlots();
    } catch (error) {
      if (error.name === "AbortError") return;
      masterSelect.replaceChildren(
        new Option("Не удалось загрузить мастеров", ""),
      );
      setError("master", "Проверьте соединение и выберите услугу повторно.");
    }
  }

  serviceSelect.addEventListener("change", () =>
    loadMasters(masterSelect.value || initialMaster),
  );
  masterSelect.addEventListener("change", () => {
    setError("master");
    loadSlots();
  });
  dateInput.addEventListener("change", loadSlots);
  for (const name of ["name", "phone", "comment", "consent"]) {
    bookingForm.elements[name].addEventListener("input", () => setError(name));
  }

  bookingForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (submitting) return;
    clearErrors();
    showMessage("", "");
    if (!bookingForm.reportValidity()) return;
    if (!serviceSelect.value || !masterSelect.value) {
      setError("master", "Выберите услугу и мастера.");
      return;
    }
    if (!currentSlotValues.includes(timeInput.value)) {
      setError("visit_time", "Выберите свободное время.");
      slotsBox.querySelector("button")?.focus();
      return;
    }
    const data = Object.fromEntries(new FormData(bookingForm));
    data.consent = bookingForm.elements.consent.checked;
    submitting = true;
    submitButton.disabled = true;
    bookingForm.setAttribute("aria-busy", "true");
    for (const fieldset of bookingForm.querySelectorAll("fieldset"))
      fieldset.disabled = true;
    bookingForm.elements.consent.disabled = true;
    showMessage("Сохраняем вашу заявку…", "loading");
    let errorFocus = null;
    try {
      const token =
        document.querySelector('meta[name="csrf-token"]')?.content || "";
      const response = await fetch("/api/bookings", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": token },
        body: JSON.stringify(data),
        signal: AbortSignal.timeout(15000),
      });
      const result = await response.json();
      if (!response.ok) {
        for (const [name, error] of Object.entries(result.errors || {})) {
          setError(name, error);
          if (!errorFocus && bookingForm.elements[name]?.type !== "hidden")
            errorFocus = bookingForm.elements[name];
        }
        if (response.status === 409) await loadSlots();
        showMessage(
          result.message || "Не удалось создать запись. Проверьте поля формы.",
        );
        return;
      }
      document.querySelector("#success-id").textContent = result.id;
      const info = result.booking || {};
      const day = info.date || data.visit_date;
      const formattedDate = new Date(`${day}T12:00:00`).toLocaleDateString(
        "ru-RU",
        { day: "numeric", month: "long", year: "numeric" },
      );
      const details = document.querySelector("#success-details");
      details.replaceChildren();
      const rows = [
        [
          "Услуга",
          info.service || serviceSelect.selectedOptions[0].textContent,
        ],
        ["Мастер", info.master || masterSelect.selectedOptions[0].textContent],
        ["Дата", formattedDate],
        ["Время", info.time || data.visit_time],
      ];
      for (const [label, value] of rows) {
        const row = document.createElement("div");
        const title = document.createElement("dt");
        const text = document.createElement("dd");
        title.textContent = label;
        text.textContent = value;
        row.append(title, text);
        details.append(row);
      }
      bookingForm.hidden = true;
      successPanel.hidden = false;
      successPanel.focus();
      successPanel.scrollIntoView({
        behavior: matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "instant"
          : "smooth",
        block: "start",
      });
    } catch {
      showMessage(
        "Сервер не ответил. Заявка могла сохраниться. Уточните её наличие у администратора перед повторной отправкой.",
      );
    } finally {
      submitting = false;
      bookingForm.removeAttribute("aria-busy");
      for (const fieldset of bookingForm.querySelectorAll("fieldset"))
        fieldset.disabled = false;
      bookingForm.elements.consent.disabled = false;
      submitButton.disabled = !currentSlotValues.includes(timeInput.value);
      errorFocus?.focus();
    }
  });

  document.querySelector("#new-booking").addEventListener("click", async () => {
    bookingForm.reset();
    clearErrors();
    showMessage("", "");
    successPanel.hidden = true;
    bookingForm.hidden = false;
    await loadMasters();
    serviceSelect.focus();
  });
  loadMasters(initialMaster);
}
