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
