(() => {
  "use strict";

  const tg = window.Telegram?.WebApp;
  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];
  const configuredApiBase = window.__BSUIR_API_BASE__ || document.querySelector('meta[name="bsuir-api-base"]')?.content || "";
  const apiBase = configuredApiBase.replace(/\/+$/, "") || (
  location.protocol === "file:"
    ? "http://127.0.0.1:8000"
    : "https://tg-student-backend-6zgh.onrender.com"
  );
  const state = { token: null, profile: null, hasAccount: false, registrationToken: null, view: "today", friends: null, selectedDate: localDate(), calendarMonth: null };
  const screens = ["authChoiceScreen", "registerScreen", "loginScreen", "verificationScreen", "confirmScreen", "dashboardScreen"];

  tg?.ready();
  tg?.expand();
  tg?.setHeaderColor?.("#943A02");
  tg?.setBackgroundColor?.("#F2F4F7");

  function show(screenId) {
    screens.forEach((screen) => document.getElementById(screen)?.classList.toggle("hidden", screen !== screenId));
  }

  function setConnection(active, label) {
    $("#connectionText").textContent = active ? (label || "Сессия активна") : "Ожидание Telegram";
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[char]));
  }

  let toastTimer;
  function toast(message) {
    const node = $("#toast");
    if (!node) return;
    node.textContent = message;
    node.classList.add("is-visible");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => node.classList.remove("is-visible"), 3200);
  }

  function formatDate(value) {
    return new Intl.DateTimeFormat("ru-RU", { weekday: "long", day: "numeric", month: "long" }).format(new Date(`${value}T12:00:00`));
  }

  function localDate(offset = 0) {
    const value = new Date();
    value.setDate(value.getDate() + offset);
    return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
  }

  function dateObject(value) {
    const [year, month, day] = String(value).split("-").map(Number);
    return new Date(year, month - 1, day);
  }

  function monthKey(value) {
    const date = dateObject(value);
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
  }

  function monthLabel(value) {
    return new Intl.DateTimeFormat("ru-RU", { month: "long", year: "numeric" }).format(dateObject(`${value}-01`));
  }

  function dateKey(year, month, day) {
    return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
  }

  function renderDatePicker(selectedDate = state.selectedDate || localDate()) {
    const selected = selectedDate;
    state.selectedDate = selected;
    state.calendarMonth = state.calendarMonth || monthKey(selected);
    const [year, month] = state.calendarMonth.split("-").map(Number);
    const firstDay = new Date(year, month - 1, 1);
    const leadingDays = (firstDay.getDay() + 6) % 7;
    const daysInMonth = new Date(year, month, 0).getDate();
    const cellCount = Math.ceil((leadingDays + daysInMonth) / 7) * 7;
    const today = localDate();
    const cells = Array.from({ length: cellCount }, (_, index) => {
      const day = index - leadingDays + 1;
      if (day < 1 || day > daysInMonth) return '<span class="calendar-cell calendar-cell-empty" aria-hidden="true"></span>';
      const value = dateKey(year, month, day);
      const classes = ["calendar-cell", value === selected ? "is-selected" : "", value === today ? "is-today" : ""].filter(Boolean).join(" ");
      return `<button class="${classes}" data-schedule-date="${value}" type="button">${day}</button>`;
    }).join("");
    const readableDate = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", year: "numeric" }).format(dateObject(selected));
    $("#scheduleDateControl").innerHTML = `<div class="schedule-date-picker"><button id="scheduleDateToggle" class="schedule-date-toggle" type="button" aria-expanded="false" aria-controls="scheduleCalendar"><span class="schedule-date-icon" aria-hidden="true">▣</span><span><small>Выбранная дата</small><strong>${escapeHtml(readableDate)}</strong></span><b aria-hidden="true">⌄</b></button><div id="scheduleCalendar" class="calendar-popover hidden" role="dialog" aria-label="Выбор даты"><div class="calendar-header"><button class="calendar-nav" data-calendar-month="previous" type="button" aria-label="Предыдущий месяц">‹</button><strong>${escapeHtml(monthLabel(state.calendarMonth))}</strong><button class="calendar-nav" data-calendar-month="next" type="button" aria-label="Следующий месяц">›</button></div><div class="calendar-weekdays">${["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"].map((day) => `<span>${day}</span>`).join("")}</div><div class="calendar-grid">${cells}</div><button class="calendar-today" data-calendar-today type="button">Сегодня</button></div></div>`;
    $("#scheduleDateToggle").addEventListener("click", () => {
      const toggle = $("#scheduleDateToggle");
      const calendar = $("#scheduleCalendar");
      const open = calendar.classList.toggle("hidden");
      toggle.setAttribute("aria-expanded", String(!open));
    });
    $$('[data-calendar-month]').forEach((button) => button.addEventListener("click", () => {
      const visible = dateObject(`${state.calendarMonth}-01`);
      visible.setMonth(visible.getMonth() + (button.dataset.calendarMonth === "next" ? 1 : -1));
      state.calendarMonth = monthKey(`${visible.getFullYear()}-${String(visible.getMonth() + 1).padStart(2, "0")}-01`);
      renderDatePicker(selected);
      $("#scheduleCalendar").classList.remove("hidden");
      $("#scheduleDateToggle").setAttribute("aria-expanded", "true");
    }));
    $$('[data-schedule-date]').forEach((button) => button.addEventListener("click", () => loadScheduleDate(button.dataset.scheduleDate)));
    $("[data-calendar-today]").addEventListener("click", () => loadScheduleDate(today));
  }

  async function loadScheduleDate(value) {
    state.selectedDate = value;
    state.calendarMonth = monthKey(value);
    await loadView("date");
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
    const localTestUser = new URLSearchParams(location.search).get("testUser");
    const localInitData = localTestUser === "2" || localTestUser === "3" ? `dev-test-init-data-${localTestUser}` : "dev-test-init-data";
    const initData = tg?.initData || ((location.hostname === "localhost" || location.hostname === "127.0.0.1") ? localInitData : "");
    if (!initData) throw new Error("Откройте приложение кнопкой из диалога с ботом Telegram.");
    const data = await api("/api/auth/telegram", { method: "POST", body: JSON.stringify({ initData }) });
    state.token = data.accessToken;
    state.hasAccount = Boolean(data.hasAccount);
    setConnection(true, "Telegram подтверждён");
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
      <div class="profile-actions"><button id="logoutButton" class="logout-button" type="button">Выйти</button><button id="logoutAllButton" class="logout-button" type="button">Выйти на всех устройствах</button></div></div>`;
    $("#logoutButton").addEventListener("click", () => logout(false));
    $("#logoutAllButton").addEventListener("click", () => logout(true));
  }

  function renderFriendProfile(profile) {
    $("#profileView").innerHTML = `<div class="profile-panel friend-profile-panel"><button id="friendProfileBack" class="back-button" type="button">← К друзьям</button><div class="section-label">Профиль друга</div><h2>${escapeHtml(profile.name)}</h2>
      <div class="profile-fields"><div class="data-cell"><small>Факультет</small><strong>${escapeHtml(profile.faculty_name || "Не указан")}</strong></div>
      <div class="data-cell"><small>Специальность</small><strong>${escapeHtml(profile.speciality_name || "Не указана")}</strong></div>
      <div class="data-cell"><small>Курс · группа</small><strong>${escapeHtml(profile.course || "Не указан")} · ${escapeHtml(profile.group_number || "Не указана")}</strong></div>
      <div class="data-cell"><small>Подгруппа</small><strong>${escapeHtml(profile.subgroup || "Не определена")}</strong></div></div></div>`;
    $("#friendProfileBack").addEventListener("click", () => loadView("friends"));
  }

  function friendProfileButton(student) {
    return `<button class="friend-action secondary" data-view-friend="${student.userId}" type="button">Профиль</button>`;
  }

  function studentCard(student, action = "") {
    const name = escapeHtml(student.name || "Студент");
    const meta = [student.faculty_name || student.faculty, student.group_number || student.group].filter(Boolean).map(escapeHtml).join(" · ");
    const study = [student.speciality_name || student.speciality, student.course ? `${student.course} курс` : ""].filter(Boolean).map(escapeHtml).join(" · ");
    return `<article class="friend-card"><span class="friend-avatar">${escapeHtml((student.name || "С").slice(0, 1))}</span><div class="friend-main"><strong>${name}</strong><small>${meta || "Данные профиля"}</small>${study ? `<small>${study}</small>` : ""}</div>${action}</article>`;
  }

  function renderFriends(data = state.friends || { friends: [], incoming: [], outgoing: [] }) {
    state.friends = data;
    const friends = data.friends || [];
    const incoming = data.incoming || [];
    const outgoing = data.outgoing || [];
    $("#friendsView").innerHTML = `<div class="friends-head"><div><div class="section-label">Сообщество студентов</div><h2>Друзья</h2><p class="muted">Находите одногруппников и знакомых по учебе.</p></div><button id="friendsRefreshButton" class="refresh-button" type="button" aria-label="Обновить друзей">↻</button></div>
      <div class="friends-section"><div class="friends-section-head"><h3>Мои друзья <span>${friends.length}</span></h3></div>${friends.length ? `<div class="friends-list">${friends.map((friend) => studentCard(friend, `<span class="friend-actions">${friendProfileButton(friend)}<button class="friend-action secondary" data-remove-friend="${friend.userId}" type="button">Удалить</button></span>`)).join("")}</div>` : '<div class="empty-state friends-empty">Пока нет друзей. Найдите первого студента ниже.</div>'}</div>
      ${incoming.length ? `<div class="friends-section"><div class="friends-section-head"><h3>Входящие заявки <span>${incoming.length}</span></h3></div><div class="friends-list">${incoming.map((request) => studentCard(request, `<span class="friend-actions"><button class="friend-action accept" data-accept-request="${request.requestId}" type="button">Принять</button><button class="friend-action secondary" data-reject-request="${request.requestId}" type="button">Отклонить</button></span>`)).join("")}</div></div>` : ""}
      ${outgoing.length ? `<div class="friends-section"><div class="friends-section-head"><h3>Отправленные заявки <span>${outgoing.length}</span></h3></div><div class="friends-list">${outgoing.map((request) => studentCard(request, `<button class="friend-action secondary" data-cancel-request="${request.requestId}" type="button">Отменить</button>`)).join("")}</div></div>` : ""}
      <div class="friends-section friends-search-section"><div class="friends-section-head"><div><h3>Добавить в друзья</h3><p class="form-hint">Введите студенческий номер или ФИО.</p></div></div><form id="friendSearchForm" class="friend-search"><div class="input-wrap friend-search-input"><span>⌕</span><input id="friendSearchInput" name="q" autocomplete="off" placeholder="Номер или фамилия" required /><button type="submit">Найти <b>↗</b></button></div><p id="friendSearchError" class="error-message" role="alert"></p></form><div id="friendSearchResults" class="friends-list"></div></div>`;
    $("#friendsRefreshButton").addEventListener("click", () => loadFriends());
    $("#friendSearchForm").addEventListener("submit", searchFriends);
    $$('[data-view-friend]').forEach((button) => button.addEventListener("click", () => loadFriendProfile(Number(button.dataset.viewFriend))));
    $$("[data-remove-friend]").forEach((button) => button.addEventListener("click", () => removeFriend(button.dataset.removeFriend)));
    $$("[data-accept-request]").forEach((button) => button.addEventListener("click", () => respondToFriendRequest(button.dataset.acceptRequest, "accept")));
    $$("[data-reject-request]").forEach((button) => button.addEventListener("click", () => respondToFriendRequest(button.dataset.rejectRequest, "reject")));
    $$("[data-cancel-request]").forEach((button) => button.addEventListener("click", () => respondToFriendRequest(button.dataset.cancelRequest, "cancel")));
  }

  async function loadFriendProfile(studentId) {
    if (!state.profile) return;
    setViewChrome("friend-profile");
    $("#profileView").innerHTML = '<div class="empty-state">Загружаем профиль друга…</div>';
    try {
      const data = await api(`/api/app/friends/${studentId}/profile`);
      renderFriendProfile(data.profile);
    } catch (error) {
      $("#profileView").innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    }
  }

  async function loadFriends() {
    $("#friendsView").innerHTML = '<div class="empty-state">Загружаем список друзей…</div>';
    try {
      renderFriends(await api("/api/app/friends"));
    } catch (error) {
      $("#friendsView").innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    }
  }

  async function searchFriends(event) {
    event.preventDefault();
    const query = $("#friendSearchInput").value.trim();
    const errorNode = $("#friendSearchError");
    const results = $("#friendSearchResults");
    errorNode.textContent = "";
    results.innerHTML = '<div class="search-loading">Ищем студента…</div>';
    try {
      const data = await api(`/api/app/friends/search?q=${encodeURIComponent(query)}`);
      if (!data.items?.length) {
        results.innerHTML = '<div class="empty-state friends-empty">Студенты не найдены. Проверьте номер или написание ФИО.</div>';
        return;
      }
      results.innerHTML = data.items.map((student) => {
        const action = student.relationship === "accepted" ? friendProfileButton(student) : student.relationship === "outgoing" ? '<span class="relationship-label">Заявка отправлена</span>' : student.relationship === "incoming" ? `<button class="friend-action accept" data-accept-request="${student.requestId}" type="button">Принять</button>` : `<button class="friend-action accept" data-add-friend="${student.userId}" type="button">Добавить</button>`;
        return studentCard(student, action);
      }).join("");
      $$('[data-add-friend]').forEach((button) => button.addEventListener("click", () => addFriend(button.dataset.addFriend)));
      $$('[data-accept-request]').forEach((button) => button.addEventListener("click", () => respondToFriendRequest(button.dataset.acceptRequest, "accept")));
      $$('[data-view-friend]').forEach((button) => button.addEventListener("click", () => loadFriendProfile(Number(button.dataset.viewFriend))));
    } catch (error) {
      results.innerHTML = "";
      errorNode.textContent = error.message;
    }
  }

  async function addFriend(userId) {
    try {
      await api("/api/app/friends/requests", { method: "POST", body: JSON.stringify({ userId: Number(userId) }) });
      toast("Заявка в друзья отправлена");
      await loadFriends();
    } catch (error) { toast(error.message); }
  }

  async function respondToFriendRequest(requestId, action) {
    const path = action === "accept" ? `/api/app/friends/requests/${requestId}/accept` : `/api/app/friends/requests/${requestId}`;
    try {
      await api(path, { method: action === "accept" ? "POST" : "DELETE" });
      toast(action === "accept" ? "Теперь вы друзья" : "Заявка удалена");
      await loadFriends();
    } catch (error) { toast(error.message); }
  }

  async function removeFriend(userId) {
    try {
      await api(`/api/app/friends/${userId}`, { method: "DELETE" });
      toast("Студент удалён из друзей");
      await loadFriends();
    } catch (error) { toast(error.message); }
  }

  function lessonCard(item) {
    const tags = [item.lessonType, item.subgroup ? `Подгруппа ${item.subgroup}` : "", item.changed ? "Изменение расписания" : ""].filter(Boolean).map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("");
    return `<article class="lesson-card"><div class="lesson-time">${escapeHtml(item.startTime)}<span>–</span>${escapeHtml(item.endTime)}</div><div class="lesson-main"><h3>${escapeHtml(item.subject)}</h3><p>Аудитория: ${escapeHtml(item.room || "не указана")}</p><p>Преподаватель: ${escapeHtml(item.teacher || "не указан")}</p><div class="lesson-tags">${tags}</div></div></article>`;
  }

  function renderSchedule(data) {
    const items = data.items || [];
    state.selectedDate = data.date;
    state.calendarMonth = monthKey(data.date);
    renderDatePicker(data.date);
    $("#scheduleView").innerHTML = `${data.stale ? `<div class="cache-banner">${escapeHtml(data.message)}</div>` : ""}<div class="day-heading"><div><div class="section-label">Расписание</div><h2>${formatDate(data.date)}</h2></div><span>${data.weekNumber ? `Учебная неделя ${data.weekNumber}` : ""}</span></div>${items.length ? `<div class="schedule-list">${items.map(lessonCard).join("")}</div>` : '<div class="empty-state">На этот день занятий нет.</div>'}`;
  }

  function setViewChrome(view) {
    state.view = view;
    $$(".tab").forEach((tab) => tab.classList.toggle("is-active", tab.dataset.view === view));
    $$(".menu-item").forEach((item) => item.classList.toggle("is-active", item.dataset.menuView === (view === "friend-profile" ? "friends" : view)));
    const isStandaloneView = ["profile", "friends", "friend-profile"].includes(view);
    $(".dashboard-head").classList.toggle("hidden", isStandaloneView);
    $("#profileSummary").classList.toggle("hidden", isStandaloneView);
    $(".view-tabs").classList.toggle("hidden", isStandaloneView);
    $("#scheduleDateControl").classList.toggle("hidden", isStandaloneView);
    $("#scheduleView").classList.toggle("hidden", isStandaloneView);
    $("#profileView").classList.toggle("hidden", !["profile", "friend-profile"].includes(view));
    $("#friendsView").classList.toggle("hidden", view !== "friends");
  }

  async function loadView(view) {
    if ((view === "profile" || view === "friends" || view === "friend-profile") && !state.profile) {
      toggleMenu(false);
      show("authChoiceScreen");
      return;
    }
    if (view === "today") state.selectedDate = localDate();
    if (view === "tomorrow") state.selectedDate = localDate(1);
    if (view === "today" || view === "tomorrow") state.calendarMonth = monthKey(state.selectedDate);
    setViewChrome(view);
    if (view === "profile") {
      renderProfile();
      return;
    }
    if (view === "friends") {
      await loadFriends();
      return;
    }
    if (view === "friend-profile") return;
    renderDatePicker(state.selectedDate);
    $("#scheduleView").innerHTML = '<div class="empty-state">Загружаем расписание…</div>';
    try {
      if (view === "week") {
        const data = await api(`/api/app/schedule/week?date=${state.selectedDate}`);
        $("#scheduleView").innerHTML = data.days.map((day) => `<div class="week-day"><div class="day-heading"><h2>${formatDate(day.date)}</h2></div>${day.items.length ? `<div class="schedule-list">${day.items.map(lessonCard).join("")}</div>` : '<div class="empty-state">Нет занятий</div>'}</div>`).join("");
      } else if (view === "exams") {
        renderSchedule({ date: localDate(), items: (await api("/api/app/exams")).items, weekNumber: null });
      } else {
        const endpoint = view === "today" ? "/api/app/schedule/today" : view === "tomorrow" ? `/api/app/schedule?date=${localDate(1)}` : `/api/app/schedule?date=${state.selectedDate}`;
        renderSchedule(await api(endpoint));
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

  async function prepareAuthChoice() {
    state.token = null;
    state.profile = null;
    state.hasAccount = false;
    state.registrationToken = null;
    try {
      await authenticate();
    } catch {
      setConnection(false);
    }
    show("authChoiceScreen");
  }

  async function logout(allDevices) {
    try { await api("/api/auth/logout", { method: "POST", body: JSON.stringify({ allDevices }) }); } catch { /* local cleanup still prevents further use */ }
    await prepareAuthChoice();
  }

  function toggleMenu(open) {
    const shouldOpen = typeof open === "boolean" ? open : !$("#appMenu").classList.contains("is-open");
    $("#appMenu").classList.toggle("is-open", shouldOpen);
    $("#menuBackdrop").classList.toggle("hidden", !shouldOpen);
    $("#menuButton").setAttribute("aria-expanded", String(shouldOpen));
    $("#appMenu").setAttribute("aria-hidden", String(!shouldOpen));
    document.body.classList.toggle("menu-open", shouldOpen);
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
  $("#menuButton").addEventListener("click", () => toggleMenu());
  $("#menuCloseButton").addEventListener("click", () => toggleMenu(false));
  $("#menuBackdrop").addEventListener("click", () => toggleMenu(false));
  $$("[data-menu-view]").forEach((item) => item.addEventListener("click", () => { toggleMenu(false); loadView(item.dataset.menuView); }));
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") toggleMenu(false); });
  window.addEventListener("load", bootstrap);
})();
