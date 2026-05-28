# Miami Processed Output QA Report

Scope: read-only inspection of `E:\miami\data_processed\miami_city`; ingestion was not rerun.

## Executive Summary

- Package status: `complete`; `all_tiles_passed`: `True`.
- Tree inventory: 1974 files, 93.86 GB, 0 zero-byte files.
- Tiles: 108 tile directories; 0 tiles with missing expected per-tile outputs.
- Corrupt/unparseable outputs: 0.
- Building records from per-tile mass CSVs: 74,372.
- Point counts from PLY headers: building 0.25 m 1,034,713,853; building 1 m 210,648,393; ground 1 m 84,955,868; vegetation 1 m 0.
- Address coverage: 65,433/74,372 matched (87.98%), 8,939 unmatched.
- Zero-building tiles from supporting outputs: 0 true zero. Stale zero manifests: 12 tiles have manifest `n_clusters=0`/`n_footprints=0` but contain buildings/footprints/GLB.

## Root File Sizes

- `tile_manifest.json`: 64,804 bytes
- `tile_manifest.json.bak_before_bbox`: 45,496 bytes
- `audit/`: 2 files, 0.00 GB
- `blender_ready/`: 6 files, 4.78 GB
- `boundaries/`: 0 files, 0.00 GB
- `logs/`: 8 files, 0.00 GB
- `metadata/`: 4 files, 0.46 GB
- `status/`: 8 files, 0.00 GB
- `tiles/`: 1944 files, 88.62 GB

## Missing Outputs

- None for expected per-tile pointcloud, cluster, footprint, mass, manifest, and per-tile GLB outputs.
- Audit warning: `boundaries/miami_city_boundary_4326.geojson` is missing; `audit/city_audit.md` reports this as the only package warning.

## Corrupt Files

- None found in JSON/GeoJSON/CSV/NPZ/GLB/PLY/OBJ header and parse checks.

## Zero-Building / Stale Manifest Tiles

- True zero-building tiles: 0.
- Stale zero-manifest tiles: 12. These are not empty; outputs contain buildings and footprints.
  - `USGS_LPC_FL_MiamiDade_D23_LID2024_316646_0901`: manifest says zero, but mass rows=1028, footprint features=1028, per-tile GLB exists.
  - `USGS_LPC_FL_MiamiDade_D23_LID2024_316647_0901`: manifest says zero, but mass rows=749, footprint features=749, per-tile GLB exists.
  - `USGS_LPC_FL_MiamiDade_D23_LID2024_316648_0901`: manifest says zero, but mass rows=1208, footprint features=1208, per-tile GLB exists.
  - `USGS_LPC_FL_MiamiDade_D23_LID2024_316649_0901`: manifest says zero, but mass rows=1144, footprint features=1144, per-tile GLB exists.
  - `USGS_LPC_FL_MiamiDade_D23_LID2024_316650_0901`: manifest says zero, but mass rows=1043, footprint features=1043, per-tile GLB exists.
  - `USGS_LPC_FL_MiamiDade_D23_LID2024_316651_0901`: manifest says zero, but mass rows=586, footprint features=586, per-tile GLB exists.
  - `USGS_LPC_FL_MiamiDade_D23_LID2024_316652_0901`: manifest says zero, but mass rows=485, footprint features=485, per-tile GLB exists.
  - `USGS_LPC_FL_MiamiDade_D23_LID2024_316654_0901`: manifest says zero, but mass rows=162, footprint features=162, per-tile GLB exists.
  - `USGS_LPC_FL_MiamiDade_D23_LID2024_316655_0901`: manifest says zero, but mass rows=565, footprint features=565, per-tile GLB exists.
  - `USGS_LPC_FL_MiamiDade_D23_LID2024_316946_0901`: manifest says zero, but mass rows=1065, footprint features=1065, per-tile GLB exists.
  - `USGS_LPC_FL_MiamiDade_D23_LID2024_316947_0901`: manifest says zero, but mass rows=1202, footprint features=1202, per-tile GLB exists.
  - `USGS_LPC_FL_MiamiDade_D23_LID2024_316948_0901`: manifest says zero, but mass rows=1432, footprint features=1432, per-tile GLB exists.

## Blender-Ready Outputs

- `miami.glb`: 2,636,300,584 bytes
- `miami_city.glb`: 101,503,748 bytes
- `miami_city_glb_offset.json`: 707 bytes
- `miami_glb_offset.json`: 109 bytes
- `miami_terrain_1m.ply`: 2,038,940,957 bytes
- `miami_vegetation_1m.ply`: 142 bytes

## Per-Tile Inventory

