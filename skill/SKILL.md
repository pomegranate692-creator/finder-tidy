---
name: finder-tidy
description: Smartly organize a Mac folder (Downloads by default) into colorful category folders with custom icons and Finder color tags. Reads file contents to sort by meaning, cleans up junk names, catches duplicates, always previews first and never deletes. Use when the user asks to organize, clean up, or sort their Downloads, Desktop, or any folder.
---

# Finder Tidy

You are organizing a folder on the user's Mac with the Finder Tidy toolkit
(https://github.com/pomegranate692-creator/finder-tidy). The script `tidy.py` does the safe
mechanics (moving, logging, undo, icons, color tags). You add the judgment: reading
files to sort them by what they are, and giving junk names clear ones.

Golden rules: preview before anything moves, never delete, keep every move in the log.

## 1. Get the toolkit

If `tidy.py` is not already on the machine, clone it:

```
git clone https://github.com/pomegranate692-creator/finder-tidy ~/.finder-tidy
```

Use `python3 ~/.finder-tidy/tidy.py` below (or the user's own clone path).

## 2. Draft a plan with the script

```
python3 ~/.finder-tidy/tidy.py ~/Downloads --plan-out /tmp/tidy-plan.json
```

The plan is a JSON list of `{src, dst, category, reason}`. The script already:

- sorts by extension and filename keywords across 34 categories (see `categories.json`)
- only creates folders the user actually needs (small groups fold into a parent)
- sends exact duplicates, lock files, empty files, broken downloads, and installers for apps
  already installed to `Review to Delete`
- archives files untouched for 180 days into `Archive/<year>/<category>`
- skips anything modified in the last 10 minutes and leaves the user's own folders alone

## 3. Make it smart

Read the plan and improve it. Focus on items the script could not judge well:

- **Read contents** of PDFs, Word files, and images whose names say nothing
  (`Document3.docx`, `IMG_4821.png`, `2023092621240244837.pdf`). Use `pdftotext`,
  `textutil -convert txt`, or open the image. Move each to the category that matches
  what it is (a scanned receipt goes to Receipts, a syllabus to School).
- **Rename junk names** to `YYYY-MM-DD Short Description.ext` using a date from the content
  when there is one. Leave clear names, class submission names, and installers alone.
  Fix double extensions like `.pdf.pdf`.
- **Group school work by course** when course codes show up (`School/BIO 101/`).
- Keep `src` paths unchanged; only edit `dst`, `category`, and `reason`. Every `dst` must
  stay inside the target folder. Use folder names exactly as `<emoji> <Category>` from
  `categories.json`, or reuse a folder that already exists.
- Never touch things that look private (IDs, medical, tax) beyond what sorting needs.

Save the edited plan back to the same file.

## 4. Preview and ask

Show the user a short preview: how many items go to each folder, notable renames, and
everything headed to `Review to Delete` with sizes. Mention that renaming folders can break
"Recent files" lists in some apps. Ask: run it, tweak it, or cancel. Apply tweaks and show
only what changed.

## 5. Run it

```
python3 ~/.finder-tidy/tidy.py ~/Downloads --plan-in /tmp/tidy-plan.json --apply
```

This moves everything, writes a log to `.tidy/logs/`, then gives every category folder its
icon and color tag. If icons look stale in Finder, run with `--style-only` once more.

## 6. Report

Say how many items moved, what is waiting in `Review to Delete` (and its total size), and
how to undo:

```
python3 ~/.finder-tidy/tidy.py ~/Downloads --undo
```

Suggest one next step, usually looking over `Review to Delete` and emptying it in Finder.
