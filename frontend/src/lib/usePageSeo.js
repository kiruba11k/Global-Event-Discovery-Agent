import { useEffect } from 'react'

const SITE_ORIGIN = 'https://www.expotofunnel.com'
const DEFAULT_IMAGE = `${SITE_ORIGIN}/images/og-expotofunnel.png`

function swapMeta(selector, createAttrs, content) {
  let el = document.head.querySelector(selector)
  const existed = !!el
  const prevContent = el?.getAttribute('content') ?? el?.getAttribute('href') ?? ''
  if (!el) {
    el = document.createElement(createAttrs.tag === 'link' ? 'link' : 'meta')
    Object.entries(createAttrs.attrs).forEach(([k, v]) => el.setAttribute(k, v))
    document.head.appendChild(el)
  }
  const valueAttr = createAttrs.tag === 'link' ? 'href' : 'content'
  el.setAttribute(valueAttr, content)
  return { el, existed, prevContent, valueAttr }
}

// Sets a per-page <title>, <meta name="description">, <link rel="canonical">,
// Open Graph + Twitter title/description/url, and (optionally) a noindex
// tag - restoring every previous value on unmount so navigating away
// doesn't leave one page's metadata on another. `path` is the route path
// (e.g. '/pricing', '' for the homepage) - the canonical/OG url always
// points at that page's own URL, never a shared default.
//
// `extra.ogTitle`/`extra.ogDescription` default to `title`/`description`
// when omitted - most pages want the same copy in both places, only a
// few (e.g. the homepage's punchier OG hook) need to diverge.
export function usePageSeo(title, description, path = '', extra = {}) {
  const { ogTitle = title, ogDescription = description, image = DEFAULT_IMAGE, noindex = false } = extra

  useEffect(() => {
    const prevTitle = document.title
    document.title = title

    const url = `${SITE_ORIGIN}${path}`
    const restores = [
      swapMeta('meta[name="description"]', { tag: 'meta', attrs: { name: 'description' } }, description),
      swapMeta('link[rel="canonical"]', { tag: 'link', attrs: { rel: 'canonical' } }, url),
      swapMeta('meta[property="og:title"]', { tag: 'meta', attrs: { property: 'og:title' } }, ogTitle),
      swapMeta('meta[property="og:description"]', { tag: 'meta', attrs: { property: 'og:description' } }, ogDescription),
      swapMeta('meta[property="og:url"]', { tag: 'meta', attrs: { property: 'og:url' } }, url),
      swapMeta('meta[property="og:image"]', { tag: 'meta', attrs: { property: 'og:image' } }, image),
      swapMeta('meta[name="twitter:title"]', { tag: 'meta', attrs: { name: 'twitter:title' } }, ogTitle),
      swapMeta('meta[name="twitter:description"]', { tag: 'meta', attrs: { name: 'twitter:description' } }, ogDescription),
    ]

    // Distinct name from the static index/follow default tag in
    // index.html - this one is added/removed per-page rather than
    // fighting over the same element's content.
    let robotsEl = null
    if (noindex) {
      robotsEl = document.createElement('meta')
      robotsEl.setAttribute('name', 'robots-page')
      robotsEl.setAttribute('content', 'noindex, nofollow')
      document.head.appendChild(robotsEl)
    }

    return () => {
      document.title = prevTitle
      restores.forEach(({ el, existed, prevContent, valueAttr }) => {
        if (existed) el.setAttribute(valueAttr, prevContent)
        else el.remove()
      })
      if (robotsEl) robotsEl.remove()
    }
  }, [title, description, path, ogTitle, ogDescription, image, noindex])
}
