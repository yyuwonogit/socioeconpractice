from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared cleaning module from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import cleaning

import pandas as pd

# Parameters

# Raw inputs: the provincial subsector tables saved from the BPS WebAPI, and the BPS province list
RAW_GRDP = ROOT / "raw/grdp/20261107_bps-webapi-grdp-by-subsector.jsonl"
RAW_PROVINCES = ROOT / "raw/province-codes/20261102_bps-province-codes-2025-s1.json"

# National BPS table already cleaned in data/, a different release used only to compare vintages
NATIONAL = ROOT / "data/20261102_bps-province-grdp-population/20261102_bps-province-grdp-population.csv"

# Output; the metadata JSON is written beside it with a -metadata suffix
OUT_CSV = HERE / "20261108_bps-province-grdp-subsector.csv"

KEYS = ["province_code", "indicator", "sector", "period"]

# Price basis of each indicator, and the text that names it in a table title or column
INDICATORS = {
    "grdp_current": "PDRB atas dasar harga berlaku (GRDP at current prices), Seri 2010",
    "grdp_constant": "PDRB atas dasar harga konstan 2010 (GRDP at constant 2010 prices), Seri 2010",
}

# How each saved WebAPI table writes its values, read from opening every response in RAW_GRDP.
# Keyed by (WebAPI domain, var). Fields:
#   province     name in the BPS province list; code_in_domain False when another office publishes it
#   unit         text that must appear in the var unit (or in the title, when unit_in_title)
#   shift        decimal places to move a value so it is in Milyar Rupiah (Juta Rupiah -> -3)
#   decimals     the var's declared decimals; values carry at most this many
#   written_decimals  decimals the values actually carry, when fewer than declared (sets the rounding tolerance)
#   prices       column (turvar) label -> indicator, or None -> indicator for a one-basis table,
#                with the title text that names the basis
#   c1_split     the table splits C.1 into a. coal processing and b. oil and gas refining
#   fixes        raw row label -> sector code, for a label the source gets wrong
#   status       year -> BPS revision marker, as the table note states it; years absent have no marker
#   status_text  phrases the table note (def + note) must still carry for that status to hold
#   exclude      reason a table is read and checked but not written
READ_CONTEXT = {
    ("1200", "778"): {"province": "Sumatera Utara", "unit": "Milyar Rupiah", "shift": 0, "decimals": 2,
                      "prices": {None: ("grdp_current", "Harga Berlaku")},
                      "status": {2023: "*", 2024: "**"}, "status_text": ["2023 Angka Sementara, 2024 Angka Sangat Sementara"]},
    ("1200", "780"): {"province": "Sumatera Utara", "unit": "Milyar Rupiah", "shift": 0, "decimals": 2,
                      "prices": {None: ("grdp_constant", "Harga Konstan 2010")},
                      "status": {2023: "*", 2024: "**"}, "status_text": ["2023 Angka Sementara, 2024 Angka Sangat Sementara"]},
    ("1300", "153"): {"province": "Sumatera Barat", "unit": "Juta Rupiah", "shift": -3, "decimals": 2,
                      "prices": {"Harga Berlaku": "grdp_current", "Harga Konstan 2010": "grdp_constant"},
                      "status": {2024: "**"}, "status_text": ["2024 Angka Sangat Sementara"]},
    ("1400", "419"): {"province": "Riau", "unit": "Milyar Rupiah", "shift": 0, "decimals": 2, "written_decimals": 0,
                      "prices": {None: ("grdp_current", "ADHB")}, "status": {}, "status_text": []},
    ("1400", "418"): {"province": "Riau", "unit": "Milyar Rupiah", "shift": 0, "decimals": 2,
                      "prices": {None: ("grdp_constant", "ADHK")}, "status": {}, "status_text": []},
    ("1500", "1976"): {"province": "Jambi", "unit": "Milyar Rupiah", "shift": 0, "decimals": 1, "c1_split": True,
                       "prices": {None: ("grdp_current", "Harga Berlaku")}, "status": {}, "status_text": []},
    ("1500", "1977"): {"province": "Jambi", "unit": "Milyar Rupiah", "shift": 0, "decimals": 1, "c1_split": True,
                       "prices": {None: ("grdp_constant", "Harga Konstan")}, "status": {}, "status_text": []},
    ("1600", "741"): {"province": "Sumatera Selatan", "unit": "Miliar Rupiah", "shift": 0, "decimals": 2,
                      "prices": {None: ("grdp_current", "Harga Berlaku")},
                      "status": {2024: "*", 2025: "**"}, "status_text": ["2025: Angka sangat sementara", "2024: Angka sementara"]},
    # Lampung labels category D "/Electricity and Gas" and its D.2 row "Pengadaan Listrik dan Gas"; the D.2 row is not read
    ("1800", "893"): {"province": "Lampung", "unit": "milyar rupiah", "shift": 0, "decimals": 2,
                      "prices": {"Harga Berlaku": "grdp_current", "Harga Konstan-2010": "grdp_constant"},
                      "fixes": {"2. Pengadaan Listrik dan Gas": None},
                      "status": {}, "status_text": []},
    ("1900", "8"): {"province": "Kepulauan Bangka Belitung", "unit": "Milyar Rupiah", "shift": 0, "decimals": 2,
                    "prices": {None: ("grdp_current", "Harga Berlaku")}, "status": {}, "status_text": []},
    ("1900", "32"): {"province": "Kepulauan Bangka Belitung", "unit": "Milyar Rupiah", "shift": 0, "decimals": 2,
                     "prices": {None: ("grdp_constant", "Harga Konstan (2010=100)")}, "status": {}, "status_text": []},
    ("2100", "265"): {"province": "Kepulauan Riau", "unit": "Milyar Rupiah", "shift": 0, "decimals": 1,
                      "prices": {None: ("grdp_current", "Harga Berlaku")},
                      "status": {2024: "*", 2025: "**"},
                      "status_text": ["N: Tahun Terakhir Data", "Data Tahun ke N : Angka Sangat Sementara", "Data Tahun ke N-1 : Angka Sementara"]},
    ("2100", "268"): {"province": "Kepulauan Riau", "unit": "Milyar Rupiah", "shift": 0, "decimals": 2,
                      "prices": {None: ("grdp_constant", "Harga Konstan")},
                      "status": {2024: "*", 2025: "**"},
                      "status_text": ["N: Tahun Terakhir Data", "Data Tahun ke N : Angka Sangat Sementara", "Data Tahun ke N-1 : Angka Sementara"]},
    ("3200", "111"): {"province": "Jawa Barat", "unit": "Miliar Rupiah", "shift": 0, "decimals": 2,
                      "prices": {None: ("grdp_current", "Harga Berlaku")}, "status": {}, "status_text": []},
    ("3200", "113"): {"province": "Jawa Barat", "unit": "Miliar Rupiah", "shift": 0, "decimals": 2,
                      "prices": {None: ("grdp_constant", "Harga Konstan")}, "status": {}, "status_text": []},
    ("3300", "2280"): {"province": "Jawa Tengah", "unit": "Juta Rupiah", "shift": -3, "decimals": 2,
                       "prices": {None: ("grdp_current", "Harga Berlaku")},
                       "status": {2022: "*", 2023: "**"}, "status_text": ["2022* Angka sementara, 2023** Angka sangat sementara"]},
    ("3300", "2278"): {"province": "Jawa Tengah", "unit": "Juta Rupiah", "shift": -3, "decimals": 2,
                       "prices": {None: ("grdp_constant", "Harga Konstan 2010")},
                       "status": {2022: "*", 2023: "**"}, "status_text": ["2022* Angka sementara, 2023** Angka sangat sementara"]},
    ("3400", "268"): {"province": "DI Yogyakarta", "unit": "Miliar Rupiah", "shift": 0, "decimals": 2,
                      "prices": {"Harga Berlaku": "grdp_current", "Harga Konstan 2010": "grdp_constant"},
                      "status": {}, "status_text": []},
    # The Jawa Timur note counts from n = the current year (2026), as in every other BPS table of 2026
    ("3500", "483"): {"province": "Jawa Timur", "unit": "Miliar Rupiah", "shift": 0, "decimals": 2,
                      "prices": {None: ("grdp_current", "Harga Berlaku")},
                      "status": {2024: "*", 2025: "**"},
                      "status_text": ["Nilai tahun ke n-1 merupakan angka Sangat Sementara", "Nilai tahun ke n-2 Merupakan Angka Sementara"]},
    ("3500", "473"): {"province": "Jawa Timur", "unit": "Miliar Rupiah", "shift": 0, "decimals": 2,
                      "prices": {None: ("grdp_constant", "Harga Konstan")},
                      "status": {2024: "*", 2025: "**"},
                      "status_text": ["Nilai tahun ke n-1 merupakan angka Sangat Sementara", "Nilai tahun ke n-2 Merupakan Angka Sementara"]},
    ("3600", "342"): {"province": "Banten", "unit": "miliar rupiah", "shift": 0, "decimals": 2,
                      "prices": {None: ("grdp_current", "Harga Berlaku")},
                      "status": {2023: "*", 2024: "**", 2025: "***"},
                      "status_text": ["2023: Angka Sementara", "2024: Angka Sangat Sementara", "2025: Angka Sangat Sangat Sementara"]},
    ("3600", "343"): {"province": "Banten", "unit": "miliar rupiah", "shift": 0, "decimals": 2,
                      "prices": {None: ("grdp_constant", "ADHK 2010")},
                      "status": {2023: "*", 2024: "**", 2025: "***"},
                      "status_text": ["2023: Angka Sementara", "2024: Angka Sangat Sementara", "2025: Angka Sangat Sangat Sementara"]},
    ("5100", "363"): {"province": "Bali", "unit": "Milyar Rupiah", "shift": 0, "decimals": 2,
                      "prices": {None: ("grdp_current", "Harga Berlaku")},
                      "status": {2024: "*", 2025: "**"}, "status_text": ["2025: Angka sangat sementara", "2024: Angka sementara"]},
    ("5100", "365"): {"province": "Bali", "unit": "Milyar Rupiah", "shift": 0, "decimals": 2,
                      "prices": {None: ("grdp_constant", "Harga Konstan 2010")},
                      "status": {2024: "*", 2025: "**"}, "status_text": ["2025: Angka sangat sementara", "2024: Angka sementara"]},
    ("5200", "352"): {"province": "Nusa Tenggara Barat", "unit": "Milyar Rupiah", "shift": 0, "decimals": 2, "c1_split": True,
                      "prices": {None: ("grdp_current", "Harga Berlaku")},
                      "status": {2024: "*", 2025: "**"}, "status_text": ["Tahun 2024 : Angka sementara", "Tahun 2025 : Angka sangat sementara"]},
    ("5200", "353"): {"province": "Nusa Tenggara Barat", "unit": "Milyar Rupiah", "shift": 0, "decimals": 2, "c1_split": True,
                      "prices": {None: ("grdp_constant", "Harga Konstan")},
                      "status": {2024: "*", 2025: "**"}, "status_text": ["Tahun 2024 : Angka sementara", "Tahun 2025 : Angka sangat sementara"]},
    # Kalimantan Tengah gives no unit in the unit field ("Tidak Ada Satuan"); the title names it
    ("6200", "38"): {"province": "Kalimantan Tengah", "unit": "(miliar rupiah)", "unit_in_title": True, "shift": 0, "decimals": 2, "written_decimals": 1,
                     "c1_split": True, "prices": {None: ("grdp_current", "Harga Berlaku")},
                     "status": {2024: "*", 2025: "**"},
                     "status_text": ["Data tahun terakhir (n): Data Sangat Sementara", "Data sebelum tahun terakhir (n-1): Data Sementara"]},
    ("6200", "437"): {"province": "Kalimantan Tengah", "unit": "(miliar rupiah)", "unit_in_title": True, "shift": 0, "decimals": 2, "written_decimals": 1,
                      "c1_split": True, "prices": {None: ("grdp_constant", "Harga Konstan 2010")},
                      "status": {2024: "*", 2025: "**"},
                      "status_text": ["Data tahun terakhir (n): Data Sangat Sementara", "Data sebelum tahun terakhir (n-1): Data Sementara"]},
    ("6300", "322"): {"province": "Kalimantan Selatan", "unit": "Miliar Rupiah", "shift": 0, "decimals": 2,
                      "prices": {"Atas Dasar Harga Berlaku": "grdp_current", "Atas Dasar Harga Konstan 2010": "grdp_constant"},
                      "status": {2024: "*", 2025: "**"}, "status_text": ["Tahun 2024*: Angka Sementara", "Tahun 2025**: Angka Sangat Sementara"]},
    ("6400", "238"): {"province": "Kalimantan Timur", "unit": "Miliar Rupiah", "shift": 0, "decimals": 2,
                      "prices": {None: ("grdp_current", "Harga Berlaku")}, "status": {}, "status_text": []},
    ("6400", "239"): {"province": "Kalimantan Timur", "unit": "Miliar Rupiah", "shift": 0, "decimals": 2,
                      "prices": {None: ("grdp_constant", "Harga Konstan 2010")}, "status": {}, "status_text": []},
    ("6500", "119"): {"province": "Kalimantan Utara", "unit": "Juta Rupiah", "shift": -3, "decimals": 1, "c1_split": True,
                      "prices": {None: ("grdp_current", "Harga Berlaku")}, "status": {}, "status_text": []},
    ("6500", "120"): {"province": "Kalimantan Utara", "unit": "Juta Rupiah", "shift": -3, "decimals": 1, "c1_split": True,
                      "prices": {None: ("grdp_constant", "Harga Konstan 2010")}, "status": {}, "status_text": []},
    # The Sulawesi Utara note counts from t = the current year (2026), as in every other BPS table of 2026
    ("7100", "206"): {"province": "Sulawesi Utara", "unit": "Miliar Rupiah", "shift": 0, "decimals": 2,
                      "prices": {None: ("grdp_current", "Harga Berlaku")},
                      "status": {2024: "*", 2025: "**"},
                      "status_text": ["Data tahun t-1: sangat sementara", "Data tahun t-2; Data sementara"]},
    ("7100", "1877"): {"province": "Sulawesi Utara", "unit": "Miliar Rupiah", "shift": 0, "decimals": 2,
                       "prices": {None: ("grdp_constant", "Harga Konstan")},
                       "status": {2024: "*", 2025: "**"},
                       "status_text": ["Data tahun t-1: sangat sementara", "Data tahun t-2; Data sementara"]},
    ("7300", "1744"): {"province": "Sulawesi Selatan", "unit": "Miliar Rupiah", "shift": 0, "decimals": 2,
                       "prices": {"Atas Dasar Harga Berlaku": "grdp_current", "Atas Dasar Harga Konstan": "grdp_constant"},
                       "status": {2024: "*", 2025: "**"}, "status_text": ["2025: Angka Sangat Sementara", "2024: Angka Sementara"]},
    # Sulawesi Tenggara mixes units inside one table, so it is checked but not written (see 'exclude')
    ("7400", "422"): {"province": "Sulawesi Tenggara", "unit": "Juta Rupiah", "shift": -3, "decimals": 2,
                      "prices": {"Harga Berlaku": "grdp_current", "Harga Konstan 2010": "grdp_constant"},
                      "status": {}, "status_text": [],
                      "exclude": "The table states Juta Rupiah, but its current-price values (2020-2022) and its 2022 constant-price "
                                 "values are 1,000 times larger than its 2020-2021 constant-price values (A 2020: 31,395,380,000 "
                                 "current against 21,728,370 constant), and its 2022 TOTAL is about one tenth of the sum of its "
                                 "categories. The units cannot be read from the table, so no value is written."},
    ("7500", "240"): {"province": "Gorontalo", "unit": "Juta Rupiah", "shift": -3, "decimals": 2, "c1_split": True,
                      "prices": {None: ("grdp_current", "ADHB")}, "status": {}, "status_text": []},
    ("7500", "241"): {"province": "Gorontalo", "unit": "Juta Rupiah", "shift": -3, "decimals": 2, "c1_split": True,
                      "prices": {None: ("grdp_constant", "ADHK")}, "status": {}, "status_text": []},
    ("7600", "459"): {"province": "Sulawesi Barat", "unit": "Juta Rupiah", "shift": -3, "decimals": 2,
                      "prices": {None: ("grdp_current", "Harga Berlaku")},
                      "status": {2022: "*", 2023: "**"}, "status_text": ["2022 Angka Sementara", "2023 Angka Sangat Sementara"]},
    ("7600", "456"): {"province": "Sulawesi Barat", "unit": "Juta Rupiah", "shift": -3, "decimals": 2,
                      "prices": {None: ("grdp_constant", "Harga Konstan 2010")},
                      "status": {2022: "*", 2023: "**"}, "status_text": ["2022 Angka Sementara", "2023 Angka Sangat Sementara"]},
    # Maluku Utara labels its B.4 row "Perikanan"; it sits under mining and the B identity confirms it is B.4
    ("8200", "294"): {"province": "Maluku Utara", "unit": "Milyar Rupiah", "shift": 0, "decimals": 1,
                      "prices": {"Atas Dasar Harga Berlaku": "grdp_current", "Atas Dasar Harga Konstan 2010": "grdp_constant"},
                      "fixes": {"B.4.    Perikanan": "B4"},
                      "status": {2024: "*", 2025: "**"}, "status_text": ["2024: Angka Sementara", "2025: Angka Sangat Sementara"]},
    # The Papua Barat note predates its 2025 values, so 2025 carries no marker
    ("9100", "177"): {"province": "Papua Barat", "unit": "Milyar Rupiah", "shift": 0, "decimals": 2,
                      "prices": {"Atas Dasar Harga Berlaku": "grdp_current", "Atas Dasar Harga Konstan 2010": "grdp_constant"},
                      "status": {2023: "*", 2024: "**"},
                      "status_text": ["2024 : Angka Sangat Sementara", "2023 : Angka Sementara", "Sejak 2023, data tidak termasuk Provinsi Papua Barat Daya"]},
    # BPS Papua Barat publishes Papua Barat Daya, which has no BPS office of its own
    ("9100", "310"): {"province": "Papua Barat Daya", "code_in_domain": False, "unit": "Milyar Rupiah", "shift": 0, "decimals": 2,
                      "prices": {"Atas Dasar Harga Berlaku": "grdp_current", "Atas Dasar Harga Konstan 2010": "grdp_constant"},
                      "status": {2023: "*", 2024: "**"}, "status_text": ["2023: Angka Sementara", "2024: Angka Sangat Sementara"]},
}

