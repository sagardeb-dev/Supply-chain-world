# arXiv upload reference (saved 2026-07-10, from author-provided guidance)

Three sources pasted by the author: the arXiv preflight checklist, a
step-by-step author guide, and arXiv's "common mistakes" FAQ. Saved here so
the prep plan (ARXIV-PREP.md) can cite exact steps. Repo-specific decisions
live in ARXIV-PREP.md, not here.

## A. arXiv preflight checklist (arxiv.org)

- TeX submissions MUST upload source; PDFs produced from TeX may be declined.
- Put all upload files into one folder before starting.
- Common errors that slow announcement: missing files or references — double
  check before uploading.
- All announced content is archival and cannot be removed. Ensure nothing you
  don't want archived is in the upload — **including TeX comments in source**.

## B. Author step-by-step upload guide

1. Deep-copy the paper directory (`cp -r paper_dir tmp`); do everything in
   the copy — the clean repo layout doesn't survive arXiv prep.
2. Merge any split supplement back in: `\appendix` after main content,
   appendix content after the references, one PDF with everything.
3. Unpublished paper: remove journal-specific text ("submitted to …",
   "under peer review") from the style file copy. Published: match the
   published style/volume info.
4. Flatten subdirectories (e.g. move `figures/*` to root, fix paths,
   delete empty dirs). [arXiv does support subdirs for `\input` and
   `\includegraphics`; only `\include{subdir/…}` breaks — see FAQ C.]
5. Delete everything not needed to compile. Everything uploaded becomes
   public: hidden files (`.git/`), unused `.tex`/`.sty`/`.cls`, old notes.
   Delete the rendered PDF and LaTeX-generated files (.aux .log .out .blg).
6. Remove ALL comments (`% …`) from all `.tex` files — they become public.
7. After `\end{document}` add:
   `\typeout{get arXiv to do 4 passes: Label(s) may have changed. Rerun}`
   (forces up to 4 compile passes so cleveref/autonum refs resolve).
8. Compile in tmp/, confirm the PDF looks right.
9. Keep the generated `.bbl`; delete other generated files.
10. Delete the `.bib`; arXiv uses the precompiled `.bbl` you provide.
11. `tar -cvvf ax.tar *` in tmp/; upload the tarball.
12. After upload, inspect the extracted file list; remove anything arXiv
    flags as unnecessary.
13. Check arXiv's compile log AND the PDF arXiv produces, carefully.
14. Abstract metadata: strip LaTeX syntax, newlines, double spaces (they
    show up verbatim on arXiv).
15. Title metadata: strip LaTeX, use Initial Caps style.
16. Author metadata: full names, commas, no "and" —
    e.g. "Bob Authorson, Alice van de Paper, Rebecca Writezki".
17. Consult your advisor on the subject area choice.
18. After posting, send coauthors the paper password so they can claim
    ownership.

## C. arXiv "Common Mistakes" FAQ (info.arxiv.org/help/faq/mistakes.html)

Items relevant to this paper (plain LaTeX, standard packages, PDF figures):

- **Absolute filenames**: all includes must use relative paths
  (`myfigure.png`, never `/users/...`).
- **Filenames**: no spaces, no `/ \ : &` in file names; uploads convert such
  characters to `_` and you must fix inclusion commands yourself.
- **Missing style/macro files**: any non-TeXLive style (e.g. a conference
  .sty) must be inside the tarball.
- **Last-minute untested changes**: always recompile before submitting.
- **`\include{subdir/file}` fails** (can't write `subdir/file.aux` — only the
  top-level dir is writable during processing). `\input{subdir/file}` is OK.
- **Unprotected `\cite` inside `\caption`**: use `\protect\cite{…}`.
- **Mixed figure formats**: PDFLaTeX accepts .pdf/.jpg/.png only; (La)TeX
  accepts .ps/.eps only. No on-the-fly conversion.
- **Engine detection**: arXiv decides pdflatex vs latex itself; use the
  `ifpdf` package if conditional branching is ever needed. XeTeX/LuaTeX/LyX
  are NOT supported.
- **hyperref + complex sections → broken pdfmarks**: if PDF conversion fails,
  `\usepackage[bookmarks=false]{hyperref}`.
- **minted**: `--shell-escape` is disabled on arXiv; frozencache with a
  non-hidden cachedir only.
- **.bbl version mismatch**: the .bbl must come from a TeXLive version arXiv
  supports (TL2023: bbl 3.2/3.3; TL2025: bbl 3.3 only).
- **Ignored files**: use a `00README` file to mark files not to process.
- **User intervention impossible**: fully automated processing; interactive
  prompts need a `filename.inp` answer file.

Items in the FAQ that do NOT apply to this paper (kept as headings only):
old dvips-incompatible styles, AMS-TeX/Plain-TeX formats, unusual fonts,
PostScript `%%BoundingBox` (atend), double sub/superscript errors, feynmf,
`\Bbbk already defined` (newtxmath+amssymb clash), breqn+hyperref label loop.
