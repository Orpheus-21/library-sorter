---
name: library-sorter
description: Sort a folder of books (PDF, EPUB, MOBI, AZW3, DJVU, CBZ, TXT, DOCX, or any file) into shelf folders by the Library of Congress Classification (LoC) or the Dewey Decimal Classification (DDC). Use this skill whenever the user wants to organize, shelve, catalogue, classify, or rearrange an ebook or book folder by LoC, Dewey, call numbers, or "library order", even if the user does not name a system. It reads the metadata, looks up the real call number online, and uses Claude's own judgment only when no record exists.
---

# Library Sorter

The user gives a folder of books. The skill puts the files on virtual shelves by LoC or Dewey call number.

A file can sit in one place only. So each run uses ONE system. The user chooses it. The user can run the skill again with the other system on a copy.

Every message to the user follows the `ste-replies` skill. Keep each question short. Ask in the order below.

## Step 1: Warn, then ask

Print this warning first, exactly in capitals:

> **WARNING: MAKE A FULL BACKUP OF ALL THE FILES BEFORE YOU CONTINUE. THIS SKILL CAN MOVE AND RENAME FILES. STORE THE BACKUP IN A DIFFERENT PLACE.**

Then call `AskUserQuestion` with these questions in one call:

1. Backup: "Do you have a backup of the folder?" Options: "Yes, I have a backup", "No". If the answer is "No", stop. Tell the user to make a backup first. Do not run any script.
2. System: "Which system must I use?" Options: "Library of Congress (LoC)", "Dewey Decimal (DDC)".
3. Place: "Where must the sorted files go?" Options: "In this folder (files move, no copies)", "In another folder (files are copied, originals stay)".

If the user chooses another folder, ask for the path in a plain message. Do not guess the path.

## Step 2: Scan

`<skill>` is the folder that holds this file. Use the scratchpad folder for temporary files.

```bash
python3 <skill>/scripts/scan.py "<folder>" -o <scratch>/manifest.json
```

The script is read-only. It reads the metadata of each file (title, author, ISBN). Then it asks Open Library for the call numbers. It accepts a title match only when the title is at least 80% similar. This protects against wrong books. Add `--offline` if the user has no network or asks for no online lookup.

A large folder takes time because of a 0.3 second pause per file. Run the command in the background if there are more than 200 files.

## Step 3: Fill the gaps with judgment

List the books that have no number for the chosen system. Keep the output small:

```bash
python3 -c "import json;m=json.load(open('<scratch>/manifest.json'));k='lcc' if '<system>'=='loc' else 'ddc'
[print(b['path'],'|',b['title'],'|',b['author']) for b in m['books'] if not b[k]]"
```

For each listed book, work as a cataloguer. Use the title, the author, and the file name. Write the call number for the chosen system only.

- Use a broad number when you are unsure. Example: `PS` for American literature, or `813` for American fiction. A wrong specific number is worse than a correct broad number.
- Leave a book out when you cannot tell what it is. The file then goes to `_Unsorted/`.
- Look at `meta_found: false` in the manifest. The title then comes from the file name, and the file name can be a poor guide.

Save the numbers in `<scratch>/guesses.json`. The format is `{"<path as in the manifest>": "<call number>"}`. The apply script marks these numbers as Claude guesses in its report.

## Step 4: Plan, confirm, apply

Run the plan. It changes nothing.

```bash
python3 <skill>/scripts/apply.py <scratch>/manifest.json --system loc|dewey [--dest "<other folder>"] --guesses <scratch>/guesses.json
```

Show the user the summary: the number of files, the number of guesses, the number of unsorted files, and a few example paths. Then ask for a go-ahead. After the user agrees, run the same command with `--execute`.

## Result layout

- LoC: `Q/QA/QA76.73.P98 - original name.pdf`
- Dewey: `500/510/515.35 - original name.pdf`
- No number: `_Unsorted/original name.pdf`

The call number is added in front of the original file name. A sorted file list then matches the shelf order. A name that collides gets `(2)`, `(3)`, and so on.

## After the run

Tell the user:

- How many files the skill placed with a real record, how many with a Claude guess, and how many it left unsorted.
- A move in place can be undone: `python3 <skill>/scripts/apply.py --undo "<folder>"`. This works until the user changes the sorted files by hand.
- A copy needs no undo. The user can delete the other folder.

## Limits

- Open Library has no record for every book. Rare, old, or private documents often get a Claude guess.
- The tool does not read text inside DJVU, CBZ, or scanned PDF files. It uses the file name for these.
- Dewey editions differ. The number from Open Library follows the edition that the record holds.