# Sector codes and the row name each must match, in table order. Categories use the codes of
# data/20261102_bps-province-grdp-population; subsectors add the BPS row number (B2 = B.2).
SECTORS = {
    "A":     (r"^Pertanian, Kehutanan,? (dan|&) Perikanan$", "Pertanian, Kehutanan dan Perikanan"),
    "B":     (r"^Pertambangan (dan|&) Penggalian$", "Pertambangan dan Penggalian"),
    "B1":    (r"^Pertambangan Minyak", "Pertambangan Minyak, Gas dan Panas Bumi (oil, gas and geothermal)"),
    "B2":    (r"^Pertambangan Batu ?bara", "Pertambangan Batubara dan Lignit (coal and lignite)"),
    "B3":    (r"^Pertambangan Bijih Logam", "Pertambangan Bijih Logam (metal ores: nickel, copper, gold, tin, bauxite)"),
    "B4":    (r"^Pertambangan (dan|&) Penggalian Lainnya", "Pertambangan dan Penggalian Lainnya (other mining and quarrying)"),
    "C":     (r"^Industri Pengolahan$", "Industri Pengolahan"),
    "C1":    (r"^Industri Batu ?bara dan Pengilangan Migas$", "Industri Batubara dan Pengilangan Migas (coal products and oil refining)"),
    "C1A":   (r"^Industri Batu ?bara$", "Industri Batubara (coal products), published by some provinces only"),
    "C1B":   (r"^(Industri )?(Pengilangan|Penggilingan) Migas$", "Pengilangan Migas (oil and gas refining), published by some provinces only"),
    "C2":    (r"^Industri Makanan", "Industri Makanan dan Minuman"),
    "C3":    (r"^(Industri )?Pengolahan Tembakau", "Industri Pengolahan Tembakau"),
    "C4":    (r"^Industri Tekstil", "Industri Tekstil dan Pakaian Jadi"),
    "C5":    (r"^Industri Kulit", "Industri Kulit, Barang dari Kulit dan Alas Kaki"),
    "C6":    (r"^Industri Kayu", "Industri Kayu, Barang dari Kayu dan Gabus dan Barang Anyaman"),
    "C7":    (r"^Industri Kertas", "Industri Kertas dan Barang dari Kertas; Percetakan"),
    "C8":    (r"^Industri Kimia", "Industri Kimia, Farmasi dan Obat Tradisional"),
    "C9":    (r"^Industri Karet", "Industri Karet, Barang dari Karet dan Plastik"),
    "C10":   (r"^Industri Barang Galian", "Industri Barang Galian bukan Logam"),
    "C11":   (r"^Industri Logam Dasar", "Industri Logam Dasar (basic metals, including nickel smelting)"),
    "C12":   (r"^Industri Barang (dari )?Logam","Industri Barang Logam; Komputer, Barang Elektronik, Optik; dan Peralatan Listrik"),
    "C13":   (r"^Industri Mesin", "Industri Mesin dan Perlengkapan"),
    "C14":   (r"^Industri Alat Angkutan", "Industri Alat Angkutan"),
    "C15":   (r"^Industri Furni", "Industri Furnitur"),
    "C16":   (r"^Industri Pengolahan Lainnya", "Industri Pengolahan Lainnya; Jasa Reparasi dan Pemasangan Mesin dan Peralatan"),
    "D":     (r"^(Pengadaan Listr?ik|/Electricity and Gas$)","Pengadaan Listrik dan Gas"),
    "E":     (r"^Pengadaan Air", "Pengadaan Air, Pengelolaan Sampah, Limbah dan Daur Ulang"),
    "F":     (r"^Konstruksi$", "Konstruksi"),
    "G":     (r"^Perdagangan Besar dan (Eceran[;,]? (dan )?)?Reparasi","Perdagangan Besar dan Eceran, Reparasi Mobil dan Sepeda Motor"),
    "H":     (r"^Transportasi dan Pergudangan$", "Transportasi dan Pergudangan"),
    "I":     (r"^Penyediaan Akomodasi (dan|&) Makan Minum$", "Penyediaan Akomodasi dan Makan Minum"),
    "J":     (r"^Informasi dan Komunikasi$", "Informasi dan Komunikasi"),
    "K":     (r"^Jasa Keuangan( (dan|&) Asuransi)?$","Jasa Keuangan dan Asuransi"),
    "L":     (r"^Real Estat", "Real Estate"),
    "MN":    (r"^Jasa Perusahaan$", "Jasa Perusahaan"),
    "O":     (r"^Administrasi Pemerintahan", "Administrasi Pemerintahan, Pertahanan dan Jaminan Sosial Wajib"),
    "P":     (r"^Jasa Pendidikan$", "Jasa Pendidikan"),
    "Q":     (r"^Jasa Kesehatan", "Jasa Kesehatan dan Kegiatan Sosial"),
    "RSTU":  (r"^Jasa Lainnya$", "Jasa Lainnya"),
    "TOTAL": (r"^(Produk Domestik Regional Bruto|PDRB)$", "Produk Domestik Regional Bruto"),
}
CATEGORIES = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "MN", "O", "P", "Q", "RSTU"]
SPLIT_ONLY = {"C1A", "C1B"}

