# Miami T7 Access and Canonical Tile Discovery

Date: 2026-06-29

Branch: `audit/miami-t7-access-and-tile-discovery`

Baseline: `076864b416fbe60192c33cdd8876602375cc5f45`

Scope: read-only storage and evidence collection for canonical Miami tiles `318155` and `318455`. No mount, repository configuration, city configuration, production output, or source data was modified. The Miami smoke harness was not run.

## Repository State

Initial verification:

| Check | Result |
|---|---|
| `pwd` | `/mnt/c/Users/Glytc/glytchdraft-miami-t7-discovery` |
| Branch | `audit/miami-t7-access-and-tile-discovery` |
| `HEAD` | `076864b416fbe60192c33cdd8876602375cc5f45` |
| `origin/master` | `076864b416fbe60192c33cdd8876602375cc5f45` |
| Initial status | clean |

## Commands Run

Repository and mount verification:

```bash
pwd
git branch --show-current
git rev-parse HEAD
git rev-parse origin/master
git status --short --untracked-files=all
findmnt -no TARGET,SOURCE,FSTYPE,OPTIONS /mnt/t7
df -h /mnt/t7
stat /mnt/t7
```

Bounded T7 discovery:

```bash
find /mnt/t7/miami -maxdepth 4 -type d -print
find /mnt/t7/miami -maxdepth 6 -type f \( -iname '*318455*' -o -iname '*318155*' \) -print
```

Repository/config evidence:

```bash
git worktree list --porcelain
git config --list --show-origin
rg -n "T7|Samsung|Miami LAZ|318455|318155|data_raw|laz|miami" configs scripts docs regions . --glob '!archive/**' --glob '!data/**'
sed -n '1,260p' configs/cities/miami.json
sed -n '1,260p' scripts/miami/metric_normalization_v1.py
sed -n '1,260p' scripts/diagnostics/check_miami_vertical_units.py
find . -maxdepth 4 -iname '*MIAMI*CRS*' -o -iname '*miami*catalog*' -o -iname '*provenance*manifest*' -o -iname 'paths.local*' -o -iname '*source*catalog*'
sed -n '1,260p' docs/diagnostics/MIAMI_AUTHORITATIVE_LAZ_CRS_AUDIT.md
sed -n '1,320p' docs/diagnostics/MIAMI_CRS_CONTRACT_RECONCILIATION.md
```

Manifest/catalog evidence:

```bash
find /mnt/t7/miami/data_processed/miami_city -maxdepth 3 -type f \( -iname '*manifest*.json' -o -iname '*catalog*.json' -o -iname '*inventory*.json' -o -iname '*audit*.json' \) -print
find /mnt/t7/miami/data_raw -maxdepth 3 -type f \( -iname '*catalog*.json' -o -iname '*inventory*.json' -o -iname '*manifest*.json' -o -iname '*audit*.json' \) -print
python -m json.tool /mnt/t7/miami/data_raw/miami_d23_catalog.json
python -m json.tool /mnt/t7/miami/data_processed/miami_city/metadata/laz_inventory.json
python -m json.tool /mnt/t7/miami/data_processed/miami_city/tile_manifest.json
python -m json.tool /mnt/t7/miami/data_processed/miami_city/tiles/USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901/manifest/USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901_manifest.json
python -m json.tool /mnt/t7/miami/data_processed/miami_city/tiles/USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901/manifest/USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901_manifest.json
rg -n -C 12 "318155|318455" /mnt/t7/miami/data_processed/miami_city/tile_manifest.json
rg -n -C 12 "318155|318455" /mnt/t7/miami/data_processed/miami_city/metadata/laz_inventory.json
rg -n -C 12 "318155|318455" /mnt/t7/miami/data_raw/miami_d23_catalog.json
```

Canonical file evidence:

```bash
stat -c '%n|%s|%y|%F' /mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz /mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz
sha256sum /mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz /mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz
conda run -n pdal_env pdal --version
conda run -n pdal_env pdal info --metadata /mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz
conda run -n pdal_env pdal info --metadata /mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz
```

## Storage Observations

`/mnt/t7` was visible and read-only:

