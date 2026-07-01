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

          /* ── HERO — cinematic 3D entrance, not PDF-like static copy ─── */
          const h1 = document.querySelector('.hp-hero-solo-h1')
          if (h1 && !h1.dataset.gsapSplit) {
            h1.dataset.gsapSplit = 'true'
            const walker = document.createTreeWalker(h1, NodeFilter.SHOW_TEXT)
            const textNodes = []
            let node
            while ((node = walker.nextNode())) textNodes.push(node)
            textNodes.forEach(textNode => {
              const fragment = document.createDocumentFragment()
              textNode.textContent.split(/(\s+)/).forEach(part => {
                if (!part) return
                if (/^\s+$/.test(part)) {
                  fragment.appendChild(document.createTextNode(part))
                  return
                }
                const span = document.createElement('span')
                span.className = 'hp-hero-line'
                span.textContent = part
                fragment.appendChild(span)
              })
              textNode.parentNode.replaceChild(fragment, textNode)
            })
          }

          gsap.fromTo('.hp-hero-eyebrow',
            { y: 24, opacity: 0, rotateX: -12, filter: 'blur(8px)' },
            { y: 0, opacity: 1, rotateX: 0, filter: 'blur(0px)', duration: 0.75, ease: 'power3.out', delay: 0.08 }
          )

          gsap.fromTo('.hp-hero-line',
            { y: 42, z: -80, opacity: 0, rotateX: 22, filter: 'blur(7px)' },
            { y: 0, z: 0, opacity: 1, rotateX: 0, filter: 'blur(0px)', stagger: 0.035, duration: 0.95, ease: 'power4.out', delay: 0.14 }
          )

          gsap.fromTo('.hp-hero-solo-sub',
            { y: 28, opacity: 0, rotateX: 10, filter: 'blur(6px)' },
            { y: 0, opacity: 1, rotateX: 0, filter: 'blur(0px)', duration: 0.9, ease: 'power3.out', delay: 0.42 }
          )

          gsap.fromTo('.hp-hero-visual-col',
            { x: 44, z: -120, opacity: 0, rotateY: -16, scale: 0.92 },
            { x: 0, z: 0, opacity: 1, rotateY: 0, scale: 1, duration: 1.05, ease: 'expo.out', delay: 0.32 }
          )

          gsap.fromTo(['.hp-validator-badge', '.hp-hero-bridge'],
            { y: 26, opacity: 0, rotateX: 9 },
            { y: 0, opacity: 1, rotateX: 0, stagger: 0.12, duration: 0.8, ease: 'power3.out', delay: 0.58 }
          )

          gsap.fromTo('.hp-form-zone',
            { y: 34, z: -80, opacity: 0, rotateX: 12, scale: 0.97, filter: 'blur(8px)' },
            { y: 0, z: 0, opacity: 1, rotateX: 0, scale: 1, filter: 'blur(0px)', duration: 1, ease: 'power4.out', delay: 0.72 }
          )

          gsap.fromTo('.icp-form-root--hero .icp-field-group, .icp-form-root--hero .icp-submit-btn--hero',
            { y: 16, opacity: 0, rotateX: 8 },
            { y: 0, opacity: 1, rotateX: 0, stagger: 0.055, duration: 0.58, ease: 'power2.out', delay: 0.92 }
          )

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