# Cells that a table leaves empty, found by opening every response; any other empty cell stops the build.
# (province, indicator, sector) -> years. BPS publishes no value there, usually an activity the province lacks.
SOURCE_GAPS = {
    ('Sumatera Barat', 'grdp_constant', 'B1'): [2020, 2021, 2022, 2023, 2024],
    ('Sumatera Barat', 'grdp_constant', 'C11'): [2020, 2021, 2022, 2023, 2024],
    ('Sumatera Barat', 'grdp_constant', 'C13'): [2020, 2021, 2022, 2023, 2024],
    ('Sumatera Barat', 'grdp_current', 'B1'): [2020, 2021, 2022, 2023, 2024],
    ('Sumatera Barat', 'grdp_current', 'C11'): [2020, 2021, 2022, 2023, 2024],
    ('Sumatera Barat', 'grdp_current', 'C13'): [2020, 2021, 2022, 2023, 2024],
    ('Kepulauan Riau', 'grdp_current', 'C1'): [2021, 2022, 2023, 2024, 2025],
    ('DI Yogyakarta', 'grdp_constant', 'B1'): [2020, 2021, 2022, 2023, 2024, 2025],
    ('DI Yogyakarta', 'grdp_constant', 'B2'): [2020, 2021, 2022, 2023, 2024, 2025],
    ('DI Yogyakarta', 'grdp_constant', 'B3'): [2020, 2021, 2022, 2023, 2024, 2025],
    ('DI Yogyakarta', 'grdp_constant', 'C1'): [2020, 2021, 2022, 2023, 2024, 2025],
    ('DI Yogyakarta', 'grdp_constant', 'C11'): [2020, 2021, 2022, 2023, 2024, 2025],
    ('DI Yogyakarta', 'grdp_current', 'B1'): [2020, 2021, 2022, 2023, 2024, 2025],
    ('DI Yogyakarta', 'grdp_current', 'B2'): [2020, 2021, 2022, 2023, 2024, 2025],
    ('DI Yogyakarta', 'grdp_current', 'B3'): [2020, 2021, 2022, 2023, 2024, 2025],
    ('DI Yogyakarta', 'grdp_current', 'C1'): [2020, 2021, 2022, 2023, 2024, 2025],
    ('DI Yogyakarta', 'grdp_current', 'C11'): [2020, 2021, 2022, 2023, 2024, 2025],
    ('Kalimantan Tengah', 'grdp_constant', 'C1'): [2023, 2024, 2025],
    ('Kalimantan Tengah', 'grdp_constant', 'C11'): [2023, 2024, 2025],
    ('Kalimantan Tengah', 'grdp_constant', 'C1A'): [2023, 2024, 2025],
    ('Kalimantan Tengah', 'grdp_constant', 'C1B'): [2023, 2024, 2025],
    ('Kalimantan Tengah', 'grdp_constant', 'C3'): [2023, 2024, 2025],
    ('Kalimantan Tengah', 'grdp_constant', 'C5'): [2023, 2024, 2025],
    ('Kalimantan Tengah', 'grdp_current', 'C1'): [2023, 2024, 2025],
    ('Kalimantan Tengah', 'grdp_current', 'C11'): [2023, 2024, 2025],
    ('Kalimantan Tengah', 'grdp_current', 'C1A'): [2023, 2024, 2025],
    ('Kalimantan Tengah', 'grdp_current', 'C1B'): [2023, 2024, 2025],
    ('Kalimantan Tengah', 'grdp_current', 'C3'): [2023, 2024, 2025],
    ('Kalimantan Tengah', 'grdp_current', 'C5'): [2023, 2024, 2025],
    ('Kalimantan Selatan', 'grdp_constant', 'C1'): [2020],
    ('Kalimantan Selatan', 'grdp_constant', 'C11'): [2020],
    ('Kalimantan Selatan', 'grdp_constant', 'C3'): [2020],
    ('Kalimantan Selatan', 'grdp_constant', 'C5'): [2020],
    ('Kalimantan Selatan', 'grdp_current', 'C1'): [2020],
    ('Kalimantan Selatan', 'grdp_current', 'C11'): [2020],
    ('Kalimantan Selatan', 'grdp_current', 'C3'): [2020],
    ('Kalimantan Selatan', 'grdp_current', 'C5'): [2020],
    ('Kalimantan Timur', 'grdp_constant', 'C11'): [2020, 2021, 2022, 2023],
    ('Kalimantan Timur', 'grdp_constant', 'C3'): [2020, 2021, 2022, 2023, 2024, 2025],
    ('Kalimantan Timur', 'grdp_current', 'C11'): [2020, 2021, 2022, 2023],
    ('Kalimantan Timur', 'grdp_current', 'C3'): [2020, 2021, 2022, 2023, 2024, 2025],
    ('Sulawesi Selatan', 'grdp_constant', 'C1'): [2021],
    ('Sulawesi Selatan', 'grdp_constant', 'C13'): [2021],
    ('Sulawesi Selatan', 'grdp_constant', 'H'): [2021],
    ('Sulawesi Selatan', 'grdp_current', 'C1'): [2021],
    ('Sulawesi Selatan', 'grdp_current', 'C13'): [2021],
    ('Papua Barat', 'grdp_constant', 'B2'): [2023, 2024, 2025],
    ('Papua Barat', 'grdp_constant', 'C11'): [2023, 2024, 2025],
    ('Papua Barat', 'grdp_constant', 'C13'): [2023, 2024, 2025],
    ('Papua Barat', 'grdp_constant', 'C3'): [2023, 2024, 2025],
    ('Papua Barat', 'grdp_current', 'B2'): [2023, 2024, 2025],
    ('Papua Barat', 'grdp_current', 'C11'): [2023, 2024, 2025],
    ('Papua Barat', 'grdp_current', 'C13'): [2023, 2024, 2025],
    ('Papua Barat', 'grdp_current', 'C3'): [2023, 2024, 2025],
    ('Papua Barat Daya', 'grdp_constant', 'C11'): [2023, 2024, 2025],
    ('Papua Barat Daya', 'grdp_constant', 'C13'): [2023, 2024, 2025],
    ('Papua Barat Daya', 'grdp_constant', 'C3'): [2023, 2024, 2025],
    ('Papua Barat Daya', 'grdp_current', 'C11'): [2023, 2024, 2025],
    ('Papua Barat Daya', 'grdp_current', 'C13'): [2023, 2024, 2025],
    ('Papua Barat Daya', 'grdp_current', 'C3'): [2023, 2024, 2025],
}

