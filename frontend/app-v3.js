(() => {
  "use strict";

  const tg = window.Telegram?.WebApp;
  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];
  const configuredApiBase = window.__BSUIR_API_BASE__ || document.querySelector('meta[name="bsuir-api-base"]')?.content || "";
  const apiBase = configuredApiBase.replace(/\/$/, "") || (location.protocol === "file:" ? "http://127.0.0.1:8000" : "");
  const state = { token: null, profile: null, hasAccount: false, registrationToken: null, view: "today" };
  const screens = ["authChoiceScreen", "registerScreen", "loginScreen", "verificationScreen", "confirmScreen", "dashboardScreen"];

  tg?.ready();
  tg?.expand();
  tg?.setHeaderColor?.("#003366");
  tg?.setBackgroundColor?.("#F2F4F7");

  function show(screenId) {
    screens.forEach((screen) => document.getElementById(screen)?.classList.toggle("hidden", screen !== screenId));
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
    const value = new Date();
    value.setDate(value.getDate() + offset);
    return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
  }

  async function api(path, options = {}) {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    if (state.token) headers.Authorization = `Bearer ${state.token}`;
    let response;
    try {
      response = await fetch(`${apiBase}${path}`, { ...options, headers, credentials: "include" });
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
    const data = await api("/api/auth/telegram", { method: "POST", body: JSON.stringify({ initData }) });
    state.token = data.accessToken;
    state.hasAccount = Boolean(data.hasAccount);
    setConnection(true);
    return data.profile;
  }

  function renderCandidate(student) {
    $("#candidateCard").innerHTML = `<h2>${escapeHtml(student.name)}</h2><div class="candidate-grid">
      <div class="data-cell"><small>Факультет</small><strong>${escapeHtml(student.faculty)}</strong></div>
      <div class="data-cell"><small>Специальность</small><strong>${escapeHtml(student.speciality)}</strong></div>
      <div class="data-cell"><small>Курс · группа</small><strong>${escapeHtml(student.course)} · ${escapeHtml(student.group)}</strong></div>
      <div class="data-cell"><small>Подгруппа</small><strong>${escapeHtml(student.subgroup || "Не определена")}</strong></div></div>`;
  }

  function renderProfileSummary(profile) {
    const name = profile.name || "студент";
    $("#studentFirstName").textContent = name.split(" ")[1] || name.split(" ")[0];
    $("#dashboardDate").textContent = new Intl.DateTimeFormat("ru-RU", { dateStyle: "full" }).format(new Date());
    $("#profileSummary").innerHTML = `<div class="summary-main"><span class="summary-avatar">${escapeHtml(name.slice(0, 1))}</span>
      <span class="summary-name"><strong>${escapeHtml(profile.name)}</strong><small>${escapeHtml(profile.faculty_name)} · группа ${escapeHtml(profile.group_number)}</small></span></div>
      <span class="summary-course">${escapeHtml(profile.speciality_name)}<br />${escapeHtml(profile.course)} курс</span>`;
  }

  function renderProfile() {
    const profile = state.profile;
    $("#profileView").innerHTML = `<div class="profile-panel"><div class="section-label">Профиль аккаунта</div><h2>${escapeHtml(profile.name)}</h2>
      <div class="profile-fields"><div class="data-cell"><small>Факультет</small><strong>${escapeHtml(profile.faculty_name)}</strong></div>
      <div class="data-cell"><small>Специальность</small><strong>${escapeHtml(profile.speciality_name)}</strong></div>
      <div class="data-cell"><small>Курс · группа</small><strong>${escapeHtml(profile.course)} · ${escapeHtml(profile.group_number)}</strong></div>
      <div class="data-cell"><small>Подгруппа</small><strong>${escapeHtml(profile.subgroup || "Не определена")}</strong></div></div>
      <div class="profile-actions"><button id="logoutButton" class="danger-button" type="button">Выйти</button><button id="logoutAllButton" class="danger-button" type="button">Выйти на всех устройствах</button><button id="deleteAccountButton" class="danger-button" type="button">Удалить аккаунт</button></div>
      <form id="passwordChangeForm" class="password-change-form"><strong>Изменить пароль</strong><label>Текущий пароль<input id="currentPassword" type="password" autocomplete="current-password" required /></label><label>Новый пароль<input id="newPassword" type="password" autocomplete="new-password" required /></label><label>Повтор нового пароля<input id="newPasswordConfirmation" type="password" autocomplete="new-password" required /></label><button class="primary-button" type="submit">Сохранить пароль</button><p id="passwordChangeError" class="error-message"></p></form></div>`;
    $("#logoutButton").addEventListener("click", () => logout(false));
    $("#logoutAllButton").addEventListener("click", () => logout(true));
    $("#deleteAccountButton").addEventListener("click", () => deleteAccount());
    $("#passwordChangeForm").addEventListener("submit", changePassword);
  }

  function lessonCard(item) {
    const tags = [item.lessonType, item.subgroup ? `Подгруппа ${item.subgroup}` : "", item.changed ? "Изменение расписания" : ""].filter(Boolean).map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("");
    return `<article class="lesson-card"><div class="lesson-time">${escapeHtml(item.startTime)}<span>–</span>${escapeHtml(item.endTime)}</div><div class="lesson-main"><h3>${escapeHtml(item.subject)}</h3><p>Аудитория: ${escapeHtml(item.room || "не указана")}</p><p>Преподаватель: ${escapeHtml(item.teacher || "не указан")}</p><div class="lesson-tags">${tags}</div></div></article>`;
  }

  function renderSchedule(data) {
    const items = data.items || [];
    $("#scheduleView").innerHTML = `${data.stale ? `<div class="cache-banner">${escapeHtml(data.message)}</div>` : ""}<div class="day-heading"><div><div class="section-label">Расписание</div><h2>${formatDate(data.date)}</h2></div><span>${data.weekNumber ? `Учебная неделя ${data.weekNumber}` : ""}</span></div>${items.length ? `<div class="schedule-list">${items.map(lessonCard).join("")}</div>` : '<div class="empty-state">На этот день занятий нет.</div>'}`;
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
        renderSchedule({ date: localDate(), items: (await api("/api/app/exams")).items, weekNumber: null });
      } else {
        renderSchedule(await api(view === "today" ? "/api/app/schedule/today" : `/api/app/schedule?date=${localDate(1)}`));
      }
    } catch (error) {
      $("#scheduleView").innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    }
  }

  async function bootstrap() {
    try {
      const profile = await authenticate();
      if (profile && state.hasAccount) {
        state.profile = profile;
        renderProfileSummary(profile);
        show("dashboardScreen");
        await loadView("today");
      } else {
        show("authChoiceScreen");
      }
    } catch (error) {
      state.token = null;
      setConnection(false);
      $("#authError").textContent = error.message;
      show("authChoiceScreen");
    }
  }

  async function register(event) {
    event.preventDefault();
    $("#registerError").textContent = "";
    try {
      const data = await api("/api/auth/register", { method: "POST", body: JSON.stringify({ personalNumber: $("#registerPersonalNumber").value.trim(), password: $("#registerPassword").value, passwordConfirmation: $("#registerPasswordConfirmation").value }) });
      state.registrationToken = data.registrationToken;
      renderCandidate(data.student);
      show("confirmScreen");
    } catch (error) {
      $("#registerError").textContent = error.message;
    }
  }

  async function confirmRegistration() {
    try {
      const data = await api("/api/auth/register/confirm", { method: "POST", body: JSON.stringify({ verificationToken: state.registrationToken }) });
      state.profile = data.profile;
      state.hasAccount = true;
      renderProfileSummary(state.profile);
      show("dashboardScreen");
      await loadView("today");
    } catch (error) {
      $("#authError").textContent = error.message;
      show("authChoiceScreen");
    }
  }

  async function login(event) {
    event.preventDefault();
    $("#loginError").textContent = "";
    try {
      const data = await api("/api/auth/login", { method: "POST", body: JSON.stringify({ personalNumber: $("#loginPersonalNumber").value.trim(), password: $("#loginPassword").value, rememberMe: $("#rememberMe").checked }) });
      state.token = data.accessToken;
      state.profile = data.profile;
      state.hasAccount = true;
      setConnection(true);
      renderProfileSummary(state.profile);
      show("dashboardScreen");
      await loadView("today");
    } catch (error) {
      $("#loginError").textContent = error.message;
    }
  }

  async function logout(allDevices) {
    try { await api("/api/auth/logout", { method: "POST", body: JSON.stringify({ allDevices }) }); } catch { /* local cleanup still prevents further use */ }
    state.token = null;
    state.profile = null;
    state.hasAccount = false;
    setConnection(false);
    show("authChoiceScreen");
  }

  async function deleteAccount() {
    if (!window.confirm("Удалить аккаунт и все связанные с ним сессии?")) return;
    try {
      await api("/api/account", { method: "DELETE" });
      state.token = null;
      state.profile = null;
      state.hasAccount = false;
      setConnection(false);
      show("authChoiceScreen");
    } catch (error) {
      window.alert(error.message);
    }
  }

  async function changePassword(event) {
    event.preventDefault();
    const errorNode = $("#passwordChangeError");
    try {
      const data = await api("/api/account/password/change", { method: "POST", body: JSON.stringify({ currentPassword: $("#currentPassword").value, newPassword: $("#newPassword").value, passwordConfirmation: $("#newPasswordConfirmation").value }) });
      state.token = data.accessToken;
      errorNode.textContent = "Пароль изменён";
      event.target.reset();
    } catch (error) {
      errorNode.textContent = error.message;
    }
  }

  $("#registerModeButton").addEventListener("click", () => show("registerScreen"));
  $("#loginModeButton").addEventListener("click", () => show("loginScreen"));
  $("#registerForm").addEventListener("submit", register);
  $("#loginForm").addEventListener("submit", login);
  $("#confirmButton").addEventListener("click", confirmRegistration);
  $$(".back-button").forEach((button) => button.addEventListener("click", () => show(button.dataset.screen === "verificationScreen" ? "authChoiceScreen" : button.dataset.screen)));
  $$(".tab").forEach((tab) => tab.addEventListener("click", () => loadView(tab.dataset.view)));
  $("#refreshButton").addEventListener("click", () => loadView(state.view));
  $("#profileTopButton").addEventListener("click", () => state.profile && loadView("profile"));
  window.addEventListener("load", bootstrap);
})();
