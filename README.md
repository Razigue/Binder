# Binder

Your AI administrative agent, running entirely on your computer.

Drop in your bills, notices, payslips and certificates. Binder's AI files them, reads the key
information (amount, dates, reference, sender), tells you what needs your attention and by when,
explains letters in plain language, answers your questions about your documents and acts for you:
reminders, complete letters, application files, payments to mark, and spots what is wrong or
missing before you do.

**Everything stays on your computer.** Your documents and the database are encrypted, and the
AI runs locally. Nothing is sent to an online service.

- [Install](#install)
- [First steps](#first-steps)
- [Adding documents](#adding-documents)
- [Using Binder day to day](#using-binder-day-to-day)
- [Your data](#your-data)
- [Questions](#questions)

## Install

Download the archive for your system from the
[latest release](https://github.com/Razigue/Binder/releases/latest), then extract it.

| System | Open |
|---|---|
| Windows 10 / 11 | `Binder\Binder.exe` |
| macOS | `Binder.app`: move it to **Applications** first |
| Linux | `Binder/Binder` |

Binder is not code-signed yet, so the first launch asks for confirmation:
- **Windows**: SmartScreen shows "Windows protected your PC": click **More info**, then **Run
  anyway**.
- **macOS**: right-click `Binder.app`, then **Open**.

Binder updates itself: at launch it checks for a newer version, downloads it, verifies it and
restarts. Without internet, it simply starts as usual.

## First steps

1. **Open Binder.** The welcome screen invites you to drop your first documents. No document at
   hand? Click **Load demo documents** to explore with fictitious examples. Moving to a new
   computer? Click **Restore a backup** (see [Your data](#your-data)).
2. **That's it.** Binder gets its AI ready on its own the first time: it installs the local AI
   engine (Ollama) if needed, picks the model that suits your computer and downloads it. The
   **Today** page shows the progress; Binder keeps working meanwhile.

Language, country and theme follow your system.

## Adding documents

Accepted formats: PDF, JPG, PNG.

- **Drag and drop** files anywhere, or use **Add documents**.
- **Scan with your phone**: in the add window, click **Scan with my phone**, connect the phone to
  the same Wi-Fi as your computer and scan the QR code. Each page is captured automatically when
  you hold still. The phone warns that the connection is not private: that is expected, the page
  comes from Binder on your own network. Tap **Advanced**, then **Proceed** (once per phone).
- **Mailbox**: in **Mailbox** (bottom of the menu), enter your email address and an app password.
  Binder imports the attachments of new messages every 5 minutes. It only reads: it never deletes
  your emails nor marks them as read.

After each import, Binder tells you **what it did**: where each document went, what it asks of
you (amount and date to pay, renewal), what it did on its own (replaced an older version, noticed
a price rise, applied one of your past corrections) and the questions it still has.

Once a document is in, Binder:
- files it under one of six areas (Housing, Money, Work & benefits, Health, Identity, Vehicle)
  and recognises its type (invoice, certificate, identity card…);
- reads the amount, dates, reference, sender and the person it concerns;
- recognises the people of your household from the documents themselves;
- gives it a clear name, "YYYY-MM-DD Title Sender.pdf", used when you download or export it;
- ignores exact copies, and asks you about a probable duplicate;
- keeps the latest version of a certificate or identity document and marks the older one as
  replaced, without deleting it. Payslips are all kept.

When Binder is unsure, it asks **one short question** on the Today page, with the likely answers
as buttons ("Where does this go?", "What is the amount?" with the amounts it saw). One tap and the
document is filed. When you correct something yourself, Binder remembers it for the next
documents from the same sender.

Photos and scans are read by the built-in text recognition (OCR), on your computer. With the
local AI, Binder also looks at the page itself, like you would.

## Using Binder day to day

**Today** shows what needs you, most urgent first, each with its one-tap actions:
- payments due soon or late ("It's paid"), documents to renew;
- anomalies: billed or debited twice, an unusually high catch-up bill, an overpayment claimed by
  the CAF or owed to you, a price rise, a lower payslip; Binder offers to write the letter;
- missing documents: a monthly bill that did not arrive, a missing payslip, this year's tax
  notice, a new insurance certificate;
- suggestions: compare an insurance before it renews, send old papers to the trash, follow up a
  letter that got no answer;
- every Monday, **your week** in a few sentences.

Binder also sends **system notifications** for urgent deadlines, anomalies, documents arriving
by email and the weekly briefing, while it is open.

**Areas**: Housing, Money, Work & benefits, Health, Identity and Vehicle each show what to do,
what is coming up, recurring bills with their yearly cost, and the documents by year (filter by
household member or by word). Open a document to see its preview: hover a field (amount, due
date…) and Binder **highlights where it read it** on the page. **In short** explains the letter in
plain language.

**Ask Binder**: the bar at the bottom of every page (Ctrl K). Ask in your own words, it looks
through your documents and acts for you:
- questions: "What is my reference tax income?", "How much did I pay for electricity over my
  last two bills?";
- follow-up: "Do I have papers to renew soon?", "Is anything wrong or missing?";
- actions: "Remind me to renew my ID card a month before it expires", "I paid the property tax";
- letters for any purpose: "Write to EDF to pay the catch-up bill in three instalments",
  "Dispute the CAF overpayment". The letter is complete, with your name and address and the
  organisation's, as found in your documents; download it as a PDF, tell Binder you sent it, and
  it suggests a reminder letter if no answer comes;
- files for any purpose: "Prepare my rental application", "the file for the nursery". Binder lists
  what is ready, missing or too old, and gives a ZIP.

Each answer cites the documents it comes from; click a citation to open it.

**Undo**: every action (yours or Binder's) can be undone right after, from the message that
confirms it, or by asking "undo that". **History** and **Trash** are at the bottom of the menu.

## Your data

Binder keeps everything in one folder on your computer:

| System | Folder |
|---|---|
| Windows | `%LOCALAPPDATA%\Binder` |
| macOS | `~/Library/Application Support/Binder` |
| Linux | `~/.local/share/binder` |

**Automatic backup.** Once a day, when something changed, Binder saves an encrypted copy of your
library in `Documents/Binder backups` (the last 7 are kept). The first time, the Today page shows
your **recovery code**: write it down and keep it away from the computer. With it, a backup opens
on any computer (**Restore a backup** on the welcome screen); without it, nobody can read the
backup, not even you. If your Documents folder is synced to a cloud, the backups it receives stay
encrypted.

Your mailbox password is stored in the encrypted database, on this computer only.

## Questions

**Does Binder need internet?** Only to check for updates and, the first time, to download its AI
(the Ollama engine and the model). Your documents are never sent anywhere.

**A document is in the wrong area or has a wrong amount.** Open it, correct the information,
then click **Save and validate**. Binder applies the same correction to the next documents from
that sender.

**Can I undo something?** Yes: right after any action, click **Undo**. A document in the
**Trash** can be restored as long as you have not deleted it permanently.

---

Developers: see [docs/development.md](docs/development.md),
[docs/configuration.md](docs/configuration.md) and [docs/release.md](docs/release.md).
