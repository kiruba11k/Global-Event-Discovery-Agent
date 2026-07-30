// Blocks free/personal email providers from the ICP form's "work email"
// field - the report and any follow-up outreach are B2B, so a gmail/yahoo
// address isn't useful even when it's a technically valid email.
const FREE_EMAIL_DOMAINS = new Set([
  'gmail.com', 'googlemail.com',
  'yahoo.com', 'yahoo.co.uk', 'yahoo.co.in', 'ymail.com', 'rocketmail.com',
  'hotmail.com', 'outlook.com', 'live.com', 'msn.com',
  'icloud.com', 'me.com', 'mac.com',
  'aol.com',
  'protonmail.com', 'proton.me', 'pm.me',
  'zoho.com',
  'gmx.com', 'gmx.net',
  'mail.com', 'inbox.com',
  'rediffmail.com',
  'yandex.com', 'yandex.ru',
])

export function emailDomain(email) {
  const at = email.lastIndexOf('@')
  return at === -1 ? '' : email.slice(at + 1).trim().toLowerCase()
}

export function isFreeEmailDomain(email) {
  return FREE_EMAIL_DOMAINS.has(emailDomain(email))
}

// Best-effort company name guess from a work email's domain, used only as
// a last-resort fallback when the user hasn't typed a company name - e.g.
// "jane@acme-corp.io" -> "Acme Corp". Returns '' when nothing usable is
// left (so callers can fall back to an empty string rather than inventing
// a placeholder - the backend already renders "Your Company" for blank).
const TLD_TOKENS = new Set([
  'com', 'net', 'org', 'io', 'co', 'in', 'uk', 'us', 'ca', 'au',
  'biz', 'info', 'me', 'app', 'dev', 'ai', 'tech',
])

export function deriveCompanyNameFromEmail(email) {
  const domain = emailDomain(email)
  if (!domain) return ''
  const labels = domain.split('.').filter(Boolean)
  while (labels.length > 1 && TLD_TOKENS.has(labels[labels.length - 1])) labels.pop()
  const slug = labels[labels.length - 1] || ''
  if (!slug) return ''
  return slug
    .split(/[-_]/)
    .filter(Boolean)
    .map(w => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}
