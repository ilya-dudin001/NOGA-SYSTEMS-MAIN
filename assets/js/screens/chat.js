/* Чат: полный UX комнат и сообщений (этапы 6–7). */
(function (global) {
  "use strict";

  var MAX_CHARS = 4000;
  var MAX_FILES = 10;
  var MAX_UPLOAD_BYTES = 100 * 1024 * 1024;
  var PAGE_SIZE = 50;
  var BOTTOM_GAP = 72;

  var streamHandle = null;
  var uploadHandle = null;
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
  var roomRequestId = 0;
  var peersMode = false;

  var messagesById = {};
  var messageIds = [];
  var hasMoreOlder = false;
  var loadingOlder = false;
  var nearBottom = true;
  var unreadBelow = 0;
  var readTimer = null;
  var roomListeners = [];

  var replyTo = null;
  var mentionParts = [];
  var selectedFiles = [];
  var mentionCandidates = [];

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function canWrite() {
    return global.NogaRoles.can("chat:write");
  }

  function canDirect() {
    return global.NogaRoles.can("chat:direct");
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

  function currentUserId() {
    var user = global.NogaRoles.getUser();
    return user ? Number(user.id) : null;
  }

  function notify(message) {
    if (global.NogaTelegram && global.NogaTelegram.notify) {
      global.NogaTelegram.notify(message);
    }
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
    if (sameDay && global.NogaDict.formatTime) return global.NogaDict.formatTime(iso);
    return global.NogaDict.formatDate(iso);
  }

  function messagePreview(message) {
    if (!message) return "";
    if (message.is_deleted) return "Сообщение удалено";
    if (message.preview) return message.preview;
    var text = "";
    Array.prototype.forEach.call(message.content || [], function (part) {
      if (part.type === "text") text += part.text || "";
      if (part.type === "mention") text += "@" + (part.label || "");
    });
    if (!text && message.attachments && message.attachments.length) return "Файл";
    return text;
  }

  function mentionsCurrentUser(message) {
    var uid = currentUserId();
    if (!uid || !message || !message.content) return false;
    for (var i = 0; i < message.content.length; i++) {
      var part = message.content[i];
      if (part.type === "mention" && Number(part.user_id) === uid) return true;
    }
    return false;
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

  function trackBlob(url) {
    if (url) blobUrls.push(url);
    return url;
  }

  function on(node, type, handler, opts) {
    if (!node) return;
    node.addEventListener(type, handler, opts || false);
    roomListeners.push({ node: node, type: type, handler: handler, opts: opts || false });
  }

  function clearRoomListeners() {
    roomListeners.forEach(function (item) {
      try {
        item.node.removeEventListener(item.type, item.handler, item.opts);
      } catch (e) {
        /* ignore */
      }
    });
    roomListeners = [];
  }

  function abortUpload() {
    if (uploadHandle && uploadHandle.abort) uploadHandle.abort();
    uploadHandle = null;
    setUploadProgress(null);
  }

  function setUploadProgress(percent) {
    var wrap = document.getElementById("chatUploadProgress");
    var bar = document.getElementById("chatUploadBar");
    if (!wrap || !bar) return;
    if (percent === null || percent === undefined) {
      wrap.hidden = true;
      bar.style.width = "0%";
      return;
    }
    wrap.hidden = false;
    bar.style.width = Math.max(0, Math.min(100, Number(percent) || 0)) + "%";
  }

  function applyGate() {
    var bell = document.getElementById("bell");
    if (bell) bell.hidden = !chatAllowed();
    var neu = document.getElementById("chatNewDirect");
    if (neu) neu.hidden = !(chatAllowed() && canDirect());
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

  function setRoomsLoading(visible) {
    var loading = document.getElementById("chatRoomsLoading");
    if (loading) loading.hidden = !visible;
  }

  function setRoomsEmpty(visible) {
    var empty = document.getElementById("chatRoomsEmpty");
    if (empty) empty.hidden = !visible;
  }

  function renderRoomCard(room) {
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
    if (global.EmIcons) global.EmIcons.hydrate(list);
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
      setRoomsLoading(false);
      renderRooms([]);
      applyUnread(0, 0);
      return;
    }
    var req = ++listRequestId;
    setRoomsLoading(true);
    setRoomsEmpty(false);
    try {
      var payload = await global.NogaApi.chatRooms();
      if (req !== listRequestId) return;
      applyRoomsPayload(payload);
      ensureStream();
    } catch (err) {
      if (req !== listRequestId) return;
      renderRooms([]);
      notify((err && err.message) || "Не удалось загрузить чат");
    } finally {
      if (req === listRequestId) setRoomsLoading(false);
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
    var roomsView = document.getElementById("viewChatRooms");
    if (roomsView && !roomsView.hidden && !peersMode) renderRooms(roomsCache);
  }

  function updateRoomPreview(roomId, message) {
    var room = roomsById[roomId];
    if (!room || !message) return;
    room.last_message = {
      id: message.id,
      author_name: (message.author && message.author.display_name) || message.author_name || "",
      preview: messagePreview(message),
      has_attachments: Boolean(message.attachments && message.attachments.length),
      created_at: message.created_at,
    };
    var roomsView = document.getElementById("viewChatRooms");
    if (roomsView && !roomsView.hidden && !peersMode) renderRooms(roomsCache);
  }

  function clearComposerState() {
    replyTo = null;
    mentionParts = [];
    selectedFiles = [];
    mentionCandidates = [];
    var input = document.getElementById("chatInput");
    if (input) input.value = "";
    renderReplyBar();
    renderMentionChips();
    renderFileList();
    hideMentionPicker();
    setUploadProgress(null);
  }

  function leaveRoomState() {
    roomRequestId += 1;
    clearRoomListeners();
    abortUpload();
    if (readTimer) {
      clearTimeout(readTimer);
      readTimer = null;
    }
    messagesById = {};
    messageIds = [];
    hasMoreOlder = false;
    loadingOlder = false;
    nearBottom = true;
    unreadBelow = 0;
    pendingMessageId = null;
    clearComposerState();
    var feed = document.getElementById("chatMessages");
    if (feed) feed.innerHTML = "";
    var jump = document.getElementById("chatJumpNew");
    if (jump) jump.hidden = true;
    var older = document.getElementById("chatLoadOlder");
    if (older) older.hidden = true;
  }

  function isRoomVisible() {
    var view = document.getElementById("viewChatRoom");
    return Boolean(view && !view.hidden && currentRoomId);
  }

  function threadEl() {
    return document.getElementById("chatThread");
  }

  function measureNearBottom() {
    var thread = threadEl();
    if (!thread) return true;
    return thread.scrollHeight - thread.scrollTop - thread.clientHeight <= BOTTOM_GAP;
  }

  function updateJumpButton() {
    var jump = document.getElementById("chatJumpNew");
    if (!jump) return;
    jump.hidden = !(unreadBelow > 0 && !nearBottom);
  }

  function scrollToBottom(force) {
    var thread = threadEl();
    if (!thread) return;
    if (!force && !nearBottom) return;
    thread.scrollTop = thread.scrollHeight;
    nearBottom = true;
    unreadBelow = 0;
    updateJumpButton();
    scheduleRead();
  }

  function scheduleRead() {
    if (!isRoomVisible() || !nearBottom || !messageIds.length) return;
    if (readTimer) clearTimeout(readTimer);
    readTimer = setTimeout(function () {
      readTimer = null;
      if (!isRoomVisible() || !nearBottom || !messageIds.length) return;
      var lastId = messageIds[messageIds.length - 1];
      var room = roomsById[currentRoomId];
      global.NogaApi.updateChatRead(currentRoomId, lastId)
        .then(function (result) {
          if (room && result) {
            var prevUnread = Number(room.unread_count) || 0;
            var prevMentions = Number(room.unread_mentions) || 0;
            room.unread_count = Number(result.unread_count) || 0;
            room.unread_mentions = Number(result.unread_mentions) || 0;
            totalUnread = Math.max(0, totalUnread - (prevUnread - room.unread_count));
            totalUnreadMentions = Math.max(
              0,
              totalUnreadMentions - (prevMentions - room.unread_mentions)
            );
            applyUnread(totalUnread, totalUnreadMentions);
          }
        })
        .catch(function () {
          /* курсор не критичен */
        });
    }, 350);
  }

  function renderReplyBar() {
    var bar = document.getElementById("chatReplyBar");
    var author = document.getElementById("chatReplyAuthor");
    var preview = document.getElementById("chatReplyPreview");
    if (!bar) return;
    if (!replyTo) {
      bar.hidden = true;
      return;
    }
    bar.hidden = false;
    if (author) {
      author.textContent =
        (replyTo.author && replyTo.author.display_name) ||
        replyTo.author_name ||
        "Сообщение";
    }
    if (preview) preview.textContent = messagePreview(replyTo);
  }

  function renderMentionChips() {
    var host = document.getElementById("chatMentionChips");
    if (!host) return;
    host.innerHTML = "";
    if (!mentionParts.length) {
      host.hidden = true;
      return;
    }
    host.hidden = false;
    mentionParts.forEach(function (part, index) {
      var chip = el("span", "em-chat-chip", "@" + (part.label || part.user_id));
      var clear = el("button", "em-btn-icon em-btn-icon--muted");
      clear.type = "button";
      clear.setAttribute("aria-label", "Убрать упоминание");
      clear.appendChild(el("span", null));
      clear.firstChild.setAttribute("data-em-icon", "close");
      clear.addEventListener("click", function () {
        mentionParts.splice(index, 1);
        renderMentionChips();
      });
      chip.appendChild(clear);
      host.appendChild(chip);
    });
    if (global.EmIcons) global.EmIcons.hydrate(host);
  }

  function renderFileList() {
    var host = document.getElementById("chatFileList");
    if (!host) return;
    host.innerHTML = "";
    if (!selectedFiles.length) {
      host.hidden = true;
      return;
    }
    host.hidden = false;
    selectedFiles.forEach(function (file, index) {
      var row = el("div", "em-chat-file");
      row.appendChild(el("div", "em-chat-file__name em-ellipsis", file.name || "Файл"));
      row.appendChild(
        el(
          "div",
          "em-chat-file__meta em-num",
          global.NogaDict.formatSize ? global.NogaDict.formatSize(file.size) : String(file.size || 0)
        )
      );
      var clear = el("button", "em-btn-icon em-btn-icon--muted");
      clear.type = "button";
      clear.setAttribute("aria-label", "Убрать файл");
      var icon = el("span");
      icon.setAttribute("data-em-icon", "close");
      clear.appendChild(icon);
      clear.addEventListener("click", function () {
        selectedFiles.splice(index, 1);
        renderFileList();
      });
      row.appendChild(clear);
      host.appendChild(row);
    });
    if (global.EmIcons) global.EmIcons.hydrate(host);
  }

  function hideMentionPicker() {
    var picker = document.getElementById("chatMentionPicker");
    if (picker) picker.hidden = true;
  }

  function setComposerEnabled(enabled) {
    var input = document.getElementById("chatInput");
    var send = document.getElementById("chatSendBtn");
    var attach = document.getElementById("chatAttachBtn");
    var mention = document.getElementById("chatMentionBtn");
    var hint = document.getElementById("chatComposerHint");
    if (input) input.disabled = !enabled;
    if (send) send.disabled = !enabled;
    if (attach) attach.disabled = !enabled;
    if (mention) {
      mention.hidden = !enabled;
      mention.disabled = !enabled;
    }
    if (hint) hint.hidden = enabled;
  }

  function buildContentParts() {
    var parts = [];
    mentionParts.forEach(function (part) {
      parts.push({ type: "mention", user_id: Number(part.user_id), label: part.label });
    });
    var input = document.getElementById("chatInput");
    var text = input ? String(input.value || "").replace(/^\s+|\s+$/g, "") : "";
    if (text) parts.push({ type: "text", text: text });
    return parts;
  }

  function contentPlainLength(parts) {
    var total = 0;
    parts.forEach(function (part) {
      if (part.type === "text") total += String(part.text || "").length;
      if (part.type === "mention") total += String(part.label || "").length + 1;
    });
    return total;
  }

  function selectedFilesBytes() {
    var sum = 0;
    selectedFiles.forEach(function (file) {
      sum += Number(file.size) || 0;
    });
    return sum;
  }

  function renderMessageBody(message, host) {
    host.innerHTML = "";
    if (message.is_deleted) {
      host.appendChild(el("div", "em-chat-msg__body", "Сообщение удалено"));
      return;
    }
    var body = el("div", "em-chat-msg__body");
    Array.prototype.forEach.call(message.content || [], function (part) {
      if (part.type === "text") {
        body.appendChild(document.createTextNode(part.text || ""));
      } else if (part.type === "mention") {
        body.appendChild(el("span", "em-chat-msg__mention", "@" + (part.label || "")));
      }
    });
    if (!body.childNodes.length && !(message.attachments && message.attachments.length)) {
      body.textContent = messagePreview(message) || " ";
    }
    host.appendChild(body);

    if (message.attachments && message.attachments.length) {
      var files = el("div", "em-chat-msg__files");
      message.attachments.forEach(function (att) {
        var btn = el("button", "em-btn em-btn--ghost em-btn--sm");
        btn.type = "button";
        btn.appendChild(
          el(
            "span",
            "em-btn__label",
            (att.original_name || "Файл") +
              " · " +
              (global.NogaDict.formatSize
                ? global.NogaDict.formatSize(att.size_bytes)
                : String(att.size_bytes || 0))
          )
        );
        btn.addEventListener("click", function () {
          downloadAttachment(att);
        });
        files.appendChild(btn);
      });
      host.appendChild(files);
    }
  }

  async function downloadAttachment(att) {
    try {
      var blob = await global.NogaApi.chatAttachmentBlob(att.id);
      var url = trackBlob(global.URL.createObjectURL(blob));
      var link = document.createElement("a");
      link.href = url;
      link.download = att.original_name || "file";
      link.rel = "noopener";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (err) {
      notify((err && err.message) || "Не удалось скачать файл");
    }
  }

  function messageNode(message) {
    var card = el("article", "em-chat-msg");
    card.setAttribute("data-message-id", String(message.id));
    if (message.author && message.author.is_current_user) card.classList.add("em-chat-msg--own");
    if (message.is_deleted) card.classList.add("em-chat-msg--deleted");
    if (mentionsCurrentUser(message)) card.classList.add("em-chat-msg--mention");

    var head = el("div", "em-chat-msg__head");
    head.appendChild(
      el(
        "div",
        "em-chat-msg__author em-ellipsis",
        (message.author && message.author.display_name) || "Участник"
      )
    );
    head.appendChild(
      el(
        "div",
        "em-chat-msg__time em-num",
        global.NogaDict.formatDateTime
          ? global.NogaDict.formatDateTime(message.created_at)
          : formatRoomTime(message.created_at)
      )
    );
    card.appendChild(head);

    if (message.reply) {
      var reply = el("button", "em-chat-msg__reply");
      reply.type = "button";
      reply.appendChild(
        el("div", "em-chat-reply__author em-ellipsis", message.reply.author_name || "Сообщение")
      );
      reply.appendChild(
        el("div", "em-chat-reply__preview em-ellipsis", message.reply.preview || "")
      );
      reply.addEventListener("click", function () {
        jumpToMessage(message.reply.id);
      });
      card.appendChild(reply);
    }

    var bodyHost = el("div");
    renderMessageBody(message, bodyHost);
    while (bodyHost.firstChild) card.appendChild(bodyHost.firstChild);

    if (!message.is_deleted) {
      var actions = el("div", "em-chat-msg__actions");
      if (canWrite()) {
        var replyBtn = el("button", "em-btn em-btn--ghost em-btn--sm");
        replyBtn.type = "button";
        replyBtn.appendChild(el("span", "em-btn__label", "Ответить"));
        replyBtn.addEventListener("click", function () {
          replyTo = message;
          renderReplyBar();
          var input = document.getElementById("chatInput");
          if (input) input.focus();
        });
        actions.appendChild(replyBtn);
      }
      if (message.can_delete) {
        var delBtn = el("button", "em-btn em-btn--ghost em-btn--sm");
        delBtn.type = "button";
        delBtn.appendChild(el("span", "em-btn__label", "Удалить"));
        delBtn.addEventListener("click", function () {
          global.NogaTelegram.confirmAction("Удалить сообщение?", function () {
            deleteMessage(message.id);
          });
        });
        actions.appendChild(delBtn);
      }
      if (actions.childNodes.length) card.appendChild(actions);
    }
    return card;
  }

  function renderFeed() {
    var feed = document.getElementById("chatMessages");
    var empty = document.getElementById("chatMessagesEmpty");
    var older = document.getElementById("chatLoadOlder");
    if (!feed) return;
    feed.innerHTML = "";
    messageIds.forEach(function (id) {
      var message = messagesById[id];
      if (message) feed.appendChild(messageNode(message));
    });
    if (empty) empty.hidden = messageIds.length > 0;
    if (older) older.hidden = !hasMoreOlder;
    if (global.EmIcons) global.EmIcons.hydrate(feed);
  }

  function upsertMessage(message, options) {
    options = options || {};
    if (!message || message.id === undefined || message.id === null) return false;
    var id = Number(message.id);
    var exists = Boolean(messagesById[id]);
    messagesById[id] = message;
    if (!exists) {
      messageIds.push(id);
      messageIds.sort(function (a, b) {
        return a - b;
      });
    }
    if (options.render !== false) {
      var feed = document.getElementById("chatMessages");
      if (!feed) return !exists;
      var node = feed.querySelector('[data-message-id="' + id + '"]');
      var next = messageNode(message);
      if (node && node.parentNode) node.parentNode.replaceChild(next, node);
      else {
        var insertBefore = null;
        for (var i = 0; i < feed.children.length; i++) {
          var childId = Number(feed.children[i].getAttribute("data-message-id"));
          if (childId > id) {
            insertBefore = feed.children[i];
            break;
          }
        }
        if (insertBefore) feed.insertBefore(next, insertBefore);
        else feed.appendChild(next);
      }
      if (global.EmIcons) global.EmIcons.hydrate(next);
      var empty = document.getElementById("chatMessagesEmpty");
      if (empty) empty.hidden = true;
    }
    return !exists;
  }

  function markDeleted(messageId) {
    var id = Number(messageId);
    var message = messagesById[id];
    if (!message) return;
    message.is_deleted = true;
    message.content = [];
    message.attachments = [];
    message.can_delete = false;
    upsertMessage(message);
  }

  async function deleteMessage(messageId) {
    try {
      await global.NogaApi.deleteChatMessage(messageId);
      markDeleted(messageId);
    } catch (err) {
      notify((err && err.message) || "Не удалось удалить");
    }
  }

  async function jumpToMessage(messageId) {
    var id = Number(messageId);
    if (!id || !currentRoomId) return;
    if (messagesById[id]) {
      highlightMessage(id);
      return;
    }
    try {
      var rows = await global.NogaApi.chatMessages(currentRoomId, {
        around_id: id,
        limit: PAGE_SIZE,
      });
      ingestPage(rows, { replace: false });
      highlightMessage(id);
    } catch (err) {
      notify((err && err.message) || "Не удалось найти сообщение");
    }
  }

  function highlightMessage(messageId) {
    var feed = document.getElementById("chatMessages");
    if (!feed) return;
    var node = feed.querySelector('[data-message-id="' + messageId + '"]');
    if (!node) return;
    node.classList.add("em-chat-msg--flash");
    if (node.scrollIntoView) node.scrollIntoView({ block: "center" });
    nearBottom = measureNearBottom();
    updateJumpButton();
  }

  function ingestPage(rows, options) {
    options = options || {};
    var list = rows || [];
    if (options.replace) {
      messagesById = {};
      messageIds = [];
    }
    list.forEach(function (message) {
      upsertMessage(message, { render: false });
    });
    hasMoreOlder = list.length >= PAGE_SIZE;
    renderFeed();
  }

  async function loadHistory(options) {
    options = options || {};
    if (!currentRoomId) return;
    var req = ++roomRequestId;
    var loading = document.getElementById("chatMessagesLoading");
    if (loading) loading.hidden = false;
    try {
      var params = { limit: PAGE_SIZE };
      if (options.aroundId) params.around_id = options.aroundId;
      var rows = await global.NogaApi.chatMessages(currentRoomId, params);
      if (req !== roomRequestId) return;
      ingestPage(rows, { replace: true });
      if (options.aroundId) highlightMessage(options.aroundId);
      else scrollToBottom(true);
      scheduleRead();
    } catch (err) {
      if (req !== roomRequestId) return;
      notify((err && err.message) || "Не удалось загрузить сообщения");
    } finally {
      if (req === roomRequestId && loading) loading.hidden = true;
    }
  }

  async function loadOlder() {
    if (!currentRoomId || loadingOlder || !hasMoreOlder || !messageIds.length) return;
    loadingOlder = true;
    var thread = threadEl();
    var prevHeight = thread ? thread.scrollHeight : 0;
    var prevTop = thread ? thread.scrollTop : 0;
    try {
      var rows = await global.NogaApi.chatMessages(currentRoomId, {
        before_id: messageIds[0],
        limit: PAGE_SIZE,
      });
      hasMoreOlder = rows.length >= PAGE_SIZE;
      rows.forEach(function (message) {
        upsertMessage(message, { render: false });
      });
      renderFeed();
      if (thread) {
        thread.scrollTop = thread.scrollHeight - prevHeight + prevTop;
      }
    } catch (err) {
      notify((err && err.message) || "Не удалось подгрузить историю");
    } finally {
      loadingOlder = false;
      var older = document.getElementById("chatLoadOlder");
      if (older) older.hidden = !hasMoreOlder;
    }
  }

  async function sendCurrent() {
    if (!canWrite() || !currentRoomId || uploadHandle) return;
    var parts = buildContentParts();
    if (!parts.length && !selectedFiles.length) {
      notify("Введите текст или прикрепите файл");
      return;
    }
    if (contentPlainLength(parts) > MAX_CHARS) {
      notify("Сообщение слишком длинное");
      return;
    }
    if (selectedFiles.length > MAX_FILES) {
      notify("Не больше " + MAX_FILES + " файлов");
      return;
    }
    if (selectedFilesBytes() > MAX_UPLOAD_BYTES) {
      notify("Суммарный размер файлов больше 100 МБ");
      return;
    }

    var files = selectedFiles.slice();
    var replyId = replyTo ? replyTo.id : null;
    var sendBtn = document.getElementById("chatSendBtn");
    if (sendBtn) sendBtn.classList.add("is-loading");
    uploadHandle = global.NogaApi.sendChatMessage(
      currentRoomId,
      parts,
      replyId,
      files,
      function (progress) {
        setUploadProgress(progress.percent);
      }
    );
    try {
      var message = await uploadHandle;
      uploadHandle = null;
      setUploadProgress(null);
      clearComposerState();
      var isNew = upsertMessage(message);
      updateRoomPreview(currentRoomId, message);
      nearBottom = true;
      unreadBelow = 0;
      updateJumpButton();
      scrollToBottom(true);
      if (!isNew) scheduleRead();
    } catch (err) {
      uploadHandle = null;
      setUploadProgress(null);
      if (err && err.name === "AbortError") return;
      notify((err && err.message) || "Не удалось отправить");
    } finally {
      if (sendBtn) sendBtn.classList.remove("is-loading");
    }
  }

  function showPeers(visible) {
    peersMode = Boolean(visible);
    var body = document.getElementById("chatRoomsBody");
    var panel = document.getElementById("chatPeersPanel");
    var neu = document.getElementById("chatNewDirect");
    var title = document.querySelector("#chatRoomsHeader .em-header__title");
    if (body) body.hidden = peersMode;
    if (panel) panel.hidden = !peersMode;
    if (neu) neu.hidden = peersMode || !(chatAllowed() && canDirect());
    if (title) title.textContent = peersMode ? "Новый чат" : "Чат";
  }

  async function openPeersPicker() {
    if (!canDirect()) return;
    showPeers(true);
    var loading = document.getElementById("chatPeersLoading");
    var list = document.getElementById("chatPeersList");
    var empty = document.getElementById("chatPeersEmpty");
    if (loading) loading.hidden = false;
    if (list) list.innerHTML = "";
    if (empty) empty.hidden = true;
    try {
      var peers = await global.NogaApi.chatPeers();
      if (loading) loading.hidden = true;
      if (!list) return;
      if (!peers.length) {
        if (empty) empty.hidden = false;
        return;
      }
      peers.forEach(function (peer) {
        var btn = el("button", "em-oprow");
        btn.type = "button";
        btn.appendChild(el("span", "em-oprow__id em-ellipsis", peer.display_name || "Пользователь"));
        var side = el("span", "em-oprow__side");
        side.appendChild(el("span", "em-oprow__time", peer.role_label || peer.role || ""));
        btn.appendChild(side);
        btn.appendChild(
          el(
            "span",
            "em-oprow__meta",
            peer.username ? "@" + peer.username : peer.room_id ? "Диалог уже есть" : "Начать диалог"
          )
        );
        btn.addEventListener("click", function () {
          createOrOpenDirect(peer);
        });
        list.appendChild(btn);
      });
    } catch (err) {
      if (loading) loading.hidden = true;
      notify((err && err.message) || "Не удалось загрузить список");
    }
  }

  async function createOrOpenDirect(peer) {
    try {
      if (peer.room_id) {
        showPeers(false);
        await openRoom(peer.room_id);
        return;
      }
      var room = await global.NogaApi.createChatDirect(peer.id);
      roomsById[room.id] = room;
      showPeers(false);
      await loadRooms();
      await openRoom(room.id);
    } catch (err) {
      notify((err && err.message) || "Не удалось открыть диалог");
    }
  }

  async function openMentionPicker() {
    if (!canWrite() || !currentRoomId) return;
    var picker = document.getElementById("chatMentionPicker");
    var list = document.getElementById("chatMentionList");
    if (!picker || !list) return;
    list.innerHTML = "";
    try {
      var room = roomsById[currentRoomId];
      if (room && room.kind === "direct" && room.peer) {
        mentionCandidates = [room.peer];
      } else {
        mentionCandidates = await global.NogaApi.chatPeers();
      }
      if (!mentionCandidates.length) {
        list.appendChild(el("div", "em-empty", "Некого упомянуть"));
      } else {
        mentionCandidates.forEach(function (peer) {
          var btn = el("button", "em-oprow em-oprow--plain");
          btn.type = "button";
          btn.appendChild(el("span", "em-oprow__id", peer.display_name || "Пользователь"));
          btn.appendChild(
            el("span", "em-oprow__meta", peer.role_label || peer.role || "")
          );
          btn.addEventListener("click", function () {
            addMention(peer);
          });
          list.appendChild(btn);
        });
      }
      picker.hidden = false;
    } catch (err) {
      notify((err && err.message) || "Не удалось загрузить упоминания");
    }
  }

  function addMention(peer) {
    var exists = mentionParts.some(function (part) {
      return Number(part.user_id) === Number(peer.id);
    });
    if (!exists) {
      mentionParts.push({
        type: "mention",
        user_id: peer.id,
        label: peer.display_name || String(peer.id),
      });
      renderMentionChips();
    }
    hideMentionPicker();
  }

  function onFilesChosen(fileList) {
    var incoming = Array.prototype.slice.call(fileList || []);
    if (!incoming.length) return;
    var next = selectedFiles.concat(incoming);
    if (next.length > MAX_FILES) {
      notify("Не больше " + MAX_FILES + " файлов");
      return;
    }
    var bytes = 0;
    next.forEach(function (file) {
      bytes += Number(file.size) || 0;
    });
    if (bytes > MAX_UPLOAD_BYTES) {
      notify("Суммарный размер файлов больше 100 МБ");
      return;
    }
    selectedFiles = next;
    renderFileList();
  }

  function bindRoomChrome() {
    clearRoomListeners();
    var thread = threadEl();
    on(thread, "scroll", function () {
      nearBottom = measureNearBottom();
      if (nearBottom) {
        unreadBelow = 0;
        updateJumpButton();
        scheduleRead();
      } else {
        updateJumpButton();
      }
      if (thread && thread.scrollTop < 40 && hasMoreOlder && !loadingOlder) {
        loadOlder();
      }
    });

    on(document.getElementById("chatLoadOlder"), "click", function () {
      loadOlder();
    });
    on(document.getElementById("chatJumpNew"), "click", function () {
      scrollToBottom(true);
    });
    on(document.getElementById("chatReplyClear"), "click", function () {
      replyTo = null;
      renderReplyBar();
    });
    on(document.getElementById("chatAttachBtn"), "click", function () {
      var input = document.getElementById("chatFileInput");
      if (input) input.click();
    });
    on(document.getElementById("chatFileInput"), "change", function (event) {
      onFilesChosen(event.target.files);
      event.target.value = "";
    });
    on(document.getElementById("chatMentionBtn"), "click", function () {
      var picker = document.getElementById("chatMentionPicker");
      if (picker && !picker.hidden) hideMentionPicker();
      else openMentionPicker();
    });
    on(document.getElementById("chatSendBtn"), "click", function () {
      sendCurrent();
    });
    on(document.getElementById("chatInput"), "keydown", function (event) {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendCurrent();
      }
    });
  }

  function applyEvent(envelope) {
    if (!envelope || !envelope.type) return;
    if (envelope.event_id !== null && envelope.event_id !== undefined) {
      latestEventId = envelope.event_id;
    }

    if (envelope.type === "stream.reset") {
      loadRooms();
      if (currentRoomId) loadHistory({ aroundId: pendingMessageId });
      return;
    }

    if (envelope.type === "access.revoked") {
      release();
      applyGate();
      applyUnread(0, 0);
      notify("Доступ к чату закрыт");
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
      if (!message) return;
      if (message.author && message.author.is_current_user === undefined) {
        message.author.is_current_user =
          Number(message.author.id) === Number(currentUserId());
      }
      updateRoomPreview(envelope.room_id, message);
      if (Number(envelope.room_id) === Number(currentRoomId) && isRoomVisible()) {
        var wasNew = upsertMessage(message);
        if (wasNew) {
          if (nearBottom || (message.author && message.author.is_current_user)) {
            scrollToBottom(true);
          } else {
            unreadBelow += 1;
            updateJumpButton();
          }
        }
        return;
      }
      var isOwn = message.author && message.author.is_current_user;
      if (!isOwn) {
        if (roomsById[envelope.room_id]) bumpRoomUnread(envelope.room_id, 0);
        else loadRooms();
      }
      return;
    }

    if (envelope.type === "message.deleted") {
      var deletedId = envelope.data && envelope.data.message_id;
      if (Number(envelope.room_id) === Number(currentRoomId)) markDeleted(deletedId);
      loadRooms();
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

    if (envelope.type === "read.updated") {
      loadRooms();
    }
  }

  async function openRoom(roomId, options) {
    options = options || {};
    if (!chatAllowed()) return;
    leaveRoomState();
    currentRoomId = Number(roomId);
    pendingMessageId = options.messageId || null;
    showPeers(false);

    var room = roomsById[currentRoomId];
    if (!room) {
      try {
        await loadRooms();
        room = roomsById[currentRoomId];
      } catch (e) {
        room = null;
      }
    }

    var title = document.getElementById("chatRoomTitle");
    if (title) title.textContent = (room && room.title) || "Комната";
    setComposerEnabled(canWrite());
    clearComposerState();
    bindRoomChrome();
    global.NogaViews.show("viewChatRoom");
    ensureStream();
    await loadHistory({ aroundId: pendingMessageId });
    if (global.EmIcons) global.EmIcons.hydrate(document.getElementById("viewChatRoom"));
  }

  function openMessage(roomId, messageId) {
    return openRoom(roomId, { messageId: messageId });
  }

  function show(options) {
    options = options || {};
    if (!chatAllowed()) {
      notify("Чат недоступен");
      return;
    }
    entrySource = options.from === "profile" ? "profile" : "home";
    currentRoomId = null;
    leaveRoomState();
    showPeers(false);
    bind();
    applyGate();
    global.NogaViews.show("viewChatRooms");
    loadRooms();
  }

  function goBackFromRooms() {
    if (peersMode) {
      showPeers(false);
      return;
    }
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
    if (roomsBack) roomsBack.addEventListener("click", goBackFromRooms);

    var roomBack = document.getElementById("chatRoomBack");
    if (roomBack) {
      roomBack.addEventListener("click", function () {
        currentRoomId = null;
        leaveRoomState();
        show({ from: entrySource });
      });
    }

    var neu = document.getElementById("chatNewDirect");
    if (neu) {
      neu.addEventListener("click", function () {
        openPeersPicker();
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

  function consumeDeepLink() {
    if (!chatAllowed() || !global.NogaTelegram || !global.NogaTelegram.getChatDeepLink) {
      return;
    }
    var link = global.NogaTelegram.getChatDeepLink();
    if (!link || !link.roomId) return;
    global.NogaTelegram.clearChatDeepLink();
    openMessage(link.roomId, link.messageId || null);
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
          consumeDeepLink();
        })
        .catch(function () {
          if (chatAllowed()) ensureStream();
        });
    } else {
      release();
      applyUnread(0, 0);
    }
  }

  function release() {
    listRequestId += 1;
    roomRequestId += 1;
    stopStream();
    abortUpload();
    leaveRoomState();
    releaseBlobs();
    currentRoomId = null;
    roomsCache = [];
    roomsById = {};
    latestEventId = null;
    peersMode = false;
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
