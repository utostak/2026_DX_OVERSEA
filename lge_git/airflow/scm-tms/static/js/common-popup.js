/**
 * common-popup.js
 * LG Sales Program — 공용 Alert / Confirm 팝업
 * ─────────────────────────────────────────────
 * showAlert(message, options?)   → Promise<void>
 * showConfirm(message, options?) → Promise<boolean>
 *
 * options: { title, type: 'info'|'success'|'warning'|'error'|'confirm' }
 */

(function () {
  /* ────────────────────────── CSS 주입 ────────────────────────── */
  const STYLE_ID = '__lg-popup-styles__';
  if (!document.getElementById(STYLE_ID)) {
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
/* ── LG Popup Overlay ────────────────────────────────────────── */
.lg-popup-overlay {
  position: fixed;
  inset: 0;
  z-index: 99999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(28, 28, 28, 0.45);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  animation: lgPopupFadeIn 0.18s ease;
}
.lg-popup-overlay.closing {
  animation: lgPopupFadeOut 0.18s ease forwards;
}
@keyframes lgPopupFadeIn  { from { opacity: 0; } to { opacity: 1; } }
@keyframes lgPopupFadeOut { from { opacity: 1; } to { opacity: 0; } }

/* ── 팝업 박스 ───────────────────────────────────────────────── */
.lg-popup-box {
  background: #ffffff;
  border-radius: 14px;
  box-shadow: 0 20px 60px rgba(0,0,0,.18), 0 4px 16px rgba(0,0,0,.08);
  width: 420px;
  max-width: calc(100vw - 32px);
  overflow: hidden;
  animation: lgPopupSlideIn 0.22s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.lg-popup-overlay.closing .lg-popup-box {
  animation: lgPopupSlideOut 0.18s ease forwards;
}
@keyframes lgPopupSlideIn  { from { transform: scale(0.88) translateY(-12px); opacity: 0; } to { transform: scale(1) translateY(0); opacity: 1; } }
@keyframes lgPopupSlideOut { from { transform: scale(1);    opacity: 1; } to { transform: scale(0.92); opacity: 0; } }

/* ── 헤더 스트라이프 ─────────────────────────────────────────── */
.lg-popup-stripe {
  height: 5px;
  width: 100%;
}
.lg-popup-stripe.info    { background: linear-gradient(90deg, #3b82f6, #60a5fa); }
.lg-popup-stripe.success { background: linear-gradient(90deg, #16a34a, #4ade80); }
.lg-popup-stripe.warning { background: linear-gradient(90deg, #d97706, #fbbf24); }
.lg-popup-stripe.error   { background: linear-gradient(90deg, #A50034, #e11d48); }
.lg-popup-stripe.confirm { background: linear-gradient(90deg, #A50034, #e11d48); }

/* ── 본문 ────────────────────────────────────────────────────── */
.lg-popup-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 28px 28px 20px;
  gap: 12px;
  text-align: center;
  font-family: 'Inter', -apple-system, sans-serif;
}

/* ── 아이콘 원형 배지 ────────────────────────────────────────── */
.lg-popup-icon-wrap {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  flex-shrink: 0;
}
.lg-popup-icon-wrap.info    { background: #eff6ff; color: #2563eb; }
.lg-popup-icon-wrap.success { background: #f0fdf4; color: #16a34a; }
.lg-popup-icon-wrap.warning { background: #fffbeb; color: #d97706; }
.lg-popup-icon-wrap.error   { background: #fff1f2; color: #A50034; }
.lg-popup-icon-wrap.confirm { background: #fff1f2; color: #A50034; }

/* ── 제목 / 메시지 ───────────────────────────────────────────── */
.lg-popup-title {
  font-size: 15px;
  font-weight: 700;
  color: #1c1c1c;
  line-height: 1.3;
  margin: 0;
}
.lg-popup-message {
  font-size: 13.5px;
  color: #4b4b4b;
  line-height: 1.55;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}

/* ── 버튼 영역 ───────────────────────────────────────────────── */
.lg-popup-footer {
  display: flex;
  justify-content: center;
  gap: 10px;
  padding: 0 28px 24px;
}
.lg-popup-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 9px 24px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  font-family: 'Inter', -apple-system, sans-serif;
  cursor: pointer;
  border: none;
  outline: none;
  transition: background 0.15s, transform 0.1s, box-shadow 0.15s;
  min-width: 88px;
}
.lg-popup-btn:active { transform: scale(0.97); }

.lg-popup-btn-ok {
  background: #A50034;
  color: #fff;
  box-shadow: 0 2px 8px rgba(165,0,52,.3);
}
.lg-popup-btn-ok:hover { background: #8b002b; box-shadow: 0 4px 12px rgba(165,0,52,.4); }

.lg-popup-btn-ok.info    { background: #2563eb; box-shadow: 0 2px 8px rgba(37,99,235,.3); }
.lg-popup-btn-ok.info:hover { background: #1d4ed8; }

.lg-popup-btn-ok.success { background: #16a34a; box-shadow: 0 2px 8px rgba(22,163,74,.3); }
.lg-popup-btn-ok.success:hover { background: #15803d; }

.lg-popup-btn-ok.warning { background: #d97706; box-shadow: 0 2px 8px rgba(217,119,6,.3); }
.lg-popup-btn-ok.warning:hover { background: #b45309; }

.lg-popup-btn-cancel {
  background: #f0ece4;
  color: #4b4b4b;
  border: 1px solid #ddd6c8;
}
.lg-popup-btn-cancel:hover { background: #e6e0d2; }
`;
    document.head.appendChild(style);
  }

  /* ────────────────────────── 유틸 ───────────────────────────── */

  /**
   * 메시지에서 타입 자동 감지
   * ✅ → success, ❌ → error, ⚠️ → warning, 기본 → info
   */
  function detectType(message, fallback) {
    if (fallback && fallback !== 'auto') return fallback;
    if (!message) return 'info';
    const m = String(message);
    if (m.startsWith('✅') || m.startsWith('✔')) return 'success';
    if (m.startsWith('❌') || m.startsWith('✖') || m.includes('failed') || m.includes('error') || m.includes('Failed') || m.includes('Error')) return 'error';
    if (m.startsWith('⚠️') || m.startsWith('⚠') || m.includes('warning') || m.includes('Warning')) return 'warning';
    return 'info';
  }

  const ICONS = {
    info:    '<i class="fas fa-info-circle"></i>',
    success: '<i class="fas fa-check-circle"></i>',
    warning: '<i class="fas fa-exclamation-triangle"></i>',
    error:   '<i class="fas fa-times-circle"></i>',
    confirm: '<i class="fas fa-question-circle"></i>',
  };

  const DEFAULT_TITLES = {
    info:    'Notice',
    success: 'Success',
    warning: 'Warning',
    error:   'Error',
    confirm: 'Confirm',
  };

  /**
   * 팝업 DOM 생성 후 overlay 반환
   * @param {string} message
   * @param {object} opts - { title, type, buttons: [{label, cls, value}] }
   * @returns {{ overlay: HTMLElement, promise: Promise<any> }}
   */
  function createPopup(message, opts = {}) {
    const type  = opts.type  || 'info';
    const title = opts.title || DEFAULT_TITLES[type] || 'Notice';

    /* 오버레이 */
    const overlay = document.createElement('div');
    overlay.className = 'lg-popup-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');

    /* 박스 */
    const box = document.createElement('div');
    box.className = 'lg-popup-box';

    /* 상단 컬러 스트라이프 */
    const stripe = document.createElement('div');
    stripe.className = `lg-popup-stripe ${type}`;

    /* 본문 */
    const body = document.createElement('div');
    body.className = 'lg-popup-body';

    /* 아이콘 */
    const iconWrap = document.createElement('div');
    iconWrap.className = `lg-popup-icon-wrap ${type}`;
    iconWrap.innerHTML = ICONS[type] || ICONS.info;

    /* 제목 */
    const titleEl = document.createElement('p');
    titleEl.className = 'lg-popup-title';
    titleEl.textContent = title;

    /* 메시지 */
    const msgEl = document.createElement('p');
    msgEl.className = 'lg-popup-message';
    msgEl.textContent = message;

    body.appendChild(iconWrap);
    body.appendChild(titleEl);
    body.appendChild(msgEl);

    /* 버튼 영역 */
    const footer = document.createElement('div');
    footer.className = 'lg-popup-footer';

    let resolve;
    const promise = new Promise(res => { resolve = res; });

    function close(value) {
      overlay.classList.add('closing');
      overlay.addEventListener('animationend', () => {
        overlay.remove();
        resolve(value);
      }, { once: true });
    }

    (opts.buttons || []).forEach(btn => {
      const el = document.createElement('button');
      el.className = `lg-popup-btn ${btn.cls || ''}`;
      el.innerHTML = btn.label;
      el.addEventListener('click', () => close(btn.value));
      footer.appendChild(el);
    });

    /* ESC 닫기 (마지막 버튼 값 = 취소) */
    const escHandler = (e) => {
      if (e.key === 'Escape') {
        document.removeEventListener('keydown', escHandler);
        const lastBtn = opts.buttons?.[opts.buttons.length - 1];
        close(lastBtn?.value ?? undefined);
      }
    };
    document.addEventListener('keydown', escHandler);

    /* Enter 확인 (첫 번째 버튼) */
    const enterHandler = (e) => {
      if (e.key === 'Enter') {
        document.removeEventListener('keydown', enterHandler);
        const firstBtn = opts.buttons?.[0];
        close(firstBtn?.value ?? undefined);
      }
    };
    document.addEventListener('keydown', enterHandler);

    box.appendChild(stripe);
    box.appendChild(body);
    box.appendChild(footer);
    overlay.appendChild(box);
    document.body.appendChild(overlay);

    /* 첫 번째 버튼에 포커스 */
    requestAnimationFrame(() => footer.querySelector('button')?.focus());

    return { overlay, promise };
  }

  /* ═══════════════════════════════════════════════════════════════
   * window.alert 오버라이드
   * alert('메시지')  또는  await alert('메시지')  모두 사용 가능
   * ─ 타입 자동감지: ✅→success  ❌→error  ⚠️→warning  기본→info
   * ═══════════════════════════════════════════════════════════════ */
  window.alert = function (message, options = {}) {
    const type = detectType(String(message ?? ''), options.type || 'auto');
    const { promise } = createPopup(String(message ?? ''), {
      type,
      title: options.title,
      buttons: [
        { label: '<i class="fas fa-check"></i> OK', cls: `lg-popup-btn-ok ${type}`, value: true },
      ],
    });
    return promise;  // await 없이 호출해도 무방 (fire-and-forget)
  };

  /* ═══════════════════════════════════════════════════════════════
   * window.confirm 오버라이드
   * const ok = await confirm('메시지')  → true / false
   * ─ 반드시 await 와 함께 사용 (Promise 반환)
   * ═══════════════════════════════════════════════════════════════ */
  window.confirm = function (message, options = {}) {
    const { promise } = createPopup(String(message ?? ''), {
      type:  options.type  || 'confirm',
      title: options.title || 'Confirm',
      buttons: [
        { label: `<i class="fas fa-times"></i> ${options.cancelLabel || 'Cancel'}`, cls: 'lg-popup-btn-cancel', value: false },
        { label: `<i class="fas fa-check"></i> ${options.okLabel     || 'OK'}`,     cls: 'lg-popup-btn-ok',    value: true  },
      ],
    });
    return promise;
  };

  /* ── 하위 호환 별칭 (showAlert / showConfirm 도 그대로 동작) ── */
  window.showAlert   = window.alert;
  window.showConfirm = window.confirm;

})();
