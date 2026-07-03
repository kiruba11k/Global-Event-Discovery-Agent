/*
  ScrollAnimations.jsx — GSAP premium animation system
  Plugins: ScrollTrigger · SplitText · ScrambleText · DrawSVGPlugin
           MotionPathPlugin · Draggable · Flip · CustomEase
  Uses gsap.matchMedia() for mobile-safe responsive animations.
*/
import { useEffect } from 'react'
import gsap from 'gsap'
import { ScrollTrigger }      from 'gsap/ScrollTrigger'
import { SplitText }          from 'gsap/SplitText'
import { ScrambleTextPlugin } from 'gsap/ScrambleTextPlugin'
import { DrawSVGPlugin }      from 'gsap/DrawSVGPlugin'
import { Flip }               from 'gsap/Flip'
import { MotionPathPlugin }   from 'gsap/MotionPathPlugin'
import { Draggable }          from 'gsap/Draggable'
import { CustomEase }         from 'gsap/CustomEase'

gsap.registerPlugin(
  ScrollTrigger, SplitText, ScrambleTextPlugin, DrawSVGPlugin,
  Flip, MotionPathPlugin, Draggable, CustomEase,
)

export default function ScrollAnimations() {
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return

    CustomEase.create('ld.expo', 'M0,0 C0.16,1 0.3,1 1,1')
    CustomEase.create('ld.back', 'M0,0 C0.34,1.56 0.64,1 1,1')
    CustomEase.create('ld.gate', 'M0,0 C0.12,0.96 0.2,1 1,1')

    const mm = gsap.matchMedia()
    const ctx = gsap.context(() => {

      /* ─────────────────────────────────────────────────────────────
         1. NAV — slide down + ScrambleText on logo text
      ───────────────────────────────────────────────────────────── */
      gsap.from('.ld-nav', {
        yPercent: -100, opacity: 0, duration: 0.75, ease: 'power3.out',
      })
      const logoTextEl = document.querySelector('.ld-nav-logo-text')
      if (logoTextEl) {
        const finalText = logoTextEl.textContent
        gsap.to(logoTextEl, {
          delay: 0.45, duration: 1.1,
          scrambleText: { text: finalText, chars: 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', speed: 0.45, tweenLength: false },
        })
      }
      gsap.from('.ld-nav-logo-img', {
        opacity: 0, scale: 0.7, rotate: -15, duration: 0.7, ease: 'back.out(2)', delay: 0.1,
      })

      /* ─────────────────────────────────────────────────────────────
         2. HERO — SplitText H1 · ScrambleText badge · DrawSVG lines
      ───────────────────────────────────────────────────────────── */
      gsap.fromTo('.ld-hero-badge',
        { opacity: 0, scale: 0.75, y: -12 },
        { opacity: 1, scale: 1, y: 0, duration: 0.75, ease: 'ld.back', delay: 0.12 },
      )

      const h1 = document.querySelector('.ld-hero-h1')
      if (h1) {
        const splitH1 = new SplitText(h1, { type: 'words', wordsClass: 'gsap-word' })
        gsap.set(h1, { perspective: 800 })
        gsap.from(splitH1.words, {
          opacity: 0, y: '130%', rotateX: -55,
          stagger: 0.055, duration: 0.9, ease: 'expo.out', delay: 0.22,
          onComplete() { splitH1.revert() },
        })
      }

      const sub = document.querySelector('.ld-hero-sub')
      if (sub) {
        const splitSub = new SplitText(sub, { type: 'lines', linesClass: 'gsap-line' })
        gsap.from(splitSub.lines, {
          opacity: 0, y: 28, stagger: 0.1, duration: 0.65, ease: 'power3.out', delay: 0.6,
          onComplete() { splitSub.revert() },
        })
      }

      gsap.from('.ld-hero-actions > *', {
        opacity: 0, y: 22, scale: 0.93, stagger: 0.1, duration: 0.6, ease: 'ld.back', delay: 0.85,
      })
      gsap.from('.ld-hero-trust-item', {
        opacity: 0, x: -20, stagger: 0.1, duration: 0.5, ease: 'power2.out', delay: 1.05,
      })
      gsap.fromTo('.ld-hero-right',
        { opacity: 0, x: 56, scale: 0.94, rotate: 1 },
        { opacity: 1, x: 0, scale: 1, rotate: 0, duration: 1.2, ease: 'expo.out', delay: 0.28 },
      )

      /* DrawSVG — hero decorative lines */
      const heroLines = document.querySelectorAll('.gsap-deco-line')
      if (heroLines.length) {
        gsap.from(heroLines, {
          drawSVG: '0%', duration: 2.8, stagger: 0.35, ease: 'power2.inOut', delay: 0.5,
        })
      }

      /* ─────────────────────────────────────────────────────────────
         3. MOTION PATH — ERV floating badges orbit
      ───────────────────────────────────────────────────────────── */
      const orbits = [
        [{ x:0,y:0 },{ x:10,y:-16 },{ x:16,y:0 },{ x:10,y:16 },{ x:0,y:0 }],
        [{ x:0,y:0 },{ x:-12,y:-10 },{ x:-18,y:0 },{ x:-12,y:12 },{ x:0,y:0 }],
        [{ x:0,y:0 },{ x:8,y:-20 },{ x:14,y:0 },{ x:8,y:14 },{ x:0,y:0 }],
      ]
      document.querySelectorAll('.erv-float').forEach((el, i) => {
        el.style.animation = 'none'
        gsap.to(el, {
          motionPath: { path: orbits[i % orbits.length], curviness: 1.6 },
          duration: 4.8 + i * 0.9, repeat: -1, ease: 'none', delay: i * 0.8,
        })
      })

      /* ─────────────────────────────────────────────────────────────
         4. DRAGGABLE — ERV card snaps back
      ───────────────────────────────────────────────────────────── */
      const ervCard = document.querySelector('.erv-card')
      if (ervCard) {
        Draggable.create(ervCard, {
          type: 'x,y', edgeResistance: 0.7, bounds: '.erv-wrap',
          cursor: 'grab', activeCursor: 'grabbing',
          onDragStart() {
            gsap.to(ervCard, { scale: 1.04, rotate: 0.8, boxShadow: '0 32px 80px rgba(14,165,233,0.22)', duration: 0.2 })
          },
          onDragEnd() {
            gsap.to(ervCard, { x: 0, y: 0, scale: 1, rotate: 0, boxShadow: '', duration: 0.9, ease: 'elastic.out(1, 0.4)' })
          },
        })
      }

      /* ─────────────────────────────────────────────────────────────
         5. PARALLAX SCRUB — hero content + floats
      ───────────────────────────────────────────────────────────── */
      gsap.to('.ld-hero-left', {
        y: -70, ease: 'none',
        scrollTrigger: { trigger: '.ld-hero', start: 'top top', end: 'bottom top', scrub: 0.6 },
      })
      ;['-48', '44', '-30'].forEach((y, i) => {
        gsap.to(document.querySelectorAll('.erv-float')[i] || '.erv-float', {
          y, ease: 'none',
          scrollTrigger: { trigger: '.ld-hero', start: 'top top', end: 'bottom top', scrub: 1 },
        })
      })

      /* ─────────────────────────────────────────────────────────────
         6. LOGO TICKER
      ───────────────────────────────────────────────────────────── */
      gsap.from('.ld-logos', {
        opacity: 0, y: 32, duration: 0.8, ease: 'power2.out',
        scrollTrigger: { trigger: '.ld-logos', start: 'top 92%' },
      })

      /* ─────────────────────────────────────────────────────────────
         7. STATS — ScrambleText numbers on scroll enter
      ───────────────────────────────────────────────────────────── */
      gsap.from('.ld-stat-cell', {
        opacity: 0, y: 40, scale: 0.9, stagger: 0.1, duration: 0.8, ease: 'expo.out',
        scrollTrigger: { trigger: '.ld-stats-inner', start: 'top 86%' },
      })
      document.querySelectorAll('.ld-stat-num').forEach((el) => {
        const finalText = el.textContent.trim()
        ScrollTrigger.create({
          trigger: el, start: 'top 86%', once: true,
          onEnter() {
            gsap.to(el, { duration: 1.3, scrambleText: { text: finalText, chars: '0123456789+s', speed: 0.55 } })
          },
        })
      })

      /* ─────────────────────────────────────────────────────────────
         8. SECTION HEADINGS — SplitText by words (all breakpoints)
      ───────────────────────────────────────────────────────────── */
      document.querySelectorAll('.ld-section-h2').forEach((heading) => {
        const split = new SplitText(heading, { type: 'words' })
        gsap.set(heading, { perspective: 700 })
        gsap.from(split.words, {
          opacity: 0, y: 52, rotateX: -30, stagger: 0.065, duration: 0.95, ease: 'expo.out',
          scrollTrigger: { trigger: heading, start: 'top 88%', toggleActions: 'play none none reverse' },
          onComplete() { split.revert() },
        })
      })
      document.querySelectorAll('.ld-section-eyebrow').forEach((el) => {
        gsap.from(el, {
          opacity: 0, x: -28, duration: 0.65, ease: 'power3.out',
          scrollTrigger: { trigger: el, start: 'top 90%', toggleActions: 'play none none reverse' },
        })
      })
      document.querySelectorAll('.ld-section-sub').forEach((el) => {
        gsap.from(el, {
          opacity: 0, y: 22, duration: 0.7, ease: 'power2.out',
          scrollTrigger: { trigger: el, start: 'top 90%', toggleActions: 'play none none reverse' },
        })
      })

      /* ─────────────────────────────────────────────────────────────
         9. HOW IT WORKS — responsive via matchMedia
            Mobile: simple fade-up (no 3D = no clipping bugs)
            Desktop: full 3D perspective gate effect
      ───────────────────────────────────────────────────────────── */
      const stepsEl = document.querySelectorAll('.ld-step')
      if (stepsEl.length) {
        mm.add('(max-width: 699px)', () => {
          /* MOBILE — clean fade-up, no perspective transforms */
          gsap.from(stepsEl, {
            opacity: 0, y: 36,
            stagger: 0.13, duration: 0.7, ease: 'power2.out',
            scrollTrigger: { trigger: '.ld-steps', start: 'top 85%', toggleActions: 'play none none reverse' },
          })
          gsap.from('.ld-step-icon', {
            scale: 0, stagger: 0.13, duration: 0.55, ease: 'back.out(2)',
            scrollTrigger: { trigger: '.ld-steps', start: 'top 85%', toggleActions: 'play none none reverse' },
          })
          gsap.from('.ld-step-num', {
            opacity: 0, x: -14, stagger: 0.13, duration: 0.45, ease: 'power2.out',
            scrollTrigger: { trigger: '.ld-steps', start: 'top 85%', toggleActions: 'play none none reverse' },
          })
          /* Step points */
          document.querySelectorAll('.ld-step-points').forEach((list) => {
            gsap.from(list.querySelectorAll('.ld-step-point'), {
              opacity: 0, x: -14, stagger: 0.07, duration: 0.45, ease: 'power2.out',
              scrollTrigger: { trigger: list, start: 'top 88%', toggleActions: 'play none none reverse' },
            })
          })
        })

        mm.add('(min-width: 700px)', () => {
          /* DESKTOP — full 3D rotateY gate entrance */
          gsap.set('.ld-steps', { perspective: 1000 })
          gsap.from(stepsEl, {
            opacity: 0, y: 64, rotateY: -12, transformOrigin: 'left center',
            stagger: 0.15, duration: 1, ease: 'expo.out',
            scrollTrigger: { trigger: '.ld-steps', start: 'top 82%', toggleActions: 'play none none reverse' },
          })
          gsap.from('.ld-step-icon', {
            scale: 0, rotation: -24, stagger: 0.15, duration: 0.7, ease: 'back.out(2.2)',
            scrollTrigger: { trigger: '.ld-steps', start: 'top 82%', toggleActions: 'play none none reverse' },
          })
          gsap.from('.ld-step-num', {
            opacity: 0, x: -18, stagger: 0.15, duration: 0.55, ease: 'power2.out',
            scrollTrigger: { trigger: '.ld-steps', start: 'top 82%', toggleActions: 'play none none reverse' },
          })
          document.querySelectorAll('.ld-step-h3').forEach((el) => {
            const split = new SplitText(el, { type: 'words' })
            gsap.from(split.words, {
              opacity: 0, y: 22, stagger: 0.06, duration: 0.65, ease: 'power2.out',
              scrollTrigger: { trigger: el, start: 'top 88%', toggleActions: 'play none none reverse' },
              onComplete() { split.revert() },
            })
          })
          document.querySelectorAll('.ld-step-points').forEach((list) => {
            gsap.from(list.querySelectorAll('.ld-step-point'), {
              opacity: 0, x: -18, stagger: 0.08, duration: 0.5, ease: 'power2.out',
              scrollTrigger: { trigger: list, start: 'top 88%', toggleActions: 'play none none reverse' },
            })
          })
        })
      }

      /* ─────────────────────────────────────────────────────────────
         10. PATH CARDS — dramatic gate-swing entrance + accent bar wipe
             Left card swings in from left · Right card from right
             Top accent bar wipes across with DrawSVG-style scaleX
      ───────────────────────────────────────────────────────────── */
      const pathCards = document.querySelectorAll('.ld-path-card')
      if (pathCards.length) {
        gsap.set('.ld-path-grid', { perspective: 1400 })

        pathCards.forEach((card, i) => {
          const fromX   = i === 0 ? -110 : 110
          const fromRot = i === 0 ? -18  : 18

          /* Gate swing — card rotates in around Y axis from its respective side */
          gsap.fromTo(card,
            { opacity: 0, x: fromX, rotateY: fromRot, scale: 0.86, transformOrigin: i === 0 ? 'right center' : 'left center' },
            {
              opacity: 1, x: 0, rotateY: 0, scale: 1,
              transformOrigin: 'center center',
              duration: 1.05, ease: 'ld.gate',
              delay: i * 0.22,
              scrollTrigger: { trigger: '.ld-path-grid', start: 'top 83%', toggleActions: 'play none none reverse' },
            },
          )

          /* Accent bar wipes from left to right (scaleX 0→1) */
          const accent = card.querySelector('.ld-path-accent')
          if (accent) {
            gsap.fromTo(accent,
              { scaleX: 0, transformOrigin: 'left center' },
              {
                scaleX: 1, duration: 0.85, ease: 'power3.out',
                delay: i * 0.22 + 0.35,
                scrollTrigger: { trigger: '.ld-path-grid', start: 'top 83%', toggleActions: 'play none none reverse' },
              },
            )
          }

          /* Card body content staggers in */
          const children = card.querySelectorAll('.ld-path-tag, .ld-path-h3, .ld-path-desc, .ld-path-cta')
          gsap.from(children, {
            opacity: 0, y: 24, stagger: 0.09, duration: 0.6, ease: 'power2.out',
            delay: i * 0.22 + 0.5,
            scrollTrigger: { trigger: '.ld-path-grid', start: 'top 83%', toggleActions: 'play none none reverse' },
          })

          /* Flip-based hover */
          card.addEventListener('mouseenter', () => {
            const state = Flip.getState(card)
            card.classList.add('ld-path-card--active')
            Flip.from(state, { duration: 0.32, ease: 'power2.out', absolute: true })
          })
          card.addEventListener('mouseleave', () => {
            const state = Flip.getState(card)
            card.classList.remove('ld-path-card--active')
            Flip.from(state, { duration: 0.45, ease: 'elastic.out(1, 0.5)', absolute: true })
          })
        })
      }

      /* ─────────────────────────────────────────────────────────────
         11. SOCIAL PROOF — quote cards cascade + SplitText
      ───────────────────────────────────────────────────────────── */
      gsap.from('.ld-quote-card', {
        opacity: 0, y: 55, scale: 0.95,
        stagger: { amount: 0.4, grid: [2, 2] },
        duration: 0.8, ease: 'expo.out',
        scrollTrigger: { trigger: '.ld-proof-grid', start: 'top 84%', toggleActions: 'play none none reverse' },
      })
      gsap.from('.ld-quote-mark', {
        scale: 0, opacity: 0, rotation: -40,
        stagger: 0.1, duration: 0.6, ease: 'back.out(3)',
        scrollTrigger: { trigger: '.ld-proof-grid', start: 'top 84%', toggleActions: 'play none none reverse' },
      })
      document.querySelectorAll('.ld-quote-text').forEach((el) => {
        const split = new SplitText(el, { type: 'lines' })
        gsap.from(split.lines, {
          opacity: 0, y: 16, stagger: 0.08, duration: 0.55, ease: 'power2.out',
          scrollTrigger: { trigger: el, start: 'top 88%', toggleActions: 'play none none reverse' },
          onComplete() { split.revert() },
        })
      })

      /* ─────────────────────────────────────────────────────────────
         12. FORM SECTION
      ───────────────────────────────────────────────────────────── */
      gsap.from('.ld-form-header > *', {
        opacity: 0, y: 28, stagger: 0.12, duration: 0.75, ease: 'expo.out',
        scrollTrigger: { trigger: '.ld-form-header', start: 'top 86%', toggleActions: 'play none none reverse' },
      })
      gsap.from('.ld-form-card', {
        opacity: 0, y: 48, scale: 0.97, duration: 0.9, ease: 'expo.out',
        scrollTrigger: { trigger: '.ld-form-card', start: 'top 85%', toggleActions: 'play none none reverse' },
      })
      gsap.from('.ld-form-trust-item', {
        opacity: 0, y: 16, stagger: 0.1, duration: 0.5, ease: 'power2.out',
        scrollTrigger: { trigger: '.ld-form-trust-row', start: 'top 92%', toggleActions: 'play none none reverse' },
      })

      /* ─────────────────────────────────────────────────────────────
         13. FOOTER CTA — SplitText H2 + ScrambleText sub
      ───────────────────────────────────────────────────────────── */
      const ctaH2 = document.querySelector('.ld-footer-cta-h2')
      if (ctaH2) {
        const split = new SplitText(ctaH2, { type: 'words' })
        gsap.set(ctaH2, { perspective: 700 })
        gsap.from(split.words, {
          opacity: 0, y: 50, rotateX: -30, stagger: 0.07, duration: 0.95, ease: 'expo.out',
          scrollTrigger: { trigger: ctaH2, start: 'top 86%', toggleActions: 'play none none reverse' },
          onComplete() { split.revert() },
        })
      }
      const ctaSub = document.querySelector('.ld-footer-cta-sub')
      if (ctaSub) {
        const finalSub = ctaSub.textContent
        ScrollTrigger.create({
          trigger: ctaSub, start: 'top 88%', once: true,
          onEnter() {
            gsap.to(ctaSub, { duration: 1.1, scrambleText: { text: finalSub, chars: 'lowercase', speed: 0.4 } })
          },
        })
      }
      gsap.from('.ld-footer-cta-btns > *', {
        opacity: 0, y: 22, scale: 0.92, stagger: 0.12, duration: 0.65, ease: 'ld.back',
        scrollTrigger: { trigger: '.ld-footer-cta-btns', start: 'top 92%', toggleActions: 'play none none reverse' },
      })

      /* ─────────────────────────────────────────────────────────────
         14. FOOTER
      ───────────────────────────────────────────────────────────── */
      gsap.from('.ld-footer-inner > *', {
        opacity: 0, y: 18, stagger: 0.08, duration: 0.55, ease: 'power2.out',
        scrollTrigger: { trigger: '.ld-footer', start: 'top 96%' },
      })

      /* ─────────────────────────────────────────────────────────────
         15. NAV FLIP on scroll state change
      ───────────────────────────────────────────────────────────── */
      ScrollTrigger.create({
        trigger: 'body', start: 'top -20px',
        onEnter() {
          const state = Flip.getState('.ld-nav-logo')
          document.querySelector('.ld-nav')?.classList.add('scrolled')
          Flip.from(state, { duration: 0.3, ease: 'power2.out' })
        },
        onLeaveBack() {
          const state = Flip.getState('.ld-nav')
          document.querySelector('.ld-nav')?.classList.remove('scrolled')
          Flip.from(state, { duration: 0.3, ease: 'power2.out' })
        },
      })

      /* ─────────────────────────────────────────────────────────────
         16. MAGNETIC BUTTONS — all primary CTAs
      ───────────────────────────────────────────────────────────── */
      document.querySelectorAll('.ld-btn-primary, .ld-nav-cta').forEach((btn) => {
        btn.addEventListener('mousemove', (e) => {
          const r = btn.getBoundingClientRect()
          const x = e.clientX - r.left - r.width / 2
          const y = e.clientY - r.top - r.height / 2
          gsap.to(btn, { x: x * 0.18, y: y * 0.18, duration: 0.3, ease: 'power2.out' })
        })
        btn.addEventListener('mouseleave', () => {
          gsap.to(btn, { x: 0, y: 0, duration: 0.5, ease: 'elastic.out(1, 0.5)' })
        })
      })

    }) // end gsap.context

    return () => {
      ctx.revert()
      mm.revert()
    }
  }, [])

  return null
}