# Identities: parent -> parts, checked whenever the parent is present
IDENTITIES = {
    "TOTAL": CATEGORIES,
    "B": ["B1", "B2", "B3", "B4"],
    "C": [f"C{i}" for i in range(1, 17)],
    "C1": ["C1A", "C1B"],
}

# Rounding tolerance for an identity: one unit in the last written decimal for each part, in Rp billion
def tolerance(context, parts):
    return 10 ** (-context.get("written_decimals", context["decimals"]) + context["shift"]) * parts + 1e-9

# Identity breaks in the source that are not rounding, found by opening the tables:
# (province, indicator, parent, year) -> published parts minus published parent, in Rp billion.
# The build stops if a break changes size or a new one appears.
KNOWN_BREAKS = {
    # H (Transportasi dan Pergudangan) is empty in the 2021 constant-price column, so the categories fall short of TOTAL by H
    ("Sulawesi Selatan", "grdp_constant", "TOTAL", 2021): -9901.01,
    # Sulawesi Barat's published categories and subsectors do not add up beyond rounding in these years
    ("Sulawesi Barat", "grdp_current", "TOTAL", 2021): 0.0143,
    ("Sulawesi Barat", "grdp_current", "TOTAL", 2022): 7.367,
    ("Sulawesi Barat", "grdp_constant", "C", 2021): -19.6075,
    ("Sulawesi Barat", "grdp_constant", "C", 2022): -17.2204,
    ("Sulawesi Barat", "grdp_constant", "C", 2023): -7.8578,
}

