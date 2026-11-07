# Where provincial wealth comes from: coal reliance and other extractives

Plan for upgrading the wealth-vs-momentum chart (`analysis/20261102_province-quadrants/`) so that it shows, for each province, how much of its wealth comes from coal, how much from other extractives such as nickel, copper and oil, and how much from the rest of the economy.

## Question

Which provinces owe their wealth to coal, which owe it to other extractives, and which are wealthy (or not) for other reasons?

The current chart plots GRDP per capita against GRDP growth. It ranks provinces by wealth but cannot say where that wealth comes from. Total mining (sector B), the only extractive measure in the current dataset, mixes coal with oil and gas, nickel and copper, so it cannot separate a coal province from a nickel province.

## Separating coal from other extractives

BPS provincial GRDP tables split mining into four subsectors and manufacturing into sixteen. The extractive economy of a province sits in five of those rows.

| Group | BPS rows | Example provinces (to be confirmed by the data) |
|---|---|---|
| **Coal** | B.2 Pertambangan Batubara dan Lignit | Kalimantan Timur, Kalimantan Selatan, Sumatera Selatan |
| **Oil and gas** | B.1 Pertambangan Minyak, Gas dan Panas Bumi | Riau, Kepulauan Riau, Papua Barat |
| **Metal ores** (nickel, copper, gold, tin, bauxite) | B.3 Pertambangan Bijih Logam | Maluku Utara, Sulawesi Tengah, Sulawesi Tenggara, Papua Tengah, Nusa Tenggara Barat |
| **Metal processing** (nickel smelting sits here) | C.11 Industri Logam Dasar | Maluku Utara, Sulawesi Tengah, Sulawesi Tenggara |
| **Coal and oil refining** | C.1 Industri Batubara dan Pengilangan Migas | Riau, Kalimantan Timur |

Nickel needs both the metal-ore row and the basic-metals row. Most of the value added in Maluku Utara and Sulawesi Tengah now comes from smelters (Weda Bay, Morowali), which BPS counts under manufacturing, not mining. Counting B.3 alone would understate nickel provinces.

C.1 mixes coal processing with oil refining. It is reported but kept out of the coal share, because in most provinces it is refining.

### Measures

All shares use GRDP at current prices for the same year.

- **Coal share** = B.2 / total GRDP
- **Other extractive share** = (B.1 + B.3 + C.11) / total GRDP
- **Non-extractive share** = 1 − coal share − other extractive share − C.1 share
- **GRDP per capita without coal** = (total GRDP − B.2) / population

## Charts

### 1. Wealth vs momentum, coloured by coal share (upgrade of the existing chart)

Keep GRDP per capita (log) on X and growth on Y. Colour each point with a single-hue scale in four coal-share bands: none (0%), under 5%, 5–20%, over 20%. Points of provinces whose main extractive is not coal get a hollow ring, so a nickel province does not read as coal-free and therefore diversified.

Use real growth (GRDP at constant prices) on Y once that data is in. Nominal growth moves with coal and nickel prices, which is likely why Kalimantan Timur shows only 3.6% and Maluku Utara 37.8%.

### 2. Coal reliance vs other extractive reliance (the classification chart)

- X: other extractive share (nickel, copper, oil and gas)
- Y: coal share
- Point size: GRDP per capita
- Cut lines: 10% on each axis

| | Low other extractives | High other extractives |
|---|---|---|
| **High coal** | Coal economy | Mixed extractive economy |
| **Low coal** | Non-extractive economy | Nickel, copper or oil economy |

This is the chart that separates Kalimantan Timur from Maluku Utara.

### 3. Where each province's GRDP per capita comes from (stacked bars)

One horizontal bar per province, sorted by GRDP per capita, split into coal, oil and gas, metal ores and processing, refining, and everything else. A dashed line marks Indonesia's GRDP per capita. This shows the size of each source in rupiah per person, not just its share.

### 4. Wealth with and without coal (dumbbell)

For each coal-producing province, a line from GRDP per capita with coal to GRDP per capita without it, sorted by the length of the line. Provinces whose line crosses the Indonesia average owe their above-average wealth to coal. A second version can remove all extractives.

### 5. Does extractive wealth reach households?

- X: GRDP per capita
- Y: adjusted per capita household expenditure (pengeluaran per kapita disesuaikan)
- Colour: main extractive group from chart 2

Provinces far below the trend line produce wealth that households do not spend locally: profits leave the province or go to the central government. This is common in mining provinces. The poverty rate can replace household spending on Y.

## Data

