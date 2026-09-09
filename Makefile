PY := python3
OUT := out

.PHONY: all check figures clean fetch-data

all: $(OUT)/results.json figures

$(OUT)/results.json:
	mkdir -p $(OUT)
	$(PY) analysis/run_all.py --out $(OUT)/results.json

check: $(OUT)/results.json
	$(PY) analysis/check_against_paper.py --results $(OUT)/results.json

figures:
	mkdir -p $(OUT)/figures
	cd figures && $(PY) p2_figures.py
	cp -r figures/figures_p2_electronics/. $(OUT)/figures/

fetch-data:
	$(PY) analysis/fetch_figshare.py --doi 10.6084/m9.figshare.33194013 --dest data/

clean:
	rm -rf $(OUT)