# Plausibility ranges; a value outside its range is flagged, not dropped
PLAUSIBLE = {
    "grdp_current_growth_pct": (-20, 40),
    "grdp_constant_growth_pct": (-15, 30),
    "national_table_gap_pct": (-0.5, 0.5),
}

URL_WEBAPI = "https://webapi.bps.go.id/v1/api/list/model/data/lang/ind/domain/{domain}/var/{var}/th/{th}/key/KEY/"

# Functions

def row(code, indicator, sector, period, value, status=""):
    """Return one long row."""
    return {"province_code": code, "indicator": indicator, "sector": sector, "period": period,
            "status": status, "value": value}


def check_table(context, response, where):
    """Stop unless the response still carries the unit, decimals, price basis and status phrases declared for it."""
    var = response["var"][0]
    unit_field = var["label"] if context.get("unit_in_title") else var["unit"]
    cleaning.require_text(unit_field, context["unit"], f"{where} unit")
    assert str(var["decimal"]) == str(context["decimals"]), (where, var["decimal"])
    labels = [tv["label"].strip() for tv in response["turvar"]]
    if None in context["prices"]:
        assert labels == ["Tidak ada"], (where, labels)
        cleaning.require_text(var["label"], context["prices"][None][1], f"{where} title")
    else:
        assert sorted(labels) == sorted(context["prices"]), (where, labels)
    note = cleaning.html_to_text(f"{var['def']} {var['note']}")
    for phrase in context["status_text"]:
        cleaning.require_text(" ".join(note.split()), phrase, f"{where} note")
    assert [t["label"] for t in response["turtahun"]] == ["Tahun"], where