| Priority | Data | Status (2026-11-07) |
|---|---|---|
| Essential | GRDP by subsector, current prices, all provinces (rows B.1–B.4, C.1, C.11, total) | **Fetched** through the BPS WebAPI for 27 of 38 provinces (`raw/grdp/20261107_bps-webapi-grdp-by-subsector.jsonl`). Latest year: 2025 for 17, 2024 for 5, 2023 for 3, 2022 for 2 |
| Strongly recommended | The same table for 2020–2024 | **Fetched** for the same 27 provinces, 2020 onward |
| Recommended | GRDP at constant prices by subsector | **Fetched** for the same provinces, except Sumatera Selatan, whose subsector table is current prices only |
| Recommended | Adjusted per capita expenditure by province | **Fetched** 2020–2026 (`raw/welfare/20261107_bps-webapi-welfare-by-province.jsonl`) |
| Recommended | Poverty rate (P0) by province | **Fetched** 2020–2026, same file |
| Already in the repository | GRDP total, population, total mining (B) | `data/20261102_bps-province-grdp-population/` |

### Provinces without a subsector table

Eleven BPS provincial offices publish GRDP only by the 17 main sectors, so coal cannot be separated from other mining there: Aceh, DKI Jakarta, Bengkulu, Nusa Tenggara Timur, Kalimantan Barat, Sulawesi Tengah, Maluku, Papua, Papua Selatan, Papua Tengah and Papua Pegunungan (the last three have no BPS office of their own yet).

For these, total mining (B) is an upper bound on coal. Where mining is under 2% of GRDP (Jakarta, for example), the province is classed as low-coal with confidence. Three matter for this analysis and need another source, such as the PDF "PDRB menurut lapangan usaha" publication of each provincial office:

- **Bengkulu**: a coal producer
- **Sulawesi Tengah**: nickel (Morowali)
- **Papua Tengah**: copper and gold (Grasberg)

### First look at the 2025 data

| Province | Coal (B.2) | Oil and gas (B.1) | Metal ores (B.3) | Basic metals (C.11) |
|---|---|---|---|---|
| Kalimantan Selatan | 26.3% | 0.3% | 0.3% | 0.0% |
| Kalimantan Timur | 25.1% | 4.9% | 0.0% | 0.1% |
| Sumatera Selatan | 13.9% | 5.4% | 0.0% | 0.0% |
| Kalimantan Tengah | 7.2% | 0.4% | 1.7% | 0.0% |
| Maluku Utara | 0.0% | 0.0% | 20.8% | 38.5% |
| Papua Barat | 0.0% | 25.0% | 0.0% | 0.0% |
| Kepulauan Bangka Belitung | 0.0% | 0.4% | 4.9% | 9.0% |

Shares of GRDP at current prices. Some provincial totals differ slightly from the national BPS table already in the repository (Bangka Belitung 116,387 against 116,812; Kalimantan Tengah 240,127 against 241,056), likely because the two tables were revised on different dates. The build step must report these gaps rather than force a match.

### Why the BPS WebAPI key is needed

The Kalimantan Selatan table checked on 2026-11-07 ([page](https://kalsel.bps.go.id/id/statistics-table/2/MzIyIzI=/-seri-2010-pdrb-menurut-lapangan-usaha.html)) has every row listed above, at both current and constant prices, but only for 2025. The page lists 2010–2025 as available yet ignores any year in the address. Other provinces publish the table under different names and splits (quarterly only, constant prices only, percentage distribution only), so finding it by web search is slow and error-prone across 38 sites.

The BPS WebAPI (`https://webapi.bps.go.id`) is BPS's official machine access. With a free key it can list each province's tables by keyword, return any year, and return JSON. One script can then fetch 2020–2025 for all 38 provinces, both price bases, and the 2025 welfare tables.

### How to get the key

1. Register at `https://webapi.bps.go.id/developer/register` with your own email address.
2. Log in, create an application, and copy its key.
3. Give the key to Claude. It is saved in a git-ignored `.env` file at the repository root and never committed.

## Caveats

- 2025 GRDP is very preliminary (`**`) and 2024 preliminary (`*`); BPS will revise both.
- GRDP measures production located in a province, not income of its residents. Mining profits often leave the province, so GRDP per capita overstates local living standards in mining provinces; chart 5 tests this.
- Nominal shares move with commodity prices. A province's coal share can rise in a price boom without any change in output. Using 2020–2025 shows this directly, since coal prices peaked in 2022.
- The six Papua provinces have separate values only from 2024; trends from 2020 need the pre-split areas.
- A 10% cut-off for "reliant" is a convention, not a BPS definition. The charts should show the shares so readers can apply their own threshold.

## Next steps

1. ~~Get the BPS WebAPI key.~~ Done; stored in the git-ignored `.env`.
2. ~~Download subsector GRDP and welfare tables.~~ Done for 27 provinces and all welfare tables.
3. Decide how to fill Bengkulu, Sulawesi Tengah and Papua Tengah (provincial PDF publications, or show them as total mining only).
4. Build `data/YYYYMMDD_bps-province-grdp-subsector/` through `tools/cleaning.py`, mapping each province's row labels to the shared codes, with identity checks that subsectors sum to sectors and sectors to total.
5. Build charts 1–5 in a new `analysis/` folder.
