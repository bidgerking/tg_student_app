(() => {
  "use strict";

  const tg = window.Telegram?.WebApp;
  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];
  const configuredApiBase = window.__BSUIR_API_BASE__ || document.querySelector('meta[name="bsuir-api-base"]')?.content || "";
  const apiBase = configuredApiBase.replace(/\/$/, "") || (location.protocol === "file:" ? "http://127.0.0.1:8000" : "");
  const state = { token: null, profile: null, verificationToken: null, view: "today" };
  const screens = ["verificationScreen", "confirmScreen", "dashboardScreen"];

  tg?.ready();
  tg?.expand();
  tg?.setHeaderColor?.("#003366");
  tg?.setBackgroundColor?.("#F2F4F7");

  function show(screenId) {
    screens.forEach((screen) => document.getElementById(screen).classList.toggle("hidden", screen !== screenId));
  }

  function setConnection(active) {
    $("#connectionText").textContent = active ? "Сессия активна" : "Ожидание Telegram";
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[char]));
  }

  function formatDate(value) {
    return new Intl.DateTimeFormat("ru-RU", { weekday: "long", day: "numeric", month: "long" }).format(new Date(`${value}T12:00:00`));
  }

  function localDate(offset = 0) {
    const date = new Date();
    date.setDate(date.getDate() + offset);
    const month = String(date.getMonth() + 1).padStart(2, "0");
    return `${date.getFullYear()}-${month}-${String(date.getDate()).padStart(2, "0")}`;
  }

  async function api(path, options = {}) {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    if (state.token) headers.Authorization = `Bearer ${state.token}`;
    let response;
    try {
      response = await fetch(`${apiBase}${path}`, { ...options, headers });
    } catch {
      throw new Error("Не удаётся подключиться к серверу. Проверьте backend и HTTPS-туннель.");
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.detail || data.error || `Сервер вернул HTTP ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return data;
  }

  async function authenticate() {
    const initData = tg?.initData || ((location.hostname === "localhost" || location.hostname === "127.0.0.1") ? "dev-test-init-data" : "");
    if (!initData) throw new Error("Откройте приложение кнопкой из диалога с ботом Telegram.");
    const data = await api("/api/app/telegram/auth", {
      method: "POST",
      body: JSON.stringify({ initData }),
    });
    state.token = data.accessToken;
    setConnection(true);
    return data.profile;
  }

  function renderCandidate(student) {
    $("#candidateCard").innerHTML = `
      <h2>${escapeHtml(student.name)}</h2>
      <div class="candidate-grid">
        <div class="data-cell"><small>Факультет</small><strong>${escapeHtml(student.faculty)}</strong></div>
        <div class="data-cell"><small>Специальность</small><strong>${escapeHtml(student.speciality)}</strong></div>
        <div class="data-cell"><small>Курс · группа</small><strong>${escapeHtml(student.course)} · ${escapeHtml(student.group)}</strong></div>
        <div class="data-cell"><small>Подгруппа</small><strong>${escapeHtml(student.subgroup || "Не определена")}</strong></div>
      </div>`;
  }

  function renderProfileSummary(profile) {
    const firstName = (profile.name || "студент").split(" ")[1] || (profile.name || "студент").split(" ")[0];
    $("#studentFirstName").textContent = firstName;
    $("#dashboardDate").textContent = new Intl.DateTimeFormat("ru-RU", { dateStyle: "full" }).format(new Date());
    $("#profileSummary").innerHTML = `
      <div class="summary-main"><span class="summary-avatar">${escapeHtml((profile.name || "С").slice(0, 1))}</span>
      <span class="summary-name"><strong>${escapeHtml(profile.name)}</strong><small>${escapeHtml(profile.faculty_name)} · группа ${escapeHtml(profile.group_number)}</small></span></div>
      <span class="summary-course">${escapeHtml(profile.speciality_name)}<br />${escapeHtml(profile.course)} курс</span>`;
  }

  function lessonCard(item) {
    const tags = [item.lessonType, item.subgroup ? `Подгруппа ${item.subgroup}` : "", item.changed ? "Изменение расписания" : ""]
      .filter(Boolean)
      .map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`)
      .join("");
    return `<article class="lesson-card"><div class="lesson-time">${escapeHtml(item.startTime)}<span>–</span>${escapeHtml(item.endTime)}</div>
      <div class="lesson-main"><h3>${escapeHtml(item.subject)}</h3><p>Аудитория: ${escapeHtml(item.room || "не указана")}</p>
      <p>Преподаватель: ${escapeHtml(item.teacher || "не указан")}</p><div class="lesson-tags">${tags}</div></div></article>`;
  }

  function renderSchedule(data) {
    const items = data.items || [];
    $("#scheduleView").innerHTML = `<div class="day-heading"><div><div class="section-label">Расписание</div><h2>${formatDate(data.date)}</h2></div><span>${data.weekNumber ? `Учебная неделя ${data.weekNumber}` : ""}</span></div>${items.length ? `<div class="schedule-list">${items.map(lessonCard).join("")}</div>` : '<div class="empty-state">На этот день занятий нет.</div>'}`;
  }

  function renderProfile() {
    const profile = state.profile;
    $("#profileView").innerHTML = `<div class="profile-panel"><div class="section-label">Подтверждённые данные</div><h2>${escapeHtml(profile.name)}</h2>
      <div class="profile-fields"><div class="data-cell"><small>Факультет</small><strong>${escapeHtml(profile.faculty_name)}</strong></div>
      <div class="data-cell"><small>Специальность</small><strong>${escapeHtml(profile.speciality_name)}</strong></div>
      <div class="data-cell"><small>Курс · группа</small><strong>${escapeHtml(profile.course)} · ${escapeHtml(profile.group_number)}</strong></div>
      <div class="data-cell"><small>Подгруппа</small><strong>${escapeHtml(profile.subgroup || "Не определена")}</strong></div></div></div>`;
  }

  async function loadView(view) {
    state.view = view;
    $$(".tab").forEach((tab) => tab.classList.toggle("is-active", tab.dataset.view === view));
    if (view === "profile") {
      $("#scheduleView").classList.add("hidden");
      $("#profileView").classList.remove("hidden");
      renderProfile();
      return;
    }
    $("#profileView").classList.add("hidden");
    $("#scheduleView").classList.remove("hidden");
    $("#scheduleView").innerHTML = '<div class="empty-state">Загружаем расписание…</div>';
    try {
      if (view === "week") {
        const data = await api("/api/app/schedule/week");
        $("#scheduleView").innerHTML = data.days.map((day) => `<div class="week-day"><div class="day-heading"><h2>${formatDate(day.date)}</h2></div>${day.items.length ? `<div class="schedule-list">${day.items.map(lessonCard).join("")}</div>` : '<div class="empty-state">Нет занятий</div>'}</div>`).join("");
      } else if (view === "exams") {
        const data = await api("/api/app/exams");
        renderSchedule({ date: localDate(), items: data.items, weekNumber: null });
      } else {
        renderSchedule(await api(view === "today" ? "/api/app/schedule/today" : `/api/app/schedule?date=${localDate(1)}`));
      }
    } catch (error) {
      $("#scheduleView").innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    }
  }

  async function bootstrap() {
    try {
      const profileFromAuth = await authenticate();
      if (profileFromAuth) {
        state.profile = profileFromAuth;
      } else {
        try {
          state.profile = (await api("/api/app/student/profile")).profile;
        } catch (error) {
          if (error.status !== 404) throw error;
        }
      }
      if (!state.profile) {
        show("verificationScreen");
        return;
      }
      renderProfileSummary(state.profile);
      show("dashboardScreen");
      await loadView("today");
    } catch (error) {
      state.token = null;
      setConnection(false);
      $("#verifyError").textContent = error.message;
      show("verificationScreen");
    }
  }

  $("#verifyForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = $("#verifyButton");
    $("#verifyError").textContent = "";
    button.disabled = true;
    try {
      const data = await api("/api/app/student/verify", { method: "POST", body: JSON.stringify({ personalNumber: $("#personalNumber").value.trim() }) });
      if (!data.verified) throw new Error(data.error || "Номер не найден.");
      state.verificationToken = data.verificationToken;
      renderCandidate(data.student);
      show("confirmScreen");
    } catch (error) {
      $("#verifyError").textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });

  $("#confirmButton").addEventListener("click", async () => {
    try {
      state.profile = (await api("/api/app/student/confirm", { method: "POST", body: JSON.stringify({ verificationToken: state.verificationToken }) })).profile;
      renderProfileSummary(state.profile);
      show("dashboardScreen");
      await loadView("today");
    } catch (error) {
      $("#verifyError").textContent = error.message;
      show("verificationScreen");
    }
  });

  $$(".back-button").forEach((button) => button.addEventListener("click", () => show(button.dataset.screen)));
  $$(".tab").forEach((tab) => tab.addEventListener("click", () => loadView(tab.dataset.view)));
  $("#refreshButton").addEventListener("click", () => loadView(state.view));
  $("#profileTopButton").addEventListener("click", () => state.profile && loadView("profile"));
  window.addEventListener("load", bootstrap);
})();