def read_response(record, lookup):
    """Read one saved WebAPI response (one province, table and year) into long rows."""
    context = READ_CONTEXT[(record["domain"], record["var"])]
    response = record["response"]
    where = f"{context['province']} var {record['var']} {record['year']}"
    assert response["data-availability"] == "available" and response["var"][0]["val"] == record["var"], where
    check_table(context, response, where)
    # The table must hold one year, the year the record says
    assert [t["label"] for t in response["tahun"]] == [record["year"]], where
    code = cleaning.province_code(context["province"], lookup,
                                  record["domain"][:2] if context.get("code_in_domain", True) else None)
    # Match row labels to sector codes by name
    patterns = {s: p for s, (p, _) in SECTORS.items() if context.get("c1_split") or s not in SPLIT_ONLY}
    index = cleaning.match_rows([v["label"] for v in response["vervar"]], patterns, context.get("fixes"), where)
    sector_of = {response["vervar"][i]["val"]: s for s, i in index.items()}
    out = []
    for v, tv, th, tt, text in cleaning.bps_api_cells(response):
        if v["val"] not in sector_of:
            continue
        prices = context["prices"]
        indicator = prices[None][0] if None in prices else prices[tv["label"].strip()]
        value = cleaning.parse_number(text, ".", None, max_decimals=context["decimals"], shift=context["shift"])
        status = context["status"].get(int(record["year"]), "")
        out.append(row(code, indicator, sector_of[v["val"]], record["year"], value, status))
    info = {"province_code": code, "domain": record["domain"], "var": record["var"], "title": response["var"][0]["label"],
            "unit_published": context["unit"], "decimal_shift_to_milyar": context["shift"],
            "note": " ".join(cleaning.html_to_text(f"{response['var'][0]['def']} {response['var'][0]['note']}").split())}
    return out, info, response["last_update"], code


