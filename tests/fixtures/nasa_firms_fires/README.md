# NASA FIRMS FIRES fixtures

Real payloads captured during the P4b spike on 2026-11-08, trimmed to the smallest
samples that preserve the observed response shape. Nothing here is synthetic and
nothing here was edited by hand except the trimming described below.

Source: NASA FIRMS area CSV API,
`https://firms.modaps.eosdis.nasa.gov/api/area/csv/<MAP_KEY>/<DATA_ID>/world/<DAY_RANGE>[/<DATE>]`

The `MAP_KEY` path segment is replaced by `<MAP_KEY>` everywhere; no key is stored
in this repository.

## Observed response format

- CSV, 14 columns, one header line repeated for every satellite:
  `latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight`
  (header line without the trailing newline: 122 bytes, md5
  `57591d193a8127bb19b9491dc0d69b91`; with it: 123 bytes, md5
  `4c08ee93f0ea02b0a4c397547046d0a2`)
- No trailing newline at end of body.
- `day_range` above 5 is rejected before any data is returned.

## Files

| File | Bytes | What it is |
|---|---|---|
| `availability_snpp.csv` | 62 | `data_availability` response, `VIIRS_SNPP_NRT`, byte-exact |
| `availability_noaa20.csv` | 64 | `data_availability` response, `VIIRS_NOAA20_NRT`, byte-exact |
| `availability_noaa21.csv` | 64 | `data_availability` response, `VIIRS_NOAA21_NRT`, byte-exact |
| `world_1_snpp.csv` | 122 | `world/1` for VIIRS_SNPP_NRT, byte-exact: header only, zero rows |
| `world_1_noaa20.csv` | 122 | `world/1` for VIIRS_NOAA20_NRT, byte-exact: header only, zero rows |
| `world_1_noaa21.csv` | 122 | `world/1` for VIIRS_NOAA21_NRT, byte-exact: header only, zero rows |
| `world_5_noaa20_head.csv` | 202 | `world/5` for VIIRS_NOAA20_NRT: header + first data row only (trimmed from 243 788 rows / 20 410 586 bytes) |
| `world_5_noaa21_head.csv` | 207 | `world/5` for VIIRS_NOAA21_NRT: header + first data row only (trimmed from 235 219 rows / 19 704 715 bytes) |
| `day_2026-11-02_snpp_head.csv` | 201 | `world/1/2026-11-02` for VIIRS_SNPP_NRT: header + first data row only (trimmed from 35 261 rows / 2 867 736 bytes) |
| `error_invalid_day_range.txt` | 34 | HTTP 400 body for `world/7` and `world/10`, byte-exact |

The three `world_1_*.csv` files are byte-identical (md5
`57591d193a8127bb19b9491dc0d69b91`). An empty day is a valid, well-formed CSV
whose body is the header alone, not an error.

## Measured volumes (2026-11-08 spike)

Spike start 2026-11-08T00:38Z, end 2026-11-08T00:49Z (UTC). Measured from the
same machine at that time:

- `VIIRS_NOAA20_NRT` `world/5`: 243 788 rows, `acq_date` 2026-11-04..2026-11-07
- `VIIRS_NOAA21_NRT` `world/5`: 235 219 rows, `acq_date` 2026-11-04..2026-11-07
- `VIIRS_SNPP_NRT` `world/1/2026-11-02`: 35 261 rows, all dated 2026-11-02
- `data_availability` on 2026-11-08: SNPP `max_date` 2026-11-02,
  NOAA-20 and NOAA-21 `max_date` 2026-11-07

Suomi NPP stopped delivering new observations on 2026-11-02 (NASA Earthdata
data-alert), so its `max_date` is an end of data rather than a delay.

## Reuse

These files exist to test shape handling only: header detection, empty-response
handling, the 14-column schema, `satellite` codes (`N`, `N20`, `N21`) and the
5-day limit error. They are not a sample of a full day and must not be used to
estimate volume.
