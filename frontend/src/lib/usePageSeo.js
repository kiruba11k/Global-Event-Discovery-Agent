import { useEffect } from 'react'

const SITE_ORIGIN = 'https://www.expotofunnel.com'

// Sets a per-page <title>, <meta name="description"> and <link rel="canonical">,
// restoring the previous values on unmount so navigating away doesn't leave
// one page's metadata on another. `path` is the route path (e.g. '/pricing',
// '' for the homepage) - the canonical always points at that page's own URL,
// never a shared default.
export function usePageSeo(title, description, path = '') {
  useEffect(() => {
    const prevTitle = document.title
    document.title = title

    let metaDesc = document.querySelector('meta[name="description"]')
    const hadMetaDesc = !!metaDesc
    const prevDesc = metaDesc?.getAttribute('content') || ''
    if (!metaDesc) {
      metaDesc = document.createElement('meta')
      metaDesc.setAttribute('name', 'description')
      document.head.appendChild(metaDesc)
    }
    metaDesc.setAttribute('content', description)

    let canonical = document.querySelector('link[rel="canonical"]')
    const hadCanonical = !!canonical
    const prevHref = canonical?.getAttribute('href') || ''
    if (!canonical) {
      canonical = document.createElement('link')
      canonical.setAttribute('rel', 'canonical')
      document.head.appendChild(canonical)
    }
    canonical.setAttribute('href', `${SITE_ORIGIN}${path}`)

    return () => {
      document.title = prevTitle
      if (hadMetaDesc) metaDesc.setAttribute('content', prevDesc)
      if (hadCanonical) canonical.setAttribute('href', prevHref)
    }
  }, [title, description, path])
}