def expected_keys(tables):
    """Every key the tables should yield: each table's sectors, price bases and years, less the declared gaps."""
    keys = set()
    for (domain, var), t in tables.items():
        context = READ_CONTEXT[(domain, var)]
        sectors = [s for s in SECTORS if context.get("c1_split") or s not in SPLIT_ONLY]
        indicators = [p[0] if isinstance(p, tuple) else p for p in context["prices"].values()]
        for year in t["years"]:
            for ind in indicators:
                keys |= {(t["code"], ind, s, year) for s in sectors
                         if int(year) not in SOURCE_GAPS.get((context["province"], ind, s), [])}
    return keys


def identity_checks(df, context_of):
    """Layer 3: categories sum to TOTAL, subsectors to their category, C.1 parts to C.1, within rounding.

    context_of maps (province_code, indicator) to the read context of the table that gave those values.
    An empty part counts as zero; C.1 is checked only where the table splits it.
    """
    results, breaks_seen = [], {}
    code_of = {cleaning.normalise_name(p["name"]): c for c, p in provinces.items()}
    breaks = {(code_of[cleaning.normalise_name(p)], ind, parent, str(y)): v for (p, ind, parent, y), v in KNOWN_BREAKS.items()}
    wide = df.pivot_table(index=["province_code", "indicator", "period"], columns="sector", values="value")
    for parent, parts in IDENTITIES.items():
        sub = wide[wide[parent].notna()]
        if parent == "C1":
            sub = sub[[context_of[k[:2]].get("c1_split", False) for k in sub.index]]
        gap = sub[parts].fillna(0.0).sum(axis=1) - sub[parent]
        tol = pd.Series([tolerance(context_of[k[:2]], len(parts)) for k in sub.index], index=sub.index, dtype=float)
        within = gap.abs() <= tol
        # A gap beyond rounding must be a declared break of the same size
        for k in gap[~within].index:
            declared = breaks.get((k[0], k[1], parent, k[2]))
            if declared is None or abs(gap[k] - declared) > tol[k]:
                raise ValueError(f"{parent} parts do not sum at {k}: gap {gap[k]:.4f}, declared {declared}")
            breaks_seen[(k[0], k[1], parent, k[2])] = round(float(gap[k]), 4)
        results.append({"check": f"{parts[0]}..{parts[-1]} sum to {parent}", "compared": int(len(gap)),
                        "largest_gap_within_rounding": float(round(gap[within].abs().max(), 6)),
                        "declared_breaks": int((~within).sum()),
                        "tolerance": "one unit in the last written decimal for each part, in Rp billion"})
    missing = set(breaks) - set(breaks_seen)
    if missing:
        raise ValueError(f"declared identity breaks not found: {sorted(missing)}")
    return results


def plausibility_flags(df, national):
    """Layer 5: year-on-year changes of TOTAL, and gaps against the national BPS table, outside their ranges."""
    flags = []
    for indicator in INDICATORS:
        s = df[(df["indicator"] == indicator) & (df["sector"] == "TOTAL")].sort_values(["province_code", "period"])
        s = s.assign(change=s.groupby("province_code")["value"].pct_change() * 100).dropna(subset=["change"])
        # Papua Barat loses Papua Barat Daya from 2023, so its 2023 change compares different areas
        s = s[~((s["province_code"] == "91") & (s["period"] == "2023"))]
        check = f"{indicator}_growth_pct"
        flags += cleaning.flag_outside([{"province_code": r.province_code, "period": r.period, "value": r.change}
                                        for r in s.itertuples()], check, *PLAUSIBLE[check])
    flags += cleaning.flag_outside(national.to_dict("records"), "national_table_gap_pct", *PLAUSIBLE["national_table_gap_pct"])
    return flags


def compare_national(df):
    """Compare current-price values with the national BPS table in data/, a separate release, by percentage gap."""
    nat = pd.read_csv(NATIONAL, dtype={"province_code": str, "period": str, "sector": str, "status": str}, keep_default_na=False)
    nat = nat[(nat["indicator"] == "grdp_current") & ~nat["period"].str.contains("Q")]
    merged = df[df["indicator"] == "grdp_current"].merge(nat, on=["province_code", "sector", "period"], suffixes=("", "_national"))
    merged["value"] = (merged["value"] / merged["value_national"] - 1) * 100
    return merged[["province_code", "sector", "period", "value"]]


# Steps

# Read the BPS province list that every province name is matched against
provinces, lookup = cleaning.load_bps_provinces(RAW_PROVINCES)

# Read every saved response, checking each table against its declared read context
records = cleaning.read_jsonl(RAW_GRDP)
assert {(r["domain"], r["var"]) for r in records} == set(READ_CONTEXT), "tables in the file differ from READ_CONTEXT"
rows, tables, context_of, excluded = [], {}, {}, {}
for record in records:
    out, info, updated, code = read_response(record, lookup)
    # An excluded table is read and checked above, then left out of the dataset with its reason
    reason = READ_CONTEXT[(record["domain"], record["var"])].get("exclude")
    if reason:
        excluded[f"{code} var {record['var']}"] = {"title": info["title"], "years": excluded.get(f"{code} var {record['var']}", {}).get("years", []) + [record["year"]], "reason": reason}
        continue
    rows += out
    t = tables.setdefault((record["domain"], record["var"]), {**info, "code": code, "years": [], "last_update": {}})
    t["years"].append(record["year"])
    t["last_update"][record["year"]] = updated
    context_of |= {(code, r["indicator"]): READ_CONTEXT[(record["domain"], record["var"])] for r in out}

# Layer 4: each value comes from one table, so a repeated key means two tables claim it
rows, overlaps = cleaning.merge_sources([("BPS WebAPI provincial tables", rows)], KEYS)