```text
/mnt/t7 E: 9p ro,nosuid,nodev,relatime,aname=drvfs;path=E:;symlinkroot=/mnt/,cache=5,access=client,msize=65536,trans=fd,rfd=3,wfd=3
```

Capacity:

```text
Filesystem Size Used Avail Use% Mounted on
E:         1.9T 404G 1.5T  22% /mnt/t7
```

`stat /mnt/t7` showed a directory with mode `0777/drwxrwxrwx`, owner `nobody:nogroup`, and WSL/9p placeholder timestamps. The critical mount option `ro` was present, so discovery proceeded.

## Bounded Miami Tree Discovery

The bounded directory search found `/mnt/t7/miami`, raw data under `/mnt/t7/miami/data_raw`, processed city output under `/mnt/t7/miami/data_processed/miami_city`, and exports under `/mnt/t7/miami/exports`.

The bounded file search for `318155` and `318455` found:

- raw LAZ sources in `/mnt/t7/miami/data_raw/laz`
- derived point clouds, footprints, masses, GLBs, offsets, and manifests under `/mnt/t7/miami/data_processed/miami_city/tiles`

Only the raw LAZ files were treated as source candidates. Derived artifacts were not hashed for source identity and were not passed to PDAL as canonical source metadata.

## Canonical Identity

The exact source identity was not based on filename alone.

Evidence used:

- `configs/cities/miami.json` declares source ID `miami_lidar`, but its `source_crs` is stale/contradictory at `EPSG:3857`.
- `scripts/miami/metric_normalization_v1.py` expects source horizontal CRS `EPSG:6438`, source vertical CRS `EPSG:6360`, and source vertical unit `US survey foot`.
- `docs/diagnostics/MIAMI_CRS_CONTRACT_RECONCILIATION.md` requires reinspection of these exact T7 files before real-data smoke.
- `/mnt/t7/miami/data_processed/miami_city/metadata/laz_inventory.json` lists both raw files with `raw_laz_retained: true`, under `laz_dir: /mnt/t7/miami/data_raw/laz`.
- `/mnt/t7/miami/data_processed/miami_city/tile_manifest.json` was generated from `laz_inventory`, lists both exact `local_path` values, marks both `on_disk: true`, and records `bbox_source: pdal_laz_header_epsg_6438_to_4326`.
- `/mnt/t7/miami/data_raw/miami_d23_catalog.json` identifies both as `FL_MiamiDade_D23_LID2024` / `MiamiDade_D23` with USGS rockyweb download URLs. That catalog still records historical `/mnt/e/...` local paths, which is a storage-path contradiction, not a source-identity contradiction.

## Canonical Tile Files

### 318155

| Field | Value |
|---|---|
| Path | `/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz` |
| Filename | `USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz` |
| Size | `136923600` bytes |
| Modified | `2026-05-24 17:23:22.000000000 -0400` |
| SHA-256 | `0b770a89deb58b1ab0ed2c75848e401d6bd8b1aea72dfe63b272747bf1f40095` |
| PDAL reader | `readers.las` |
| Point count | `26792505` |
| Data format | `6` |
| Compressed / COPC | `compressed: true`, `copc: false` |
| Scale | `scale_x: 0.01`, `scale_y: 0.01`, `scale_z: 0.01` |
| Offset | `offset_x: 0`, `offset_y: 0`, `offset_z: 0` |
| Bounds | `minx: 940000`, `miny: 530000`, `minz: -4.45`, `maxx: 944622.01`, `maxy: 534999.99`, `maxz: 400.91` |
| Horizontal CRS | `NAD83(2011) / Florida East (ftUS)`, EPSG `6438` |
| Vertical CRS | `NAVD88 height - Geoid18 (ftUS)` / `NAVD88 height (ftUS)`, EPSG `6360` |
| Horizontal units | `US survey foot` |
| Vertical units | `US survey foot` |
| WKT/VLR evidence | `vlr_0.user_id: LASF_Projection`, `record_id: 2112`, `description: OGC WKT Coordinate System` |
| GeoTIFF keys | No GeoTIFF key directory was reported by PDAL metadata; CRS evidence is carried by the OGC WKT VLR. |

### 318455

