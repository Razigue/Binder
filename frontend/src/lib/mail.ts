// IMAP server of the usual providers, from the email address: the user only gives the address
// and an app password.
const IMAP_HOSTS: Record<string, string> = {
  "gmail.com": "imap.gmail.com",
  "googlemail.com": "imap.gmail.com",
  "outlook.com": "outlook.office365.com",
  "outlook.fr": "outlook.office365.com",
  "hotmail.com": "outlook.office365.com",
  "hotmail.fr": "outlook.office365.com",
  "live.com": "outlook.office365.com",
  "live.fr": "outlook.office365.com",
  "msn.com": "outlook.office365.com",
  "yahoo.com": "imap.mail.yahoo.com",
  "yahoo.fr": "imap.mail.yahoo.com",
  "icloud.com": "imap.mail.me.com",
  "me.com": "imap.mail.me.com",
  "orange.fr": "imap.orange.fr",
  "wanadoo.fr": "imap.orange.fr",
  "free.fr": "imap.free.fr",
  "sfr.fr": "imap.sfr.fr",
  "neuf.fr": "imap.sfr.fr",
  "laposte.net": "imap.laposte.net",
  "gmx.fr": "imap.gmx.net",
  "gmx.com": "imap.gmx.com",
}

export function imapHost(address: string): string {
  const domain = address.split("@")[1]?.trim().toLowerCase() ?? ""
  return IMAP_HOSTS[domain] ?? (domain ? `imap.${domain}` : "")
}