# Layers 3 and 5: identities stop the build; changes and gaps against the national table only flag
df = pd.DataFrame(rows)
identities = identity_checks(df, context_of)
national = compare_national(df)
flags = plausibility_flags(df, national)

# Describe the dataset
excluded_codes = {k.split()[0] for k in excluded}
first_year = df.groupby("province_code")["period"].min().to_dict()
last_year = df.groupby("province_code")["period"].max().to_dict()
has_constant = sorted(df.loc[df["indicator"] == "grdp_constant", "province_code"].unique())
meta = {
    "title": "BPS provincial GRDP by industry with mining and manufacturing subsectors, Indonesia",
    "columns": {
        "province_code": "BPS province code (kode_bps). Names and Kemendagri codes in 'provinces'.",
        "indicator": "grdp_current or grdp_constant; definitions in 'indicators'.",
        "sector": "Sector code; names in 'sectors'. Categories use the codes of data/20261102_bps-province-grdp-population.",
        "period": "YYYY, annual.",
        "status": "BPS revision marker from the provincial table note; meanings in 'status'.",
        "value": "Rp billion (Milyar Rupiah). Multiply by 1e9 for rupiah.",
    },
    "provinces": {c: p for c, p in provinces.items() if c in set(df["province_code"])},
    "sectors": {s: name for s, (_, name) in SECTORS.items()},
    "indicators": {
        ind: {"name": name, "unit": "Rp billion (Milyar Rupiah)", "multiplier": 1e9, "base_unit": "Rp",
              "source": "BPS provincial offices, statistics tables through the BPS WebAPI; see 'source_tables'"}
        for ind, name in INDICATORS.items()
    },
    "coverage": {
        "provinces": len(set(df["province_code"])),
        "years_by_province": {c: f"{first_year[c]}-{last_year[c]}" for c in sorted(first_year)},
        "constant_prices": has_constant,
        "without_subsector_table": {c: provinces[c]["name"] for c in provinces
                                    if c not in set(df["province_code"]) | excluded_codes and c != cleaning.NATIONAL_CODE},
        "excluded_tables": excluded,
        "c1_split": sorted({tables[k]["code"] for k, c in READ_CONTEXT.items() if c.get("c1_split")}),
    },
    "source_tables": {f"{t['code']} var {k[1]}": {**{x: t[x] for x in ["domain", "var", "title", "unit_published", "decimal_shift_to_milyar", "note", "last_update"]},
                                                  "request": URL_WEBAPI.format(domain=k[0], var=k[1], th="<year id>")}
                      for k, t in tables.items()},
    "source_gaps": {f"{p} {ind} {s}": years for (p, ind, s), years in SOURCE_GAPS.items()},
    "notes": [
        "Each province's table is a separate BPS release, revised on its own date (see source_tables last_update), so provinces are not of one vintage and do not sum to Indonesia.",
        "Values published in Juta Rupiah (Sumatera Barat, Jawa Tengah, Kalimantan Utara, Sulawesi Tenggara, Gorontalo, Sulawesi Barat) are written in Milyar Rupiah by moving the decimal point three places; no digit is rounded.",
        "An empty source cell has no row (see source_gaps); identities count it as zero.",
        "C1A and C1B split C1 for Jambi, Nusa Tenggara Barat, Kalimantan Tengah, Kalimantan Utara and Gorontalo only.",
        "Maluku Utara labels its B.4 row 'Perikanan'; the row sits under mining and B1+B2+B3+B4 = B holds with it, so it is read as B4.",
        "Papua Barat values from 2023 exclude Papua Barat Daya (table note), while the national BPS tables separate the two from 2024. Papua Barat Daya (92) has values from 2023.",
        "status follows each provincial table note. Tables without a note (Riau, Jambi, Lampung, Kepulauan Bangka Belitung, Jawa Barat, DI Yogyakarta, Kalimantan Timur, Kalimantan Utara, Sulawesi Tenggara, Gorontalo) carry no marker, although their latest years are preliminary. The Jawa Timur (n-1, n-2) and Sulawesi Utara (t-1, t-2) notes are read with n = t = 2026.",
        "Shares (coal share = B2 / TOTAL, other extractives = (B1 + B3 + C11) / TOTAL) and per-capita values belong in analysis/.",
    ],
    "checks": {
        "passed": ["identities", "cross-source"],
        "identities": identities,
        "identity_breaks": {f"{p} {ind} {parent} {y}": {"parts_minus_total": v} for (p, ind, parent, y), v in KNOWN_BREAKS.items()},
        "identity_breaks_note": "Gaps beyond rounding in the source tables. Sulawesi Selatan 2021 constant: H is empty, so the gap equals H. Sulawesi Barat: the published parts do not add up; no value is changed.",
        "cross_source_overlaps": overlaps,
        "national_table_comparison": {
            "against": str(NATIONAL.relative_to(ROOT)),
            "compared": int(len(national)),
            "largest_gap_pct": float(round(national["value"].abs().max(), 4)),
            "note": "The national table is a different BPS release, so gaps are recorded, not forced to zero; gaps outside the range are flagged.",
        },
        "plausible_ranges": PLAUSIBLE,
        "flags": flags,
    },
}

# Layers 1, 2 and 6: check structure and completeness, then write the CSV and metadata
out = cleaning.write_dataset(
    rows, KEYS,
    allowed={"province_code": provinces, "indicator": list(INDICATORS), "sector": list(SECTORS)},
    expected=expected_keys(tables),
    csv_path=OUT_CSV, meta=meta, raw_files=[RAW_GRDP, RAW_PROVINCES, NATIONAL],
    sort_orders={"sector": list(SECTORS)},
)

# Report what was written
print(f"{OUT_CSV.name}: {len(out)} rows, {len(flags)} plausibility flags")
print(out.groupby(["indicator", "status"]).size().to_string())
for f in flags:
    print("  flag:", f)
