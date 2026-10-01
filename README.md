# Binder

Your AI administrative agent, running entirely on your computer.

Drop in your bills, notices, payslips and certificates. Binder's AI files them, reads the key
information (amount, dates, reference, sender), tells you what needs your attention and by when,
explains letters in plain language, answers your questions about your documents and acts for you:
reminders, letters, folders, payments to mark.

**Everything stays on your computer.** Your documents and the database are encrypted, and the
AI runs locally. Nothing is sent to an online service.

- [Install](#install)
- [First steps](#first-steps)
- [Adding documents](#adding-documents)
- [Using Binder day to day](#using-binder-day-to-day)
- [Settings](#settings)
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
   hand? Click **Load demo documents** to explore with fictitious examples.
2. **Turn on the local AI.** It is what reads, files and explains your documents, and what powers
   the agent.
   1. Install [Ollama](https://ollama.com) and start it.
   2. In **Settings → Local AI**, pick a Qwen model (the **Recommended** one suits most
      computers) and click **Download**. Binder uses it as soon as it is ready.
   3. Also download **Qwen 3 Embedding** (0.6 GB) for smart search: it finds documents by
      meaning ("proof of address" finds your rent receipt and energy bills).
3. **Check your language and country** in **Settings → Language & region**. The country sets the
   currency and date formats, and the language of your letters.

## Adding documents

Accepted formats: PDF, JPG, PNG.

- **Drag and drop** files onto the Home page, or use **+ Import**.
- **Scan with your phone**: click **Scan with my phone**, connect the phone to the same Wi-Fi as
  your computer and scan the QR code. Each page is captured automatically when you hold still.
  The phone warns that the connection is not private: that is expected, the page comes from Binder
  on your own network. Tap **Advanced**, then **Proceed** (once per phone). If the phone cannot
  connect, allow Binder on private networks in your firewall.
- **Watched folder**: in **Settings → Automatic import**, choose a folder. Every PDF, JPG or PNG
  dropped in it (subfolders included) is imported.
- **Mailbox**: in the same section, enter your IMAP server and an app password. Binder imports the
  attachments of new messages every 5 minutes.

Binder only reads: it never moves your files, never deletes your emails and never marks them as
read.

Once a document is in, Binder:
- files it by category (Taxes, Energy, Insurance, Bank, Housing, Health, Social benefits, Work,
  Telecom, Identity, Vehicle) and recognises its type (invoice, certificate, identity card…);
- reads the amount, dates, reference and sender, with a confidence score;
- gives it a clear name, "YYYY-MM-DD Title Sender.pdf", used when you download or export it;
- ignores exact copies, and flags a probable duplicate (another scan of the same letter);
- keeps the latest version of a certificate or identity document and marks the older one as
  replaced, without deleting it. Payslips are all kept.

When something is missing or doubtful, the document goes to **To review**: open it, check or
correct the information, then click **Validate**.

Photos and scans are read by the built-in text recognition (OCR), on your computer. With the
local AI, Binder also looks at the page itself, like you would: it reads a crumpled photo, a table
or a stamp that text recognition gets wrong.

## Using Binder day to day

**Home** shows what needs your attention today: upcoming deadlines, documents to check, expiring
documents, price increases, and recent documents.

**Documents**: browse by category, open a document to see its preview, the extracted information
and its history. **In short** explains the letter in plain language: what it is, what to do, and
by when. From a document you can also write a letter, export it, or move it to the trash.

**Search**: finds any word in your documents, even inside their text. With smart search
installed, it also finds documents by meaning.

**Agent**: your paperwork assistant. Ask in your own words, it looks through your documents and
acts for you, and you see each step as it works:
- questions: "What is my reference tax income?", "How much did I pay for electricity over my
  last two bills?", "What is my car's registration number?";
- follow-up: "What should I do with this tax notice?", "Do I have papers to renew soon?",
  "What is missing for my rental application?", "Have my subscriptions gone up?";
- actions: "Remind me to renew my ID card a month before it expires", "I paid the property tax,
  mark it as paid", "The garage quote is €165, correct it", "Write a letter to cancel my Orange
  subscription", "Move last year's insurance certificate to the trash".

Each answer cites the documents it comes from; click a citation to open it. The agent only
changes something when you ask, logs it in **History**, and a trashed document can be restored.
Attach a file or take a photo in the conversation to ask about it straight away.

**Tracking**
- **Deadlines**: payments and expiry dates taken from your documents, in a list and a calendar.
  Mark a bill as paid, or add your own reminder ("Renew passport"). Identity documents are flagged
  ahead of time to leave room for renewal (90 days for an identity card, 120 for a passport).
- **Subscriptions**: recurring bills grouped by provider, with their frequency and a yearly
  estimate. Binder warns you when an amount rises by more than 10%.

**Paperwork**
- **Folders**: the documents a procedure needs (renting a home, a mortgage, CAF housing benefit).
  Binder shows what is ready, missing or too old, and exports the folder as a numbered ZIP.
- **Letters**: cancellation, dispute or document request, prefilled with the details of your
  documents. Fill in the parts in [square brackets], then copy or download. Letters to
  French-speaking administrations (France, Belgium, Luxembourg, Monaco) are always written in
  French.

**Upkeep**
- **Sorting**: documents you no longer need to keep, based on the recommended retention periods
  (service-public.fr). Nothing is deleted unless you choose to.
- **History**: everything Binder, the agent and you did, document by document.
- **Trash**: deleted documents stay here and can be restored. Deleting permanently asks for
  confirmation.

**Export**: from **Documents**, export everything (or one category) as a ZIP sorted by category and
year.

## Settings

| Section | What you can change |
|---|---|
| Language & region | English or French, country (currency, date format, letters). Automatic follows your system. |
| Appearance | Light, dark, or automatic (follows your system). |
| Local AI | Download, choose or delete a model; smart search model. |
| Automatic import | Watched folder and mailbox, and a **Check now** button. |

## Your data

Binder keeps everything in one folder on your computer:

| System | Folder |
|---|---|
| Windows | `%LOCALAPPDATA%\Binder` |
| macOS | `~/Library/Application Support/Binder` |
| Linux | `~/.local/share/binder` |

> ⚠️ **Back up the `key` file in this folder.** It unlocks your encrypted documents: without it,
> they cannot be recovered. To back up Binder, copy the whole folder while Binder is closed.

Your mailbox password is stored in the encrypted database, on this computer only.

## Questions

**Does Binder need internet?** No. It only connects to check for updates, and to download an AI
model when you ask for one.

**Which model should I choose?** The one marked **Recommended**. Smaller models are faster on
modest computers; the largest needs a powerful machine.

**A document is in the wrong category or has a wrong amount.** Open it, correct the information,
then click **Save and validate**. Binder keeps your correction.

**Can I undo a deletion?** Yes, from the **Trash**, as long as you have not deleted it permanently.

---

Developers: see [docs/development.md](docs/development.md),
[docs/configuration.md](docs/configuration.md) and [docs/release.md](docs/release.md).