| Field | Value |
|---|---|
| Path | `/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz` |
| Filename | `USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz` |
| Size | `114641426` bytes |
| Modified | `2026-05-24 17:24:16.000000000 -0400` |
| SHA-256 | `dfa514ff43232c5a9914a08e30cec111c3e7cadab1216576107d30fb5ace8816` |
| PDAL reader | `readers.las` |
| Point count | `22434580` |
| Data format | `6` |
| Compressed / COPC | `compressed: true`, `copc: false` |
| Scale | `scale_x: 0.01`, `scale_y: 0.01`, `scale_z: 0.01` |
| Offset | `offset_x: 0`, `offset_y: 0`, `offset_z: 0` |
| Bounds | `minx: 940000`, `miny: 525000`, `minz: -6.3`, `maxx: 943264.42`, `maxy: 529999.99`, `maxz: 198.79` |
| Horizontal CRS | `NAD83(2011) / Florida East (ftUS)`, EPSG `6438` |
| Vertical CRS | `NAVD88 height - Geoid18 (ftUS)` / `NAVD88 height (ftUS)`, EPSG `6360` |
| Horizontal units | `US survey foot` |
| Vertical units | `US survey foot` |
| WKT/VLR evidence | `vlr_0.user_id: LASF_Projection`, `record_id: 2112`, `description: OGC WKT Coordinate System` |
| GeoTIFF keys | No GeoTIFF key directory was reported by PDAL metadata; CRS evidence is carried by the OGC WKT VLR. |

## Metadata Conclusions

Both exact canonical D23 LAZ files were located on read-only T7 storage and inspected with PDAL `2.10.1`.

Both files embed the same compound CRS:

```text
NAD83(2011) / Florida East (ftUS) + NAVD88 height - Geoid18 (ftUS)
```

Both files verify:

- horizontal CRS: `EPSG:6438`
- vertical CRS: `EPSG:6360`
- horizontal units: `US survey foot`
- vertical units: `US survey foot`
- LAS 1.4 point format 6
- scales `0.01 / 0.01 / 0.01`
- zero offsets
- CRS evidence in OGC WKT VLR `LASF_Projection` record `2112`

There is no contradiction between the two canonical tiles. Their bounds differ as expected for adjacent/distinct tiles, but their CRS, units, scale, offset, reader type, compression state, and source collection identity are consistent.

## Contradictions and Risks

| Item | Observation | Impact |
|---|---|---|
| `configs/cities/miami.json` | Declares Miami `source_crs: EPSG:3857`. | Contradicts live LAZ metadata. Treat as stale/wrong for raw 2024 D23 LAZ. |
| `configs/cities/miami.json` provenance | Says `EPSG:3857 per hero-tile manifest; verify against full collection metadata`. | Full collection canonical tiles now verify `EPSG:6438 + EPSG:6360`, not Web Mercator. |
| Address CRS | Miami-Dade GeoAddress still appears as `EPSG:3857`. | Address CRS must remain separate from LAZ source CRS. |
| `miami_d23_catalog.json` | Canonical catalog rows record `local_path: /mnt/e/...` while the safe mounted path is `/mnt/t7/...`. | Storage path contradiction only; source identity still matches filename, USGS URL, project, dataset, bbox, and size. |
| Historical outputs | Existing processed GLBs/manifests predate controlled V1 metric smoke. | Do not certify historical outputs as corrected metric results from this discovery. |

## Decision

**GO** for preparing the controlled canonical two-tile smoke using:

- `/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz`
- `/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz`

The expected source contract `EPSG:6438 + EPSG:6360` with US survey-foot XY and Z units is verified for both exact canonical tiles.

Execution of the real smoke should still re-check immediately before running that `/mnt/t7` remains mounted read-only or otherwise intentionally mounted under the operator-approved policy, and should record these same paths, hashes, CRS fields, units, conversion factor, and stage order in smoke provenance.

## Blockers

No storage blocker remains for metadata verification of the two canonical source tiles.

Remaining blockers before production certification:

- Correct or supersede Miami config/provenance that claims LAZ `EPSG:3857`.
- Keep address `EPSG:3857` separate from LAZ source CRS.
- Do not certify historical Miami outputs as metric-correct until regenerated or proven with V1 normalization provenance.
- The real smoke was intentionally not executed in this read-only discovery lane.
