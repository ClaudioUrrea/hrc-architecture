"""Download the large data files from the Figshare deposit."""
import argparse, json, os, urllib.request

API = "https://api.figshare.com/v2/articles/33194013/files"
LARGE = ["cycles_36M.parquet", "protocol_samples.parquet", "ablation_cycles.parquet",
         "segments_30.parquet", "cbf_dataset_66d.npz"]


def main(dest):
    os.makedirs(dest, exist_ok=True)
    with urllib.request.urlopen(API) as fh:
        files = json.load(fh)
    for f in files:
        if f["name"] in LARGE:
            out = os.path.join(dest, f["name"])
            print(f"fetching {f['name']} ({f['size'] / 1e6:.1f} MB)")
            urllib.request.urlretrieve(f["download_url"], out)
            print(f"  md5 expected {f['supplied_md5']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--doi", default="10.6084/m9.figshare.33194013")
    ap.add_argument("--dest", default="data/")
    main(ap.parse_args().dest)