| Tile | Size | Buildings | Footprints | Bldg 0.25m pts | Bldg 1m pts | Ground 1m pts | Veg pts | Address matched | Missing |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `USGS_LPC_FL_MiamiDade_D23_LID2024_316646_0901` | 787.28 MB | 1028 | 1028 | 9,303,998 | 1,608,352 | 1,137,897 | 0 | 910/1028 (88.5%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_316647_0901` | 951.82 MB | 749 | 749 | 11,219,603 | 2,078,190 | 1,180,897 | 0 | 710/749 (94.8%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_316648_0901` | 889.84 MB | 1208 | 1208 | 10,134,352 | 2,141,588 | 1,261,547 | 0 | 1182/1208 (97.8%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_316649_0901` | 852.51 MB | 1144 | 1144 | 9,820,201 | 2,007,770 | 1,063,864 | 0 | 1035/1144 (90.5%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_316650_0901` | 1283.87 MB | 1043 | 1043 | 15,007,042 | 3,042,079 | 1,212,970 | 0 | 1041/1043 (99.8%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_316651_0901` | 1505.07 MB | 586 | 586 | 17,570,235 | 3,718,559 | 1,152,274 | 0 | 559/586 (95.4%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_316652_0901` | 1142.16 MB | 485 | 485 | 13,399,390 | 2,745,027 | 923,051 | 0 | 376/485 (77.5%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_316654_0901` | 182.82 MB | 162 | 162 | 2,153,759 | 409,237 | 181,797 | 0 | 133/162 (82.1%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_316655_0901` | 809.72 MB | 565 | 565 | 9,567,980 | 1,870,185 | 709,793 | 0 | 549/565 (97.2%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_316946_0901` | 846.62 MB | 1065 | 1065 | 10,047,971 | 1,743,555 | 1,115,757 | 0 | 995/1065 (93.4%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_316947_0901` | 809.69 MB | 1202 | 1202 | 9,436,405 | 1,726,360 | 1,252,810 | 0 | 1126/1202 (93.7%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_316948_0901` | 846.69 MB | 1432 | 1432 | 9,605,413 | 2,015,210 | 1,296,380 | 0 | 1430/1432 (99.9%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_316949_0901` | 923.36 MB | 1362 | 1362 | 10,645,106 | 2,130,463 | 1,223,064 | 0 | 1362/1362 (100.0%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_316950_0901` | 1042.12 MB | 1431 | 1431 | 12,109,717 | 2,399,878 | 1,206,067 | 0 | 1431/1431 (100.0%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_316951_0901` | 1319.38 MB | 825 | 825 | 15,379,621 | 3,229,335 | 1,111,958 | 0 | 824/825 (99.9%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_316952_0901` | 990.00 MB | 399 | 399 | 11,643,908 | 2,406,371 | 679,142 | 0 | 382/399 (95.7%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_316953_0901` | 317.25 MB | 354 | 354 | 3,690,679 | 761,553 | 286,344 | 0 | 306/354 (86.4%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_316954_0901` | 494.85 MB | 541 | 541 | 5,790,039 | 1,125,687 | 559,256 | 0 | 483/541 (89.3%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_316955_0901` | 785.24 MB | 448 | 448 | 9,197,194 | 1,909,770 | 611,857 | 0 | 440/448 (98.2%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_317246_0901` | 876.62 MB | 944 | 944 | 10,423,046 | 1,816,926 | 1,120,131 | 0 | 936/944 (99.2%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_317247_0901` | 800.67 MB | 979 | 979 | 9,581,482 | 1,593,988 | 1,036,087 | 0 | 933/979 (95.3%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_317248_0901` | 725.61 MB | 1529 | 1529 | 8,155,490 | 1,681,196 | 1,323,619 | 0 | 1454/1529 (95.1%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_317249_0901` | 806.19 MB | 1524 | 1524 | 9,277,962 | 1,788,014 | 1,258,345 | 0 | 1474/1524 (96.7%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_317250_0901` | 1012.50 MB | 1487 | 1487 | 11,818,395 | 2,273,009 | 1,207,348 | 0 | 1484/1487 (99.8%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_317251_0901` | 1145.38 MB | 752 | 752 | 13,375,268 | 2,730,017 | 1,118,647 | 0 | 752/752 (100.0%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_317252_0901` | 538.76 MB | 136 | 136 | 6,375,633 | 1,313,965 | 278,873 | 0 | 132/136 (97.1%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_317253_0901` | 12.51 MB | 17 | 17 | 145,617 | 30,470 | 8,698 | 0 | 17/17 (100.0%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_317254_0901` | 2.56 MB | 19 | 19 | 27,514 | 6,168 | 3,200 | 0 | 19/19 (100.0%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_317255_0901` | 605.49 MB | 428 | 428 | 6,961,356 | 1,500,092 | 651,507 | 0 | 284/428 (66.4%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_317546_0901` | 847.23 MB | 1140 | 1140 | 10,041,876 | 1,741,838 | 1,137,039 | 0 | 1129/1140 (99.0%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_317547_0901` | 866.52 MB | 984 | 984 | 10,276,851 | 1,818,110 | 1,091,879 | 0 | 983/984 (99.9%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_317548_0901` | 856.51 MB | 1353 | 1353 | 9,757,754 | 2,021,514 | 1,281,648 | 0 | 1353/1353 (100.0%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_317549_0901` | 1063.36 MB | 1037 | 1037 | 12,418,902 | 2,444,088 | 1,203,373 | 0 | 1008/1037 (97.2%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_317550_0901` | 1275.70 MB | 954 | 954 | 15,009,930 | 2,962,236 | 1,177,827 | 0 | 954/954 (100.0%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_317551_0901` | 1388.29 MB | 627 | 627 | 16,254,596 | 3,388,276 | 1,085,471 | 0 | 620/627 (98.9%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_317552_0901` | 366.77 MB | 205 | 205 | 4,321,153 | 871,798 | 255,344 | 0 | 143/205 (69.8%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_317554_0901` | 40.57 MB | 23 | 23 | 489,585 | 89,749 | 20,597 | 0 | 23/23 (100.0%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_317555_0901` | 1079.60 MB | 456 | 456 | 12,569,124 | 2,717,139 | 785,616 | 0 | 376/456 (82.5%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_317846_0901` | 719.37 MB | 1344 | 1344 | 8,300,196 | 1,521,247 | 1,242,313 | 0 | 1185/1344 (88.2%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_317847_0901` | 808.37 MB | 1206 | 1206 | 9,434,317 | 1,735,905 | 1,188,287 | 0 | 1179/1206 (97.8%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_317848_0901` | 873.70 MB | 1189 | 1189 | 10,082,873 | 2,009,446 | 1,219,525 | 0 | 1184/1189 (99.6%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_317849_0901` | 1120.68 MB | 1096 | 1096 | 13,137,088 | 2,579,465 | 1,154,366 | 0 | 1090/1096 (99.5%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_317850_0901` | 1101.84 MB | 1104 | 1104 | 12,878,053 | 2,541,238 | 1,204,924 | 0 | 999/1104 (90.5%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_317851_0901` | 1048.06 MB | 878 | 878 | 12,159,683 | 2,617,180 | 883,199 | 0 | 839/878 (95.6%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_317852_0901` | 6.66 MB | 45 | 45 | 68,870 | 15,128 | 18,232 | 0 | 3/45 (6.7%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_317854_0901` | 387.43 MB | 409 | 409 | 4,526,198 | 904,873 | 374,636 | 0 | 134/409 (32.8%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_317855_0901` | 1158.14 MB | 607 | 607 | 13,424,965 | 2,909,842 | 1,002,433 | 0 | 476/607 (78.4%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_318146_0901` | 463.58 MB | 1289 | 1289 | 5,124,015 | 930,488 | 1,363,359 | 0 | 629/1289 (48.8%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_318147_0901` | 789.78 MB | 1045 | 1045 | 9,238,869 | 1,710,770 | 1,104,749 | 0 | 990/1045 (94.7%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_318148_0901` | 866.51 MB | 1197 | 1197 | 10,066,127 | 1,972,089 | 1,118,755 | 0 | 1174/1197 (98.1%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_318149_0901` | 996.72 MB | 1232 | 1232 | 11,697,277 | 2,252,756 | 1,097,126 | 0 | 1192/1232 (96.8%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_318150_0901` | 976.17 MB | 1334 | 1334 | 11,434,264 | 2,192,480 | 1,149,294 | 0 | 1306/1334 (97.9%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_318151_0901` | 849.11 MB | 1096 | 1096 | 9,784,614 | 2,100,461 | 874,106 | 0 | 1066/1096 (97.3%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_318152_0901` | 117.05 MB | 86 | 86 | 1,366,464 | 284,822 | 93,620 | 0 | 84/86 (97.7%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_318153_0901` | 278.89 MB | 117 | 117 | 3,286,503 | 679,182 | 170,136 | 0 | 109/117 (93.2%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_318154_0901` | 817.60 MB | 376 | 376 | 9,653,061 | 1,967,947 | 544,215 | 0 | 340/376 (90.4%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901` | 874.70 MB | 550 | 550 | 10,202,141 | 2,140,690 | 756,597 | 0 | 388/550 (70.5%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_318446_0901` | 624.31 MB | 1506 | 1506 | 7,076,554 | 1,347,461 | 1,259,796 | 0 | 818/1506 (54.3%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_318447_0901` | 957.36 MB | 984 | 984 | 11,305,079 | 2,061,277 | 1,179,875 | 0 | 908/984 (92.3%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_318448_0901` | 904.53 MB | 1295 | 1295 | 10,479,208 | 2,078,959 | 1,161,700 | 0 | 1245/1295 (96.1%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_318449_0901` | 1064.73 MB | 1278 | 1278 | 12,433,291 | 2,506,064 | 1,040,197 | 0 | 1249/1278 (97.7%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_318450_0901` | 1053.44 MB | 1633 | 1633 | 12,214,785 | 2,487,530 | 1,128,200 | 0 | 1507/1633 (92.3%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_318451_0901` | 836.55 MB | 1361 | 1361 | 9,530,894 | 2,121,215 | 900,118 | 0 | 1207/1361 (88.7%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_318452_0901` | 333.86 MB | 615 | 615 | 3,856,996 | 740,463 | 453,439 | 0 | 393/615 (63.9%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_318453_0901` | 463.88 MB | 193 | 193 | 5,452,960 | 1,134,949 | 295,462 | 0 | 130/193 (67.4%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_318454_0901` | 676.11 MB | 397 | 397 | 7,897,370 | 1,673,052 | 497,186 | 0 | 375/397 (94.5%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901` | 719.77 MB | 544 | 544 | 8,372,525 | 1,785,846 | 599,143 | 0 | 384/544 (70.6%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_318746_0901` | 1138.60 MB | 799 | 799 | 13,516,629 | 2,524,141 | 1,137,172 | 0 | 795/799 (99.5%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_318747_0901` | 1094.85 MB | 879 | 879 | 12,940,430 | 2,454,192 | 1,119,332 | 0 | 843/879 (95.9%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_318748_0901` | 974.43 MB | 1015 | 1015 | 11,336,943 | 2,275,284 | 1,146,555 | 0 | 1013/1015 (99.8%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_318749_0901` | 1141.79 MB | 972 | 972 | 13,492,735 | 2,619,095 | 1,057,943 | 0 | 972/972 (100.0%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_318750_0901` | 1100.52 MB | 1104 | 1104 | 12,915,683 | 2,570,925 | 1,057,549 | 0 | 1099/1104 (99.5%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_318751_0901` | 1034.08 MB | 697 | 697 | 11,907,884 | 2,757,278 | 634,358 | 0 | 629/697 (90.2%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_318752_0901` | 94.14 MB | 265 | 265 | 1,038,247 | 208,260 | 240,399 | 0 | 150/265 (56.6%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_318753_0901` | 221.28 MB | 620 | 620 | 2,476,675 | 461,120 | 585,922 | 0 | 242/620 (39.0%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_318754_0901` | 426.81 MB | 570 | 570 | 4,939,226 | 1,008,451 | 469,045 | 0 | 364/570 (63.9%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_318755_0901` | 448.48 MB | 372 | 372 | 5,132,585 | 1,157,318 | 419,937 | 0 | 259/372 (69.6%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_319046_0901` | 1668.33 MB | 290 | 290 | 19,824,322 | 3,975,534 | 1,031,675 | 0 | 281/290 (96.9%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_319047_0901` | 1248.32 MB | 741 | 741 | 14,737,447 | 2,911,419 | 1,080,318 | 0 | 676/741 (91.2%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_319048_0901` | 1147.33 MB | 541 | 541 | 13,469,853 | 2,719,641 | 1,068,102 | 0 | 541/541 (100.0%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_319049_0901` | 1383.85 MB | 444 | 444 | 16,434,683 | 3,230,019 | 1,038,268 | 0 | 444/444 (100.0%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_319050_0901` | 1439.89 MB | 687 | 687 | 16,886,961 | 3,514,266 | 1,082,731 | 0 | 678/687 (98.7%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_319051_0901` | 471.77 MB | 321 | 321 | 5,436,420 | 1,250,334 | 297,527 | 0 | 305/321 (95.0%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_319052_0901` | 31.91 MB | 3 | 3 | 356,508 | 95,550 | 14,335 | 0 | 0/3 (0.0%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_319053_0901` | 283.87 MB | 58 | 58 | 3,305,972 | 739,406 | 120,749 | 0 | 1/58 (1.7%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_319054_0901` | 681.93 MB | 474 | 474 | 7,709,000 | 1,860,260 | 565,791 | 0 | 204/474 (43.0%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_319055_0901` | 39.86 MB | 55 | 55 | 468,892 | 89,776 | 36,686 | 0 | 55/55 (100.0%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_319346_0901` | 1797.43 MB | 303 | 303 | 21,326,309 | 4,338,511 | 1,007,834 | 0 | 303/303 (100.0%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_319347_0901` | 1214.30 MB | 625 | 625 | 14,409,226 | 2,774,277 | 1,038,617 | 0 | 625/625 (100.0%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_319348_0901` | 1443.17 MB | 505 | 505 | 16,813,817 | 3,663,216 | 1,009,877 | 0 | 505/505 (100.0%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_319349_0901` | 1605.32 MB | 392 | 392 | 18,957,008 | 3,966,071 | 827,012 | 0 | 293/392 (74.7%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_319350_0901` | 416.31 MB | 196 | 196 | 4,847,038 | 1,076,995 | 213,683 | 0 | 111/196 (56.6%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_319351_0901` | 16.05 MB | 209 | 209 | 156,145 | 31,092 | 66,508 | 0 | 0/209 (0.0%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_319352_0901` | 104.69 MB | 272 | 272 | 1,160,758 | 239,982 | 206,832 | 0 | 64/272 (23.5%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_319353_0901` | 2032.78 MB | 471 | 471 | 23,443,643 | 5,529,077 | 764,813 | 0 | 100/471 (21.2%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_319354_0901` | 656.88 MB | 366 | 366 | 7,366,630 | 1,870,216 | 478,069 | 0 | 6/366 (1.6%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_319646_0901` | 1568.01 MB | 534 | 534 | 18,500,981 | 3,777,429 | 1,033,301 | 0 | 526/534 (98.5%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_319647_0901` | 1762.75 MB | 492 | 492 | 20,771,204 | 4,345,515 | 1,038,200 | 0 | 492/492 (100.0%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_319648_0901` | 912.16 MB | 573 | 573 | 10,574,418 | 2,370,918 | 519,138 | 0 | 379/573 (66.1%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_319649_0901` | 36.57 MB | 26 | 26 | 433,122 | 83,916 | 23,477 | 0 | 15/26 (57.7%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_319653_0901` | 324.16 MB | 400 | 400 | 3,755,227 | 785,928 | 262,213 | 0 | 94/400 (23.5%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_319654_0901` | 382.63 MB | 24 | 24 | 4,354,654 | 1,081,442 | 194,464 | 0 | 0/24 (0.0%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_319946_0901` | 1821.85 MB | 265 | 265 | 21,567,204 | 4,436,375 | 983,950 | 0 | 238/265 (89.8%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_319947_0901` | 1843.81 MB | 89 | 89 | 21,648,091 | 4,768,068 | 714,984 | 0 | 88/89 (98.9%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_319948_0901` | 8.04 MB | 10 | 10 | 90,600 | 22,049 | 4,872 | 0 | 9/10 (90.0%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_319952_0901` | 360.68 MB | 1 | 1 | 4,217,487 | 957,111 | 78,687 | 0 | 0/1 (0.0%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_319953_0901` | 1030.00 MB | 846 | 846 | 11,900,134 | 2,587,268 | 751,218 | 0 | 81/846 (9.6%) | 0 |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_319954_0901` | 235.13 MB | 237 | 237 | 2,603,675 | 660,081 | 246,763 | 0 | 22/237 (9.3%) | 0 |

## Recommended Fixes

1. Regenerate or patch the 12 stale per-tile manifests and `metadata/miami_city_manifest.json` from existing outputs only. Do not rerun ingestion; derive `n_clusters`, `n_footprints`, `lod0_count`, and `lod1_count` from existing cluster summaries, footprint GeoJSON, and mass metadata.
2. Restore or generate `boundaries/miami_city_boundary_4326.geojson`, or remove it from required package outputs if boundary export is intentionally optional.
3. Investigate vegetation extraction: every per-tile vegetation PLY has 0 vertices and `blender_ready/miami_vegetation_1m.ply` is only 142 bytes, despite `vegetation_enabled: true`. Either disable vegetation in manifests or rerun only the vegetation stage after verifying source classifications.
4. Review low address-coverage tiles before publication, especially `319351`, `319354`, `319954`, `319953`, `319353`, and `319653`; global coverage is acceptable at 88.0%, but several edge/water/park tiles are weak.
5. Resolve the building total discrepancy: per-tile mass CSVs contain 74,372 buildings, while city manifest totals report 63,675 LOD0 / 63,703 LOD1. Update city totals from existing artifacts before treating the package as final.
