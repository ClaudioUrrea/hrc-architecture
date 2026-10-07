PY := python3
OUT := out

.PHONY: all check figures conformance tuning clean fetch-data data

all: $(OUT)/results.json figures

$(OUT)/results.json:
	mkdir -p $(OUT)
	$(PY) analysis/run_all.py --out $(OUT)/results.json

check: $(OUT)/results.json
	$(PY) analysis/check_against_paper.py --results $(OUT)/results.json

figures:
	mkdir -p $(OUT)/figures
	cd figures && $(PY) p2_figures.py   # regenerates all 13 figures; Figures 6, 7 and 10 are drawn from data/
	cp -r figures/figures_p2_electronics/. $(OUT)/figures/

data:
	$(PY) tools/reconstruct_data.py all --out data/
	$(PY) tools/reconstruct_faults.py data/faults_450.csv

fetch-data:
	$(PY) analysis/fetch_figshare.py --doi 10.6084/m9.figshare.33194013 --dest data/

conformance:
	$(PY) analysis/conformance.py

tuning:
	$(PY) analysis/tune_baselines.py

clean:
	rm -rf $(OUT)
