/* Чат: каркас экранов, unread badge и глобальный SSE (этап 6). */
(function (global) {
  "use strict";

  var streamHandle = null;
  var latestEventId = null;
  var roomsCache = [];
  var roomsById = {};
  var totalUnread = 0;
  var totalUnreadMentions = 0;
  var currentRoomId = null;
  var pendingMessageId = null;
  var entrySource = "home";
  var bound = false;
  var blobUrls = [];
  var listRequestId = 0;

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function chatAllowed() {
    var user = global.NogaRoles.getUser();
    return Boolean(
      user &&
        user.features &&
        user.features.chat &&
        global.NogaRoles.can("chat:read")
    );
  }

  function formatRoomTime(iso) {
    if (!iso) return "";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return "";
    var now = new Date();
    var sameDay =
      d.getFullYear() === now.getFullYear() &&
      d.getMonth() === now.getMonth() &&
      d.getDate() === now.getDate();
    if (sameDay && global.NogaDict.formatTime) {
      return global.NogaDict.formatTime(iso);
    }
    return global.NogaDict.formatDate(iso);
  }

  function releaseBlobs() {
    blobUrls.forEach(function (url) {
      try {
        global.URL.revokeObjectURL(url);
      } catch (e) {
        /* ignore */
      }
    });
    blobUrls = [];
  }

  function applyGate() {
    var bell = document.getElementById("bell");
    if (bell) bell.hidden = !chatAllowed();
  }

  function applyUnread(total, mentions) {
    totalUnread = Math.max(0, Number(total) || 0);
    if (mentions !== undefined && mentions !== null) {
      totalUnreadMentions = Math.max(0, Number(mentions) || 0);
    }
    var bell = document.getElementById("bell");
    var count = document.getElementById("bellCount");
    var hasUnread = totalUnread > 0;
    var hasMention = totalUnreadMentions > 0;
    if (bell) {
      bell.classList.toggle("has-alert", hasUnread || hasMention);
      bell.setAttribute(
        "aria-label",
        hasUnread ? "Чат, непрочитанных: " + totalUnread : "Чат"
      );
    }
    if (count) {
      if (hasUnread) {
        count.hidden = false;
        count.textContent = totalUnread > 99 ? "99+" : String(totalUnread);
        count.setAttribute("aria-hidden", "false");
      } else {
        count.hidden = true;
        count.textContent = "0";
        count.setAttribute("aria-hidden", "true");
      }
    }
  }

  function setLoading(visible) {
    var loading = document.getElementById("chatRoomsLoading");
    if (loading) loading.hidden = !visible;
  }

  function setRoomsEmpty(visible) {
    var empty = document.getElementById("chatRoomsEmpty");
    if (empty) empty.hidden = !visible;
  }

  function renderRoomCard(room) {
    /* Строка комнаты — паттерн em-oprow из design-system (список операций). */
    var btn = el("button", "em-oprow em-chat-room-row");
    btn.type = "button";
    btn.setAttribute("data-room-id", String(room.id));

    btn.appendChild(el("span", "em-oprow__id em-ellipsis", room.title || "Комната"));

    var side = el("span", "em-oprow__side");
    var last = room.last_message;
    if (last && last.created_at) {
      side.appendChild(el("span", "em-oprow__time em-num", formatRoomTime(last.created_at)));
    }
    if (room.unread_mentions > 0) {
      var mention = el("span", "em-status em-status--wait");
      mention.appendChild(el("span", "em-dot em-dot--live"));
      mention.appendChild(document.createTextNode("@"));
      mention.setAttribute("aria-label", "Есть упоминания");
      side.appendChild(mention);
    }
    if (room.unread_count > 0) {
      side.appendChild(
        el("span", "em-count em-num", room.unread_count > 99 ? "99+" : String(room.unread_count))
      );
    }
    btn.appendChild(side);

    var preview = "";
    if (last) {
      preview = last.author_name
        ? last.author_name + " · " + (last.preview || "")
        : last.preview || "";
    } else {
      preview = room.kind === "system" ? "Системная комната" : "Нет сообщений";
    }
    btn.appendChild(el("span", "em-oprow__meta", preview));

    btn.addEventListener("click", function () {
      openRoom(room.id);
    });
    return btn;
  }

  function renderRooms(rooms) {
    var list = document.getElementById("chatRoomsList");
    if (!list) return;
    list.innerHTML = "";
    roomsCache = rooms || [];
    roomsById = {};
    roomsCache.forEach(function (room) {
      roomsById[room.id] = room;
      list.appendChild(renderRoomCard(room));
    });
    setRoomsEmpty(!roomsCache.length);
    if (global.EmDS) global.EmDS.init(list);
  }

  function applyRoomsPayload(payload) {
    payload = payload || {};
    if (payload.latest_event_id !== null && payload.latest_event_id !== undefined) {
      latestEventId = payload.latest_event_id;
    }
    applyUnread(payload.total_unread, payload.total_unread_mentions);
    renderRooms(payload.rooms || []);
  }

  async function loadRooms() {
    if (!chatAllowed()) {
      setLoading(false);
      renderRooms([]);
      applyUnread(0, 0);
      return;
    }
    var req = ++listRequestId;
    setLoading(true);
    setRoomsEmpty(false);
    try {
      var payload = await global.NogaApi.chatRooms();
      if (req !== listRequestId) return;
      applyRoomsPayload(payload);
      ensureStream();
    } catch (err) {
      if (req !== listRequestId) return;
      renderRooms([]);
      if (global.NogaTelegram && global.NogaTelegram.notify) {
        global.NogaTelegram.notify((err && err.message) || "Не удалось загрузить чат");
      }
    } finally {
      if (req === listRequestId) setLoading(false);
    }
  }

  function stopStream() {
    if (streamHandle && streamHandle.abort) streamHandle.abort();
    streamHandle = null;
  }

  function ensureStream() {
    if (!chatAllowed()) {
      stopStream();
      return;
    }
    if (streamHandle) return;
    streamHandle = global.NogaApi.openChatStream({
      lastEventId: latestEventId,
      onEvent: function (envelope) {
        applyEvent(envelope);
      },
      onError: function () {
        /* backoff внутри openChatStream */
      },
    });
  }

  function bumpRoomUnread(roomId, mentionsDelta) {
    var room = roomsById[roomId];
    if (!room) return;
    room.unread_count = (Number(room.unread_count) || 0) + 1;
    totalUnread += 1;
    if (mentionsDelta) {
      room.unread_mentions = (Number(room.unread_mentions) || 0) + Number(mentionsDelta);
      totalUnreadMentions += Number(mentionsDelta);
    }
    applyUnread(totalUnread, totalUnreadMentions);
    var list = document.getElementById("chatRoomsList");
    if (list && !document.getElementById("viewChatRooms").hidden) {
      renderRooms(roomsCache);
    }
  }

  function updateRoomPreview(roomId, message) {
    var room = roomsById[roomId];
    if (!room || !message) return;
    room.last_message = {
      id: message.id,
      author_name: (message.author && message.author.display_name) || message.author_name || "",
      preview: message.preview || "",
      has_attachments: Boolean(message.attachments && message.attachments.length),
      created_at: message.created_at,
    };
    var list = document.getElementById("chatRoomsList");
    if (list && !document.getElementById("viewChatRooms").hidden) {
      renderRooms(roomsCache);
    }
  }

  function applyEvent(envelope) {
    if (!envelope || !envelope.type) return;
    if (envelope.event_id !== null && envelope.event_id !== undefined) {
      latestEventId = envelope.event_id;
    }

    if (envelope.type === "stream.reset") {
      loadRooms();
      return;
    }

    if (envelope.type === "access.revoked") {
      release();
      applyGate();
      applyUnread(0, 0);
      if (global.NogaTelegram && global.NogaTelegram.notify) {
        global.NogaTelegram.notify("Доступ к чату закрыт");
      }
      var roomsView = document.getElementById("viewChatRooms");
      var roomView = document.getElementById("viewChatRoom");
      if ((roomsView && !roomsView.hidden) || (roomView && !roomView.hidden)) {
        global.NogaViews.show("viewHome");
        global.NogaRoles.activateTab("home");
      }
      return;
    }

    if (envelope.type === "message.created") {
      var message = envelope.data && envelope.data.message;
      updateRoomPreview(envelope.room_id, message);
      var isOwn =
        message &&
        message.author &&
        message.author.is_current_user;
      if (!isOwn && Number(envelope.room_id) !== Number(currentRoomId)) {
        bumpRoomUnread(envelope.room_id, 0);
      } else if (!isOwn && !roomsById[envelope.room_id]) {
        loadRooms();
      }
      return;
    }

    if (envelope.type === "mention.created") {
      if (Number(envelope.room_id) !== Number(currentRoomId)) {
        bumpRoomUnread(envelope.room_id, 1);
      } else {
        totalUnreadMentions += 1;
        applyUnread(totalUnread, totalUnreadMentions);
      }
      return;
    }

    if (envelope.type === "read.updated" || envelope.type === "message.deleted") {
      loadRooms();
    }
  }

  function showRoomShell(room) {
    var title = document.getElementById("chatRoomTitle");
    if (title) title.textContent = (room && room.title) || "Комната";
    var loading = document.getElementById("chatMessagesLoading");
    var feed = document.getElementById("chatMessages");
    var empty = document.getElementById("chatMessagesEmpty");
    if (loading) loading.hidden = true;
    if (feed) feed.innerHTML = "";
    if (empty) empty.hidden = false;
  }

  async function openRoom(roomId, options) {
    options = options || {};
    if (!chatAllowed()) return;
    currentRoomId = Number(roomId);
    pendingMessageId = options.messageId || null;

    var room = roomsById[currentRoomId];
    if (!room) {
      try {
        await loadRooms();
        room = roomsById[currentRoomId];
      } catch (e) {
        room = null;
      }
    }
    showRoomShell(room || { title: "Комната" });
    global.NogaViews.show("viewChatRoom");
    ensureStream();
  }

  function openMessage(roomId, messageId) {
    openRoom(roomId, { messageId: messageId });
  }

  function show(options) {
    options = options || {};
    if (!chatAllowed()) {
      if (global.NogaTelegram && global.NogaTelegram.notify) {
        global.NogaTelegram.notify("Чат недоступен");
      }
      return;
    }
    entrySource = options.from === "profile" ? "profile" : "home";
    currentRoomId = null;
    pendingMessageId = null;
    bind();
    global.NogaViews.show("viewChatRooms");
    loadRooms();
  }

  function goBackFromRooms() {
    if (entrySource === "profile") {
      global.NogaProfile.show();
      return;
    }
    global.NogaViews.show("viewHome");
    global.NogaRoles.activateTab("home");
  }

  function bind() {
    if (bound) return;
    bound = true;

    var roomsBack = document.getElementById("chatRoomsBack");
    if (roomsBack) {
      roomsBack.addEventListener("click", goBackFromRooms);
    }

    var roomBack = document.getElementById("chatRoomBack");
    if (roomBack) {
      roomBack.addEventListener("click", function () {
        currentRoomId = null;
        pendingMessageId = null;
        show({ from: entrySource });
      });
    }

    var bell = document.getElementById("bell");
    if (bell) {
      bell.addEventListener("click", function () {
        if (!chatAllowed()) return;
        global.NogaProfile.hideBack();
        show({ from: "home" });
        global.NogaRoles.activateTab("home");
      });
    }
  }

  function syncAccess() {
    applyGate();
    if (chatAllowed()) {
      bind();
      global.NogaApi.chatRooms()
        .then(function (payload) {
          if (!chatAllowed()) return;
          applyRoomsPayload(payload);
          ensureStream();
        })
        .catch(function () {
          /* список подтянется при открытии экрана; stream стартует без cursor */
          if (chatAllowed()) ensureStream();
        });
    } else {
      release();
      applyUnread(0, 0);
    }
  }

  function release() {
    listRequestId += 1;
    stopStream();
    releaseBlobs();
    currentRoomId = null;
    pendingMessageId = null;
    roomsCache = [];
    roomsById = {};
    latestEventId = null;
  }

  global.NogaChat = {
    show: show,
    openRoom: openRoom,
    openMessage: openMessage,
    applyEvent: applyEvent,
    applyUnread: applyUnread,
    release: release,
    syncAccess: syncAccess,
    chatAllowed: chatAllowed,
  };
})(window);
