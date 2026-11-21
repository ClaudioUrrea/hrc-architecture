#!/bin/bash
# Marked copy of manuscript R4 against the round-3 manuscript (Reviewer 2, Point 15).
#   - both versions are flattened first: every result macro is replaced by its printed value and every
#     generated table body is inlined, so that changed numbers appear as changed text;
#   - latexdiff 1.3.1: added text in blue, deleted text in red and struck through (so that adjacent deleted and
#     added words stay apart), NO underlining;
#     changed equations are marked as a whole (--math-markup=whole); tables, tabulars and TikZ pictures
#     are treated as blocks (PICTUREENV), so a changed table appears once deleted and once added, whole;
#     figures are not marked (--graphics-markup=none);
#   - the result is self-contained (macros, tables and references inlined) and compiles alone.
# Run in WSL after scripts/build_r4.ps1; compile the output on Windows (MiKTeX):
#   bash scripts/make_marked_r4.sh  &&  pdflatex P2_Electronics_R4_marked.tex (x3)
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p diff_base
python3 - <<'PYEOF'
import re, pathlib
P = pathlib.Path
def macros(path):
    m = {}
    for line in P(path).read_text(encoding="utf-8").splitlines():
        g = re.match(r"\\newcommand\{\\(\w+)\}\{(.*)\}\s*$", line)
        if g:
            m[g.group(1)] = g.group(2)
    return m
def flatten(tex, numdir, numfile, bib, extra_num_files=()):
    s = P(tex).read_text(encoding="utf-8")
    M = macros(P(numdir) / numfile)
    for f in extra_num_files:
        if P(f).exists():
            M.update(macros(f))
    s = re.sub(r"\\gtab\{([^}]*)\}", lambda g: "\n".join(l for l in (P(numdir) / f"{g.group(1)}.tex").read_text(encoding="utf-8").splitlines() if not l.startswith("%")), s)
    s = re.sub(r"\\(R[A-Za-z]+|Chr[A-Za-z]+)\{\}", lambda g: M.get(g.group(1), g.group(0)), s)
    s = re.sub(r"\\InputIfFileExists\{numbers/[^}]*\}\{\}\{[^}]*\}\n", "", s)
    s = s.replace("\\makeatletter\n\\newcommand{\\gtab}[1]{\\@@input numbers/#1.tex }\n\\makeatother\n", "")
    s = s.replace("\\input{" + bib + "}", P(bib + ".tex").read_text(encoding="utf-8").strip())
    return s
old = flatten("_R3_base/P2_Electronics_R3.tex", "numbers_r30_old", "r3_numbers.tex", "_R3_base/bibliography_r3")
# the name of the department was updated without being a change of content: not marked
old = old.replace("Electrical Engineering Department, Faculty", "Department of Electrical Engineering, Faculty")
new = flatten("P2_Electronics_R4.tex", "numbers", "r4_numbers.tex", "bibliography_r4", ["numbers/r4_chronology.tex"])
left = sorted(set(re.findall(r"\\(R[A-Z][A-Za-z]+)\{\}", new)) - {"RepoURL"})
assert not left, left
P("diff_base/old_R3_flat.tex").write_text(old, encoding="utf-8")
P("diff_base/new_R4_flat.tex").write_text(new, encoding="utf-8")
P("diff_base/marked_preamble.tex").write_text(
    "\\RequirePackage{color}\n"
    "\\RequirePackage[normalem]{ulem}\n"
    "\\providecommand{\\DIFadd}[1]{{\\color{blue}#1}}\n"
    "\\providecommand{\\DIFdel}[1]{{\\color{red}\\sout{#1}}}\n"
    "\\providecommand{\\DIFaddbegin}{}\\providecommand{\\DIFaddend}{}\n"
    "\\providecommand{\\DIFdelbegin}{}\\providecommand{\\DIFdelend}{}\n"
    "\\providecommand{\\DIFmodbegin}{}\\providecommand{\\DIFmodend}{}\n"
    "\\providecommand{\\DIFaddFL}[1]{\\DIFadd{#1}}\\providecommand{\\DIFdelFL}[1]{\\DIFdel{#1}}\n"
    "\\providecommand{\\DIFaddbeginFL}{\\begingroup\\color{blue}}\\providecommand{\\DIFaddendFL}{\\endgroup}\n"
    "\\providecommand{\\DIFdelbeginFL}{}\\providecommand{\\DIFdelendFL}{}\n"
    "\\newenvironment{DIFnomarkup}{}{}\n", encoding="utf-8")
PYEOF
latexdiff --preamble=diff_base/marked_preamble.tex --graphics-markup=none --math-markup=whole \
  --config="PICTUREENV=(?:picture|tikzpicture|DIFnomarkup|tabular|verbatim)[\w\d*@]*" \
  --exclude-textcmd="section,subsection,subsubsection" \
  diff_base/old_R3_flat.tex diff_base/new_R4_flat.tex > diff_base/marked_raw.tex 2> diff_base/latexdiff_r4.log
python3 - <<'PYEOF'
import pathlib
s = pathlib.Path("diff_base/marked_raw.tex").read_text(encoding="utf-8")
note = (r"\noindent\fbox{\parbox{\linewidth}{\small\textbf{Marked copy (round 4).} Changes with respect to the "
        r"round-3 manuscript: added text in \textcolor{blue}{blue}, deleted text in \textcolor{red}{red} and struck through, "
        r"without underlining. Changed equations are shown whole, the old version in red followed by the new one in blue; changed tables are shown whole "
        r"in blue; the old version of a changed table is not reproduced here (it is in the round-3 manuscript). Numbers are shown as printed in each version. Figures are not marked; all figures were regenerated "
        r"from the release-3.1 records. Generated with latexdiff 1.3.1 (script \texttt{make\_marked\_r4.sh}).}}\par\medskip" + "\n")
s = s.replace("\\begin{document}", "\\begin{document}\n" + note, 1)
import re
# a label must stay inside the group that \\DIFaddbeginFL opens around a new caption
s = re.sub(r"\\DIFaddendFL\s*(\\label\{[^}]*\})", r"\1\\DIFaddendFL ", s)
pathlib.Path("P2_Electronics_R4_marked.tex").write_text(s, encoding="utf-8")
print("written P2_Electronics_R4_marked.tex", len(s))
PYEOF
