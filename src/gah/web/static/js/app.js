/**
 * M5 — SSE 클라이언트 핸들러.
 *
 * Phase 6 fix: htmx-sse extension 의 sse-swap + hx-on::sse-message 매칭이
 * HTML attribute lowercase 강제 (hx-on::sse-message) 와 htmx-sse 가 fire
 * 하는 htmx:sseMessage (camelCase) 사이 mismatch 로 동작 안 함.
 * → native EventSource 직접 등록으로 교체 (htmx-sse 의존성 우회).
 *
 * user_pick_request  → Alpine pickQueue 에 추가 + #pick-cards 에 카드 삽입.
 * user_pick_resolved → Alpine pickQueue 에서 제거 (DOM 정리는 채택/거부 버튼의
 *                      hx-swap="outerHTML" 이 자동으로 처리).
 * labels_signature_changed → 우측 하단 토스트 4초.
 *
 * EventSource 는 연결 끊김 시 브라우저가 자동 재연결 시도.
 */

/**
 * SSE labels_signature_changed 이벤트 핸들러.
 * 라벨 어휘가 변경됐을 때 토스트 알림을 잠깐 노출한다.
 *
 * @param {CustomEvent} evt
 */
window.onLabelsChanged = function (evt) {
  var toast = document.getElementById("labels-toast");
  if (!toast) return;
  toast.textContent = "라벨 어휘가 변경됐습니다 — 새로 고침 권장";
  toast.style.display = "block";
  // 4초 후 자동 숨김
  setTimeout(function () {
    toast.style.display = "none";
  }, 4000);
};

/**
 * 모달 ESC 키 dismiss.
 *
 * #asset-detail-modal 컨테이너 안의 내용을 지워 모달을 닫는다.
 * pick-card 그룹 등 다른 요소에는 영향을 주지 않는다.
 */
document.addEventListener("keydown", function (e) {
  if (e.key !== "Escape") return;
  // 1) 자산 상세 모달 우선 닫기
  var modal = document.getElementById("asset-detail-modal");
  if (modal && modal.innerHTML.trim() !== "") {
    modal.innerHTML = "";
    return;
  }
  // 2) 사이드 패널이 열려 있으면 닫기 (좁은 화면에서 fixed full-height
  //    상태에서도 ESC 로 dead-end 회피 가능)
  if (typeof Alpine !== "undefined" && Alpine.store) {
    try {
      if (Alpine.store("advanced").open) {
        Alpine.store("advanced").open = false;
      }
    } catch (_e) { /* Alpine 미초기화 시 무시 */ }
  }
});

/**
 * SSE user_pick_request 이벤트 핸들러.
 * htmx 의 hx-on::sse-message 에서 호출 — event.detail 형태의 HTMX CustomEvent.
 *
 * @param {CustomEvent} evt - htmx-sse 가 전달하는 이벤트 (evt.detail.data = SSE data 문자열)
 */
window.onPickRequest = function (evt) {
  var data;
  try {
    // htmx-sse 는 SSE 데이터 문자열을 evt.detail.data 에 넣는다.
    data = JSON.parse(evt.detail ? evt.detail.data : evt.data);
  } catch (e) {
    console.warn("[GAH] onPickRequest: JSON 파싱 실패", e);
    return;
  }

  // Alpine store 업데이트 (Alpine 초기화 이후에만 안전)
  if (typeof Alpine !== "undefined" && Alpine.store) {
    Alpine.store("pickQueue").items.unshift(data);
    Alpine.store("notifications").pickCount =
      Alpine.store("pickQueue").items.length;
  }

  // #pick-cards 컨테이너에 카드 fragment 삽입
  var rid = data.request_id;
  if (rid) {
    htmx.ajax("GET", "/ui/pick-card/" + rid, {
      target: "#pick-cards",
      swap: "afterbegin",
    });
  }
};

/**
 * SSE user_pick_resolved 이벤트 핸들러.
 * 채택/거부 버튼의 hx-swap="outerHTML" 이 이미 DOM 을 교체하므로
 * 여기서는 Alpine store 만 정리한다.
 *
 * @param {CustomEvent} evt
 */
window.onPickResolved = function (evt) {
  var data;
  try {
    data = JSON.parse(evt.detail ? evt.detail.data : evt.data);
  } catch (e) {
    console.warn("[GAH] onPickResolved: JSON 파싱 실패", e);
    return;
  }

  if (typeof Alpine !== "undefined" && Alpine.store) {
    var rid = data.request_id;
    Alpine.store("pickQueue").items = Alpine.store("pickQueue").items.filter(
      function (x) { return x.request_id !== rid; }
    );
    Alpine.store("notifications").pickCount =
      Alpine.store("pickQueue").items.length;
  }
};

/**
 * Native EventSource 직접 등록 — htmx-sse 우회.
 *
 * DOMContentLoaded 시점에 한 번 등록. 페이지 진입마다 새 EventSource 인스턴스
 * 생성 (브라우저가 SPA 가 아니라 traditional MPA 라 페이지마다 새로 로드됨).
 */
(function registerSseListeners() {
  if (typeof EventSource === "undefined") {
    console.warn("[GAH] EventSource 미지원 브라우저 — SSE 비활성");
    return;
  }
  function _attach() {
    var es = new EventSource("/sse/notifications");
    es.addEventListener("user_pick_request", window.onPickRequest);
    es.addEventListener("user_pick_resolved", window.onPickResolved);
    es.addEventListener("labels_signature_changed", window.onLabelsChanged);
    // window 에 보관해 디버깅 + 명시적 close 가능
    window._gahSse = es;
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _attach);
  } else {
    _attach();
  }
})();
