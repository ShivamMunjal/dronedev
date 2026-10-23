/* controls.js — touch/pointer joystick widgets shared by the dashboards.
 *   makePad(el, onChange)   : 360-degree circular pad -> onChange(nx,ny) in [-1,1]
 *   makeWheel(el, onChange) : steering-wheel yaw   -> onChange(v) in [-1,1]
 * Self-centering on release. Elements must contain a child with class "knob".
 */
(function () {
  const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);

  window.makePad = function (el, onChange) {
    const knob = el.querySelector('.knob');
    let active = false;
    const rad = () => Math.max(10, el.clientWidth / 2 - (knob ? knob.offsetWidth / 2 : 0) - 4);
    function apply(e) {
      const r = el.getBoundingClientRect();
      let dx = e.clientX - (r.left + r.width / 2);
      let dy = e.clientY - (r.top + r.height / 2);
      const R = rad();
      let nx = dx / R, ny = dy / R;
      const m = Math.hypot(nx, ny);
      if (m > 1) { nx /= m; ny /= m; }
      if (knob) knob.style.transform = `translate(${nx * R}px,${ny * R}px)`;
      onChange(nx, ny);
    }
    function end() {
      if (!active) return; active = false;
      if (knob) knob.style.transform = 'translate(0,0)';
      onChange(0, 0);
    }
    el.addEventListener('pointerdown', e => { e.preventDefault(); active = true; try { el.setPointerCapture(e.pointerId); } catch (_) {} apply(e); });
    el.addEventListener('pointermove', e => { if (active) { e.preventDefault(); apply(e); } });
    el.addEventListener('pointerup', e => { e.preventDefault(); end(); });
    el.addEventListener('pointercancel', end);
    el.addEventListener('lostpointercapture', end);
    el.addEventListener('contextmenu', e => e.preventDefault());
  };

  window.makeWheel = function (el, onChange) {
    const knob = el.querySelector('.knob');
    const LIM = Math.PI * 0.75, BASE = -Math.PI / 2;   /* neutral at top */
    let active = false, acc = 0, last = 0;
    function place() {
      const R = Math.max(10, el.clientWidth / 2 * 0.72);
      const a = BASE + acc;
      if (knob) knob.style.transform = `translate(${Math.cos(a) * R}px,${Math.sin(a) * R}px)`;
    }
    place();
    function ang(e) {
      const r = el.getBoundingClientRect();
      return Math.atan2(e.clientY - (r.top + r.height / 2), e.clientX - (r.left + r.width / 2));
    }
    el.addEventListener('pointerdown', e => { e.preventDefault(); active = true; try { el.setPointerCapture(e.pointerId); } catch (_) {} last = ang(e); });
    el.addEventListener('pointermove', e => {
      if (!active) return; e.preventDefault();
      let a = ang(e), d = a - last;
      if (d > Math.PI) d -= 2 * Math.PI;
      if (d < -Math.PI) d += 2 * Math.PI;
      acc = clamp(acc + d, -LIM, LIM); last = a; place(); onChange(acc / LIM);
    });
    function end() {
      if (!active) return; active = false;
      const s = acc, t0 = performance.now();
      (function anim(t) {
        const k = Math.min(1, (t - t0) / 160);
        acc = s * (1 - k); place(); onChange(acc / LIM);
        if (k < 1) requestAnimationFrame(anim);
      })(t0);
    }
    el.addEventListener('pointerup', e => { e.preventDefault(); end(); });
    el.addEventListener('pointercancel', end);
    el.addEventListener('lostpointercapture', end);
    el.addEventListener('contextmenu', e => e.preventDefault());
  };
})();
