/*
  ScrollAnimations.jsx
  Comprehensive GSAP ScrollTrigger scrub animations for the entire homepage.
  All animations are bidirectional (scrub) so they reverse on scroll-up.
  Handles: hero text, nav, section headings, path cards, proof stats, pain cards, footer CTA.
*/

import { useEffect, useRef } from 'react'

export default function ScrollAnimations() {
  const initRef = useRef(false)

  useEffect(() => {
    if (initRef.current) return
    initRef.current = true

    let ctx = null

    const init = async () => {
      try {
        if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return

        const { gsap }          = await import('gsap')
        const { ScrollTrigger } = await import('gsap/ScrollTrigger')
        const { SplitText }     = await import('gsap/SplitText').catch(() => ({ SplitText: null }))
        gsap.registerPlugin(ScrollTrigger)
        if (SplitText) gsap.registerPlugin(SplitText)

        ctx = gsap.context(() => {

          /* ── Helper: stagger reveal from below ───────────────────── */
          const fromBelow = (targets, vars = {}) =>
            gsap.fromTo(targets,
              { y: vars.y ?? 40, opacity: 0 },
              {
                y: 0, opacity: 1,
                ease: vars.ease ?? 'power3.out',
                stagger: vars.stagger ?? 0,
                scrollTrigger: {
                  trigger:  vars.trigger ?? targets,
                  start:    vars.start   ?? 'top 88%',
                  end:      vars.end     ?? 'top 55%',
                  scrub:    vars.scrub   ?? 1.2,
                },
                ...vars.extra,
              }
            )

          /* ── NAV ─────────────────────────────────────────────────── */
          gsap.fromTo('.hp-nav',
            { y: -60, opacity: 0 },
            { y: 0, opacity: 1, ease: 'power2.out', duration: 0.9 }
          )

          /* ── HERO EYEBROW ─────────────────────────────────────────── */
          fromBelow('.hp-hero-eyebrow', {
            y: 24, start: 'top 95%', end: 'top 75%', scrub: 0.8,
          })

          /* ── HERO H1 — word-by-word scrub ────────────────────────── */
          const h1 = document.querySelector('.hp-hero-solo-h1')
          if (h1) {
            const words = [...h1.querySelectorAll('*')]
              .filter(el => el.childElementCount === 0)
              .reduce((acc, el) => {
                // wrap each text node word in a span
                return acc
              }, [])

            // Word split: wrap text-node words manually (no SplitText dep)
            const wrapWords = (el) => {
              const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT)
              const nodes = []
              let n
              while ((n = walker.nextNode())) nodes.push(n)
              nodes.forEach(node => {
                const words = node.textContent.split(/(\s+)/)
                const frag = document.createDocumentFragment()
                words.forEach(w => {
                  if (/^\s+$/.test(w)) {
                    frag.appendChild(document.createTextNode(w))
                  } else if (w) {
                    const span = document.createElement('span')
                    span.style.display = 'inline-block'
                    span.style.willChange = 'transform, opacity'
                    span.textContent = w
                    frag.appendChild(span)
                  }
                })
                node.parentNode.replaceChild(frag, node)
              })
              return el.querySelectorAll('span[style]')
            }

            const wordSpans = wrapWords(h1)
            if (wordSpans.length) {
              gsap.fromTo(wordSpans,
                { y: 32, opacity: 0 },
                {
                  y: 0, opacity: 1,
                  stagger: 0.04,
                  ease: 'power3.out',
                  scrollTrigger: {
                    trigger: h1,
                    start: 'top 92%',
                    end:   'top 55%',
                    scrub: 1,
                  },
                }
              )
            }
          }

          /* ── HERO SUB PARAGRAPH ──────────────────────────────────── */
          fromBelow('.hp-hero-solo-sub', {
            y: 28, start: 'top 90%', end: 'top 60%', scrub: 1,
          })

          /* ── VALIDATOR BADGE ─────────────────────────────────────── */
          fromBelow('.hp-validator-badge', {
            y: 24, start: 'top 92%', end: 'top 62%', scrub: 1,
          })

          /* ── BRIDGE LINE ─────────────────────────────────────────── */
          gsap.fromTo('.hp-hero-bridge',
            { x: -30, opacity: 0 },
            {
              x: 0, opacity: 1, ease: 'power2.out',
              scrollTrigger: {
                trigger: '.hp-hero-bridge',
                start: 'top 90%', end: 'top 65%', scrub: 1,
              },
            }
          )

          /* ── FORM ZONE — scale in ────────────────────────────────── */
          gsap.fromTo('.hp-form-zone',
            { scale: 0.96, opacity: 0, y: 20 },
            {
              scale: 1, opacity: 1, y: 0, ease: 'power2.out',
              scrollTrigger: {
                trigger: '.hp-form-zone',
                start: 'top 88%', end: 'top 58%', scrub: 1.2,
              },
            }
          )

          /* ── MICROCOPY + ESCAPE LINK ─────────────────────────────── */
          fromBelow(['.hp-microcopy', '.hp-escape-link'], {
            y: 14, start: 'top 90%', end: 'top 68%', scrub: 0.8, stagger: 0.2,
            trigger: '.hp-microcopy',
          })

          /* ── PATHS SECTION ───────────────────────────────────────── */
          fromBelow('.hp-section-eyebrow', {
            y: 20, start: 'top 88%', end: 'top 68%', scrub: 1,
            trigger: '.hp-paths',
          })
          fromBelow('.hp-section-title', {
            y: 28, start: 'top 85%', end: 'top 60%', scrub: 1.1,
            trigger: '.hp-paths',
          })
          fromBelow('.hp-paths-sub', {
            y: 20, start: 'top 82%', end: 'top 58%', scrub: 1,
            trigger: '.hp-paths',
          })

          /* Path cards — slide in from alternating sides */
          const pathCards = document.querySelectorAll('.hp-path-card')
          pathCards.forEach((card, i) => {
            gsap.fromTo(card,
              { x: i % 2 === 0 ? -50 : 50, opacity: 0, y: 20 },
              {
                x: 0, opacity: 1, y: 0, ease: 'power3.out',
                scrollTrigger: {
                  trigger: card,
                  start: 'top 88%',
                  end:   'top 55%',
                  scrub: 1.3,
                },
              }
            )
          })

          /* Path card content — staggered children reveal */
          pathCards.forEach(card => {
            const children = card.querySelectorAll('.hp-path-tag, .hp-path-title, .hp-path-desc, .hp-path-cta')
            gsap.fromTo(children,
              { y: 16, opacity: 0 },
              {
                y: 0, opacity: 1, stagger: 0.08, ease: 'power2.out',
                scrollTrigger: {
                  trigger: card,
                  start: 'top 82%',
                  end:   'top 45%',
                  scrub: 1.2,
                },
              }
            )
          })

          /* ── PROOF STATS ─────────────────────────────────────────── */
          const statItems = document.querySelectorAll('.hp-stat-item')
          statItems.forEach((item, i) => {
            gsap.fromTo(item,
              { y: 35, opacity: 0, scale: 0.92 },
              {
                y: 0, opacity: 1, scale: 1, ease: 'back.out(1.5)',
                scrollTrigger: {
                  trigger: '.hp-proof',
                  start: `top 85%`,
                  end:   `top 50%`,
                  scrub: 1 + i * 0.1,
                },
              }
            )
          })

          /* Proof numbers — count-up tied to scroll position */
          statItems.forEach(item => {
            const numEl = item.querySelector('.hp-stat-num')
            if (!numEl) return
            const text = numEl.textContent.trim()
            const match = text.match(/^(\D*)(\d[\d,]*)(\D*)$/)
            if (!match) return
            const [, pre, rawNum, suf] = match
            const target = parseInt(rawNum.replace(/,/g, ''), 10)
            if (isNaN(target) || target < 2) return

            gsap.fromTo({ v: 0 },
              { v: 0 },
              {
                v: target,
                ease: 'none',
                scrollTrigger: {
                  trigger: item,
                  start: 'top 85%',
                  end:   'top 40%',
                  scrub: 1.4,
                  onUpdate(self) {
                    const cur = Math.round(target * self.progress)
                    numEl.textContent = `${pre}${cur.toLocaleString()}${suf}`
                  },
                },
              }
            )
          })

          /* ── PAIN SECTION ────────────────────────────────────────── */
          fromBelow(document.querySelectorAll('.hp-pain .hp-section-eyebrow'), {
            y: 20, start: 'top 88%', end: 'top 68%', scrub: 1,
            trigger: '.hp-pain',
          })
          fromBelow(document.querySelectorAll('.hp-pain .hp-section-title'), {
            y: 28, start: 'top 85%', end: 'top 60%', scrub: 1.1,
            trigger: '.hp-pain',
          })
          fromBelow(document.querySelectorAll('.hp-pain-sub'), {
            y: 20, start: 'top 82%', end: 'top 58%', scrub: 1,
            trigger: '.hp-pain',
          })

          /* Pain cards — cascade with scrub */
          document.querySelectorAll('.hp-pain-card').forEach((card, i) => {
            gsap.fromTo(card,
              { y: 44, opacity: 0, rotateX: 6 },
              {
                y: 0, opacity: 1, rotateX: 0, ease: 'power3.out',
                scrollTrigger: {
                  trigger: card,
                  start: 'top 90%',
                  end:   'top 58%',
                  scrub: 1.2 + i * 0.08,
                },
              }
            )
          })

          /* ── TICKER — parallax speed boost ───────────────────────── */
          gsap.to('.hp-ticker-inner', {
            x: '-5%',
            ease: 'none',
            scrollTrigger: {
              trigger: '.hp-ticker-wrap',
              start: 'top bottom',
              end:   'bottom top',
              scrub: 1,
            },
          })

          /* ── FOOTER CTA ──────────────────────────────────────────── */
          const footerInner = document.querySelector('.hp-footer-cta-inner')
          if (footerInner) {
            const items = footerInner.querySelectorAll('.hp-section-eyebrow, .hp-footer-cta-h2, .hp-footer-cta-sub, .hp-footer-cta-btns')
            gsap.fromTo(items,
              { y: 36, opacity: 0 },
              {
                y: 0, opacity: 1, stagger: 0.12, ease: 'power3.out',
                scrollTrigger: {
                  trigger: footerInner,
                  start: 'top 88%',
                  end:   'top 50%',
                  scrub: 1.3,
                },
              }
            )
          }

          /* Footer CTA buttons — scale pop */
          gsap.fromTo('.hp-footer-cta-btns > *',
            { scale: 0.9, opacity: 0 },
            {
              scale: 1, opacity: 1, stagger: 0.1, ease: 'back.out(1.8)',
              scrollTrigger: {
                trigger: '.hp-footer-cta-btns',
                start: 'top 88%',
                end:   'top 60%',
                scrub: 1,
              },
            }
          )

          /* ── LOGO ticker fade-in ──────────────────────────────────── */
          gsap.fromTo('.hp-ticker-wrap',
            { opacity: 0 },
            {
              opacity: 1, ease: 'none',
              scrollTrigger: {
                trigger: '.hp-ticker-wrap',
                start: 'top 95%',
                end:   'top 75%',
                scrub: 0.8,
              },
            }
          )

          /* ── Section divider parallax ─────────────────────────────── */
          document.querySelectorAll('.hp-proof, .hp-paths, .hp-pain, .hp-footer-cta').forEach(section => {
            gsap.fromTo(section,
              { backgroundPositionY: '0%' },
              {
                backgroundPositionY: '20%', ease: 'none',
                scrollTrigger: {
                  trigger: section,
                  start: 'top bottom',
                  end:   'bottom top',
                  scrub: 1,
                },
              }
            )
          })

          /* ── App footer links ─────────────────────────────────────── */
          fromBelow('.hp-app-footer', {
            y: 20, start: 'top 98%', end: 'top 80%', scrub: 0.8,
          })

        }) // end gsap.context

      } catch (err) {
        /* GSAP unavailable — CSS fallback handles visibility */
      }
    }

    init()
    return () => { ctx?.revert() }
  }, [])

  return null // render-nothing component
}
