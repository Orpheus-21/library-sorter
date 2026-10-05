# library-sorter

A Claude Code skill that puts a folder of books on shelves. The shelves follow the Library of Congress Classification (LoC) or the Dewey Decimal Classification (DDC).

## What it does

The skill reads the title, the author, and the ISBN from each file. It asks Open Library for the call number of the book. If Open Library has no matching record, Claude gives a call number from the title and the author. The report marks each of these numbers as a guess.

The skill then sorts the files into folders by call number. A file can sit in one place only, so one run uses one system. The user chooses LoC or Dewey for each run.

The skill asks the user for a backup before it does anything. It shows a dry run before it changes a file.

## Requirements

* Python 3.8 or later. The scripts use only the standard library.
* Claude Code, to use the skill by name.
* A network connection, for the Open Library lookup. The `--offline` flag turns the lookup off.
* Optional: `pdfinfo` and `pdftotext` from the `poppler` package. Without them, the scripts read no metadata from PDF files and use the file name.

## Install

1. Clone this repo into the skills folder of Claude Code:

   ```
   git clone <URL of this repo> ~/.claude/skills/library-sorter
   ```

2. Start a new Claude Code session. The skill is then available.

If you have no remote URL, copy the folder of this repo to `~/.claude/skills/library-sorter`.

## Usage

Tell Claude Code to sort a folder of books. Example:

```
Sort the books in ~/Books by the Dewey Decimal system.
```

Claude then follows these steps:

1. Claude prints a warning to make a backup and asks you to confirm.
2. Claude asks which system to use: LoC or Dewey.
3. Claude asks where the sorted files go: in the same folder (files move), or in another folder (files are copied).
4. Claude scans the folder and looks up the call numbers.
5. Claude shows the dry run. You agree or stop.
6. Claude applies the plan.

### Scripts

You can run the scripts without Claude. The scan writes a manifest and changes no file:

```
python3 scripts/scan.py "<folder>" -o manifest.json
```

Add `--offline` to skip the Open Library lookup.

The apply script shows a dry run by default:

```
python3 scripts/apply.py manifest.json --system loc
python3 scripts/apply.py manifest.json --system dewey --dest "<other folder>"
```

Add `--execute` to change files. Add `-v` to list every file in the plan. Without `--dest`, the files move inside the scanned folder. With `--dest`, the files are copied and the originals stay.

To give call numbers for books with no record, use `--guesses guesses.json`. The file maps a path from the manifest to a call number:

```
{"old/scan_0042.djvu": "TX"}
```

To undo a move in place:

```
python3 scripts/apply.py --undo "<folder>"
```

The undo works until you change the sorted files by hand.

## Configuration

The skill has no settings file. These options exist:

| Option | Script | Default | Effect |
| --- | --- | --- | --- |
| `--offline` | `scan.py` | off | Skip the Open Library lookup. |
| `--system loc` or `--system dewey` | `apply.py` | none, required | Choose the classification system. |
| `--dest DIR` | `apply.py` | the scanned folder | Copy the files into `DIR`. |
| `--guesses FILE` | `apply.py` | none | Add call numbers for books with no record. |
| `--execute` | `apply.py` | off | Change files. Without it, the script only shows the plan. |
| `-v` | `apply.py` | off | List every file in the plan. |

## How it works

`scan.py` walks the folder and skips hidden files, hidden folders, and symbolic links. For each file it reads the metadata with a reader for the file type:

* EPUB: the OPF file in the archive.
* DOCX: `docProps/core.xml`.
* MOBI, AZW, AZW3: the MOBI header and the EXTH block.
* PDF: `pdfinfo` for the title and the author. `pdftotext` for an ISBN in the first 10 pages.
* TXT: an ISBN in the first 20000 bytes.
* Other files: the file name is the title.

The lookup uses the Open Library search API. It searches by ISBN first. If that gives no call number, it searches by title and author. A result is valid only if its title is at least 80% similar to the title of the book. If the author is known, an author name of the result must also be at least 60% similar. The script waits 0.3 seconds between files.

Open Library returns a list of call numbers from all editions of a work. The script takes the first value of the most common class in that list. It converts the Open Library sort form of a LoC number, such as `QA-0076.73000000.C15`, back to the normal form `QA76.73.C15`.

`apply.py` reads the manifest and builds the plan. A path has this form:

* LoC: `<first letter>/<class letters>/<call number> - <original name>`, for example `Q/QA/QA76.73.C15 - book.epub`.
* Dewey: `<hundreds>/<tens>/<call number> - <original name>`, for example `800/810/813.54 - book.mobi`.
* No call number: `_Unsorted/<original name>`.

If two files get the same path, the second file gets `(2)` before the extension, then `(3)`, and so on. A file that already sits in the right shelf folder with the right prefix stays where it is, so a second run on a sorted folder moves nothing.

In place, the script moves the files and appends each move to `.library-sorter-undo.json` in the folder. The script writes the log even if a move fails half way. It then removes the empty folders. With `--dest`, the script copies the files and writes no log.

## License

Copyright (C) 2026 Orpheus-21. This program is free software. You can redistribute it and change it under the terms of the GNU General Public License, version 3 or (at your option) any later version. See the `LICENSE` file.
