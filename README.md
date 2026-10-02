# Binder

Your AI administrative agent, running entirely on your computer.

Drop in your bills, notices, payslips and certificates. Binder's AI files them, reads the key
information (amount, dates, reference, sender), tells you what needs your attention and by when,
explains letters in plain language, answers your questions about your documents and acts for you:
reminders, complete letters, application files, payments to mark, and spots what is wrong or
missing before you do.

**Everything stays on your computer.** Your documents and the database are encrypted, and the
AI runs locally. Your documents are never sent to an online service: when the AI looks up a
general fact on the web (a legal notice period, an official procedure), only a general search
leaves your computer, never your name, address, numbers or references. Each search appears in
your history.

**The law it quotes is checked the day it writes.** Before a letter is ready, Binder looks up
each legal point it relies on (articles, notice periods, deadlines) on official sites such as
service-public.gouv.fr. Under the letter you see which points were confirmed, and the sources.
If the official site says something different, Binder shows you its exact sentence and a
corrected wording you can put in the letter with one click; if a point could not be checked
(no internet, for example), it tells you to check it before sending.

- [Install](#install)
- [First steps](#first-steps)
- [Adding documents](#adding-documents)
- [Using Binder day to day](#using-binder-day-to-day)
- [Your data](#your-data)
- [Questions](#questions)

## Install

Download the installer for your system from the
[latest release](https://github.com/Razigue/Binder/releases/latest) and open it. On Windows,
Binder installs itself in a few seconds, with no question and no administrator rights, then
opens.

| System | Installer |
|---|---|
| Windows 10 / 11 | `BinderApp-windows-Setup.exe`, then Binder is in the Start menu and on the desktop |
| macOS | the `.pkg` file |
| Linux | the `.AppImage` file: make it executable (`chmod +x`), then open it |

If the release is not code-signed, the first launch asks for confirmation:
- **Windows**: SmartScreen shows "Windows protected your PC": click **More info**, then **Run
  anyway**.
- **macOS**: right-click the installer, then **Open**.

Binder updates itself: at launch it checks for a newer version, downloads only what changed and
restarts. Without internet, it simply starts as usual. To uninstall it, use your system's usual
way (Windows: Settings > Apps); your documents stay in place (see [Your data](#your-data)).

## First steps

1. **Open Binder.** The welcome screen asks three things, one tap each: your situation
   (student, employee, self-employed, looking for work, retired), where you live (renting,
   owning, housed by someone) and whether you have a vehicle. Binder then lists **the papers
   you should have**: why each one matters, how long to keep it, and which ones are missing.
   Scan your first paper with your phone, or choose a file. No document at hand? Click **Load
   demo documents** to explore with fictitious examples. Moving to a new computer? Click
   **Restore a backup** (see [Your data](#your-data)). The list stays in **My papers**, where
   you can change your answers.
2. **That's it.** Binder gets its AI ready on its own the first time: it sets up its local AI
   engine, picks the model that suits your computer and downloads it. The **To do** page shows
   the progress; Binder keeps working meanwhile. The engine is part of Binder: nothing else to
   start, and it stops when you close Binder.

Language, country and theme follow your system.

## Adding documents

Accepted formats: PDF, JPG, PNG.

- **Drag and drop** files anywhere, or use **Add documents**.
- **Scan with your phone**: in the add window, click **Scan with my phone**, connect the phone to
  the same Wi-Fi as your computer and scan the QR code. Each page is captured automatically when
  you hold still. The phone warns that the connection is not private: that is expected, the page
  comes from Binder on your own network. Tap **Advanced**, then **Proceed** (once per phone).
- **Mailbox**: in **Settings** (in the profile menu), enter your email address and an app password.
  Binder imports the attachments of new messages every 5 minutes. It only reads: it never deletes
  your emails nor marks them as read.
- **About you**: Binder fills in your name, address, email and mobile from your documents
  (**Settings**, never over what you typed). Tell it about your situation there or in a
  sentence to the agent ("I'm a tenant, two children"): it keeps it in mind.
- **Synced folder**: in **Settings**, point Binder at your scanner's or cloud drive's folder:
  every PDF, JPG or PNG that lands in it is imported.

After each import, Binder tells you **what it did**: where each document went, what it asks of
you (amount and date to pay, renewal), what it did on its own (replaced an older version, noticed
a price rise, applied one of your past corrections) and the questions it still has.

Once a document is in, Binder:
- files it under one of seven areas (Housing, Money, Work & benefits, Family, Health, Identity,
  Vehicle) and recognises its type (invoice, certificate, identity card, loan statement, donation
  receipt, childcare certificate, fine, purchase invoice and its warranty…);
- reads the amount, dates, reference, sender and the person it concerns;
- recognises the people of your household from the documents themselves;
- gives it a clear name, "YYYY-MM-DD Title Sender.pdf", used when you download or export it;
- ignores exact copies, and asks you about a probable duplicate;
- keeps the latest version of a certificate or identity document and marks the older one as
  replaced, without deleting it. Payslips are all kept.

When Binder is unsure, and only if the answer changes something today (a payment coming up, an
identity card or a contract still valid, a bill it follows), it asks **one short question**,
with the likely answers as buttons ("Where does this go?", "What is the amount?" with the
amounts it saw). Open a question to answer it with the document beside it, the place Binder
read highlighted. Old documents are never asked about, and a detail that has no effect is
simply left "not filled in". The same question about several documents of one sender comes
as one card ("These 6 Free bills go in Housing?"). At most three questions are shown at a
time; the others wait, already filed, until you choose to answer them. When you correct
something yourself, Binder remembers it for the next documents from the same sender.

Photos and scans are read by the built-in text recognition (OCR), on your computer. With the
local AI, Binder also looks at the page itself, like you would.

Documents you add while the local AI is still being set up are kept safe and marked "Waiting for
the AI": Binder reads and files them on its own as soon as it is ready.

## Using Binder day to day

Binder has three places: **To do**, **My papers** and **Life events**. The **＋ Add** button,
on every page, adds a paper (scan it with your phone, or choose a file) or asks Binder a
question (Ctrl K does too). **Settings**, **History** and **Trash** are in the profile menu.
On a phone, the three places and ＋ sit in a bar at the bottom of the screen.

**To do** greets you with one sentence on your day, then a pile of cards, the most urgent on
top. Each card says what it is, what to do and by when, with its button:
- payments due soon or late ("It's paid"), documents to renew;
- anomalies: billed or debited twice, an unusually high catch-up bill, an overpayment claimed by
  the CAF or owed to you, a price rise, a lower payslip; Binder offers to write the letter;
- missing documents: a monthly bill that did not arrive, a missing payslip, this year's tax
  notice, a new insurance certificate;
- suggestions: compare an insurance before it renews, archive old papers (past their retention
  period or replaced by a newer version), follow up a letter that got no answer;
- at most three short questions from Binder (see above).

When nothing needs you, To do says **All in order ✓**.

Binder also sends **system notifications** for urgent deadlines, anomalies, documents arriving
by email and the weekly briefing, while it is open.

**Life events** starts from what is happening to you: "I'm moving", "I'm starting a job", "We're
having a child", "I'm retiring", "A loved one has died", "I got a letter I don't understand",
"I want to stop a subscription", "I want to dispute a bill or a fine". Each one opens what
Binder can do about it: a checklist, the letters, the files to put together, a question to ask.
Other procedures (the income tax return, renewing an ID card, a mortgage file, any other letter
or file) sit below. On top, **In progress** follows what is under way: checklists and letters
(to send, awaiting an answer, to follow up). Letters you sent show when Binder plans the
reminder; once the date has passed, **Write a reminder** drafts it, and **I got an answer**
closes the letter.

**Checklists** ("Moving house", "A birth", "Death of a relative", "Income tax return"): Binder
builds them from your own documents, each step with its deadline:
the suppliers, bank and insurers to tell about a move (one tap writes each letter, and the step
ticks itself once you mark the letter as sent), the time limits after a birth or a death, the
donation and childcare receipts of the year with their total and the boxes to fill in. The next
steps also appear in To do. You can ask for it in words too: "We're moving on 15 December".

**My papers**: the seven areas (Housing, Money, Work & benefits, Family, Health, Identity,
Vehicle) as tiles that say their state in words: "Up to date", "Identity card: renew it",
"Tax notice 2026 · Due 7 Oct". Tap a tile to see only its documents, or filter by household
member. The search reads the documents' content (a sender, a reference, a word on the page); a
search can also go to Binder as a question in one click. Three tabs:
- **Documents**: everything Binder has filed, by year;
- **Calendar**: your deadlines on a timeline, then the **administrative year** (in France): what
  comes back each month (the tax return in April, the property tax in October…), marked when your
  papers show it concerns you;
- **Archives**: old papers, still readable (see below).

Open a document to see its preview: hover a field (amount, due date…) and Binder **highlights
where it read it** on the page. **In short** explains the letter in plain language. Right after
an import, each new paper gets one line saying what it is, whether to act and by when, and how
long it is kept.

**Words of paperwork** (RIB, rent receipt, tax notice, overpayment, formal notice…) are
underlined with dots: tap one for a one-sentence explanation.

**Letters**: **Print** and **Send by post** come first (the steps: print, sign, envelope,
stamp or registered mail, then "I sent it"); **Download (PDF)** is there too.

**Text size**: Settings > Appearance offers Normal, Large and Larger.

**Ask Binder**: ＋ Add, then **Ask a question**, on every page, or Ctrl K. Ask in your own words,
it looks
through your documents and acts for you:
- questions: "What is my reference tax income?", "How much did I pay for electricity over my
  last two bills?";
- follow-up: "Do I have papers to renew soon?", "Is anything wrong or missing?";
- actions: "Remind me to renew my ID card a month before it expires", "I paid the property tax";
- letters for any purpose: "Write to EDF to pay the catch-up bill in three instalments",
  "Dispute the CAF overpayment". The common ones (cancellation, complaint, payment plan,
  challenging a fine, a tax or a CAF decision, formal notice, change of address) carry the legal
  points and time limits that apply. The letter is complete, with your name and address and the
  organisation's, as found in your documents; download it as a PDF, tell Binder you sent it, and
  it suggests a reminder letter if no answer comes;
- files for any purpose: "Prepare my rental application", "renew my passport", "school
  enrolment", "my retirement claim", "the file for the nursery". Binder lists
  what is ready, missing or too old, and gives a ZIP.

Each answer cites the documents it comes from; click a citation to open it.

**Undo**: every action (yours or Binder's) can be undone right after, from the message that
confirms it, or by asking "undo that". **History** and **Trash** are in the profile menu.

## Your data

Binder keeps everything in one folder on your computer:

| System | Folder |
|---|---|
| Windows | `%LOCALAPPDATA%\Binder` |
| macOS | `~/Library/Application Support/Binder` |
| Linux | `~/.local/share/binder` |

**Automatic backup.** Once a day, when something changed, Binder saves an encrypted copy of your
library in `Documents/Binder backups` (the last 7 are kept). **Settings** shows
your **recovery code**: write it down and keep it away from the computer. With it, a backup opens
on any computer (**Restore a backup** on the welcome screen); without it, nobody can read the
backup, not even you. If your Documents folder is synced to a cloud, the backups it receives stay
encrypted.

Your mailbox password is stored in the encrypted database, on this computer only.

## Questions

**Does Binder need internet?** Only to check for updates, to download its AI the first time (the
Ollama engine and the model), and when the AI searches the web for general information. Your
documents are never sent anywhere.

**A document is in the wrong area or has a wrong amount.** Open it, correct the information,
then click **Save and validate**. Binder applies the same correction to the next documents from
that sender.

**Can I undo something?** Yes: right after any action, click **Undo**. A document in the
**Trash** can be restored as long as you have not deleted it permanently.

**What happens to old papers?** Binder never deletes them. Once a paper is past its retention
period, or replaced by a newer version, Binder offers to **archive** it (a paper imported
already that old is archived straight away). Archived papers leave your to-do list, alerts and
files, but stay encrypted on your computer: find them in the **Archives** tab, search them,
download them or bring them back in one click.

**Which AI model will my computer get?** The best one it runs comfortably:

| Your computer | Model |
| --- | --- |
| Graphics card with 20 GB or more, or a Mac with 48 GB or more | Qwen 3.6 · 27B (18 GB download) |
| 32 GB of memory or more, counting the graphics card's (a Mac: its memory) | Qwen 3.6 · 35B-A3B (23 GB) |
| Graphics card with 8 GB, or 16 GB of memory | Qwen 3.5 · 9B (6.6 GB) |
| 10 to 16 GB of memory | Qwen 3.5 · 4B (3.4 GB) |
| Less | Qwen 3.5 · 2B (2.7 GB) |

The 35B-A3B only puts about 3 billion of its 35 billion parameters to work on each word, so it
stays fast even without a graphics card. Short on disk space, Binder takes the next model down.
At each launch Binder checks your computer again: if you added memory or a graphics card, it
offers a better model on the **To do** page, with its download size, and switches once it is
downloaded (the previous one stays installed). Say **No thanks** and it will not ask again
unless an even better model suits your computer. Binder never moves you to a smaller model on
its own: it only warns you if the model in use has become too heavy. **Settings > Local AI**
shows the model in use and the one best suited to your computer.

**Would a less compressed model read better?** The models Binder downloads are quantized to
4 bits (Q4), the best trade-off for most computers. To measure what an 8-bit version (Q8) would
change on your machine, from the `backend` folder of the source code (a Q8 tag of the model,
listed on ollama.com, e.g. `qwen3.5:9b-q8_0`):

```bash
ollama pull qwen3.5:9b-q8_0
uv run python scripts/evaluate.py --llm --report q4.json
uv run python scripts/evaluate.py --llm --model qwen3.5:9b-q8_0 --report q8.json
```

Both reports give the accuracy per field and the time per document; add `--corpus <folder>`
to measure on your own annotated documents (see [docs/evaluation.md](docs/evaluation.md)).

---

Developers: see [docs/development.md](docs/development.md),
[docs/configuration.md](docs/configuration.md), [docs/models.md](docs/models.md) and
[docs/release.md](docs/release.md).
